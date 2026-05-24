from __future__ import annotations

import time

from app.cache import LocalCache, invalidate_all_caches, invalidate_source_dependent_caches


def test_cache_put_and_get(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")

    cache.put("retrieval", "bakery", {"citations": ["chunk-1"]})

    assert cache.get("retrieval", "bakery") == {"citations": ["chunk-1"]}
    assert cache.get("retrieval", "missing") is None


def test_cache_ttl_expiry(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")

    cache.put("analysis", "request", {"status": "ok"}, ttl_seconds=1)
    assert cache.get("analysis", "request") == {"status": "ok"}

    time.sleep(1.1)

    assert cache.get("analysis", "request") is None


def test_cache_version_invalidation(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")
    cache.put("retrieval", "old", {"value": 1}, version="v1")
    cache.put("retrieval", "current", {"value": 2}, version="v2")

    deleted = cache.invalidate_by_version("retrieval", "v2")

    assert deleted == 1
    assert cache.get("retrieval", "old") is None
    assert cache.get("retrieval", "current") == {"value": 2}


def test_cache_namespace_invalidation(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")
    cache.put("retrieval", "a", {"value": 1})
    cache.put("analysis", "a", {"value": 2})

    deleted = cache.invalidate("retrieval")

    assert deleted == 1
    assert cache.get("retrieval", "a") is None
    assert cache.get("analysis", "a") == {"value": 2}


def test_source_dependent_cache_invalidation(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")
    cache.put("address_normalization", "raw", {"value": 1})
    cache.put("jurisdiction", "37:-80", {"value": 2})
    cache.put("retrieval", "query", {"value": 3})
    cache.put("analysis", "request", {"value": 4})

    deleted = invalidate_source_dependent_caches(cache)

    assert deleted == 2
    assert cache.get("address_normalization", "raw") == {"value": 1}
    assert cache.get("jurisdiction", "37:-80") == {"value": 2}
    assert cache.get("retrieval", "query") is None
    assert cache.get("analysis", "request") is None


def test_all_cache_invalidation(tmp_path) -> None:
    cache = LocalCache(tmp_path / "cache.sqlite3")
    for namespace in ["address_normalization", "jurisdiction", "retrieval", "analysis"]:
        cache.put(namespace, "key", {"value": namespace})

    deleted = invalidate_all_caches(cache)

    assert deleted == 4
    for namespace in ["address_normalization", "jurisdiction", "retrieval", "analysis"]:
        assert cache.get(namespace, "key") is None
