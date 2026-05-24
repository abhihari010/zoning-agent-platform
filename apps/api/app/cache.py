"""SQLite-backed result cache with namespace and version invalidation.

Namespaces used by this application:
  - ``address_normalization`` - key: normalized raw address string
  - ``jurisdiction`` - key: ``{lat}:{lng}``
  - ``retrieval`` - key: ``{jurisdiction_id}:{district}:{use}:{scope}:{source_version}``
  - ``analysis`` - key: ``{request_hash}:{source_index_version}:{provider}:{prompt_version}``

Cache entries are automatically expired by TTL and optionally invalidated
when the associated version string changes.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.settings import get_settings


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache_entries (
    namespace    TEXT NOT NULL,
    cache_key    TEXT NOT NULL,
    value_json   TEXT NOT NULL,
    version      TEXT,
    created_at   TEXT NOT NULL,
    expires_at   TEXT,
    PRIMARY KEY (namespace, cache_key)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalCache:
    """Thread-safe (single-writer) SQLite-backed cache.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Defaults to the path configured
        in ``Settings.cache_db_path``.  Pass ``:memory:`` for an ephemeral
        in-process cache (useful in tests).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            try:
                settings = get_settings()
                db_path = settings.cache_db_path
            except Exception:
                db_path = Path("app/data/cache.sqlite3")

        self._path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, namespace: str, key: str) -> Any | None:
        """Return cached value or ``None`` when missing / expired."""
        conn = self._connection()
        row = conn.execute(
            "SELECT value_json, expires_at FROM cache_entries WHERE namespace=? AND cache_key=?",
            (namespace, key),
        ).fetchone()
        if row is None:
            return None
        value_json, expires_at = row
        if expires_at and _now_iso() > expires_at:
            # Entry expired; delete lazily.
            conn.execute(
                "DELETE FROM cache_entries WHERE namespace=? AND cache_key=?",
                (namespace, key),
            )
            conn.commit()
            return None
        try:
            return json.loads(value_json)
        except Exception:
            return None

    def put(
        self,
        namespace: str,
        key: str,
        value: Any,
        version: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """Insert or replace a cache entry."""
        now = _now_iso()
        expires_at: str | None = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            ).isoformat()
        conn = self._connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_entries
                (namespace, cache_key, value_json, version, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (namespace, key, json.dumps(value), version, now, expires_at),
        )
        conn.commit()

    def invalidate(self, namespace: str, key: str | None = None) -> int:
        """Delete one entry (if *key* given) or all entries in *namespace*.

        Returns the number of deleted rows.
        """
        conn = self._connection()
        if key is not None:
            cur = conn.execute(
                "DELETE FROM cache_entries WHERE namespace=? AND cache_key=?",
                (namespace, key),
            )
        else:
            cur = conn.execute(
                "DELETE FROM cache_entries WHERE namespace=?",
                (namespace,),
            )
        conn.commit()
        return cur.rowcount

    def invalidate_by_version(self, namespace: str, current_version: str) -> int:
        """Delete all entries in *namespace* whose stored version != *current_version*.

        Useful for evicting stale data after a reindex or prompt bump.
        Returns the number of deleted rows.
        """
        conn = self._connection()
        cur = conn.execute(
            "DELETE FROM cache_entries WHERE namespace=? AND (version IS NULL OR version != ?)",
            (namespace, current_version),
        )
        conn.commit()
        return cur.rowcount

    def invalidate_namespaces(self, *namespaces: str) -> int:
        """Convenience: delete all entries in each of the given namespaces."""
        total = 0
        for ns in namespaces:
            total += self.invalidate(ns)
        return total

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        conn = self._connection()
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._path != ":memory:":
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn


# ---------------------------------------------------------------------------
# Module-level singleton avoids re-opening the DB on every request.
# Tests should create their own instance with db_path=":memory:".
# ---------------------------------------------------------------------------

_cache_instance: LocalCache | None = None


def get_cache() -> LocalCache:
    """Return the module-level LocalCache singleton.

    The cache is only created when first accessed so that importing this
    module does not trigger DB creation at import time.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LocalCache()
    return _cache_instance


def invalidate_source_dependent_caches(cache: LocalCache | None = None) -> int:
    """Invalidate caches whose values depend on source documents or chunks."""
    resolved = cache or get_cache()
    return resolved.invalidate_namespaces("retrieval", "analysis")


def invalidate_all_caches(cache: LocalCache | None = None) -> int:
    """Invalidate all currently defined local cache namespaces."""
    resolved = cache or get_cache()
    return resolved.invalidate_namespaces(
        "address_normalization",
        "jurisdiction",
        "retrieval",
        "analysis",
    )
