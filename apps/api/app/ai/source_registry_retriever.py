from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai.interfaces import RetrievalProviderRequest, RetrievalProviderResult
from app.cache import invalidate_all_caches, invalidate_source_dependent_caches
from app.ingestion import build_source_chunks
from app.models import SourceChunk, SourceCitation, SourceRegistryEntry
from app.settings import get_settings
from app.storage import SQLiteStore, store


SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "source_registry.json"


@dataclass(frozen=True)
class SourceIndexReadiness:
    source_count: int
    chunk_count: int
    index_ready: bool
    stale_source_ids: list[str] = field(default_factory=list)
    missing_chunk_source_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_seed_source_registry() -> list[dict[str, Any]]:
    if not SOURCE_REGISTRY_PATH.exists():
        return []

    with SOURCE_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def ensure_seed_sources(source_store: SQLiteStore = store) -> None:
    settings = get_settings()
    if not settings.auto_seed_sources:
        return

    version_stage = (
        f"source.seed.registry_version.{settings.source_registry_version}"
        if settings.source_registry_version
        else ""
    )
    should_seed = source_store.get_source_count() == 0 or (
        bool(version_stage) and source_store.get_latest_audit_timestamp(version_stage) is None
    )
    if not should_seed:
        return

    seeded_count = 0
    for source in _load_seed_source_registry():
        try:
            entry = SourceRegistryEntry.model_validate(source)
        except Exception:
            continue
        source_store.upsert_source(entry)
        seeded_count += 1

    if seeded_count:
        invalidate_all_caches()
        source_store.audit("source.seed.completed", f"{seeded_count} sources")
        if version_stage:
            source_store.audit(version_stage, "source-registry")


# Memoized readiness for the production global store, keyed on a cheap
# (source_count, chunk_count) signature. Computing readiness loads AND rebuilds
# the entire corpus (build_source_chunks over every source), materializing 20k+
# chunks twice per call; doing that on every /ready check and every analyze blew
# the instance memory limit at breadth scale. See ensure_source_index_ready.
_READINESS_MEMO: tuple[tuple[int, int], "SourceIndexReadiness"] | None = None


def reset_source_index_readiness_memo() -> None:
    """Clear the memoized readiness result (e.g. after an in-process reindex)."""
    global _READINESS_MEMO
    _READINESS_MEMO = None


def ensure_source_index_ready(source_store: SQLiteStore = store) -> SourceIndexReadiness:
    ensure_seed_sources(source_store)

    # Hot-path memoization (production global store only). The corpus only
    # changes via (re)indexing, which moves the source/chunk counts, so we cache
    # the readiness result and recompute the expensive load+rebuild only when
    # those counts change. A throwaway store (tests) is never memoized.
    global _READINESS_MEMO
    use_memo = source_store is store
    if use_memo:
        signature = (source_store.get_source_count(), source_store.get_source_chunk_count())
        if _READINESS_MEMO is not None and _READINESS_MEMO[0] == signature:
            return _READINESS_MEMO[1]

    sources = source_store.list_sources()
    chunks = source_store.list_source_chunks()
    expected_chunks = build_source_chunks(sources)
    stale_source_ids = _stale_source_ids(expected_chunks, chunks)
    missing_chunk_source_ids = _missing_chunk_source_ids(sources, chunks)
    settings = get_settings()
    should_reindex = bool(sources) and (
        stale_source_ids
        or (bool(missing_chunk_source_ids) and (bool(chunks) or settings.auto_reindex_on_empty))
        or (settings.auto_reindex_on_empty and not chunks)
    )

    if should_reindex:
        chunks = source_store.replace_source_chunks(expected_chunks)
        invalidate_source_dependent_caches()
        source_store.audit(
            "source.index.auto_reindex.completed",
            _auto_reindex_reason(stale_source_ids, missing_chunk_source_ids),
        )
        stale_source_ids = _stale_source_ids(expected_chunks, chunks)
        missing_chunk_source_ids = _missing_chunk_source_ids(sources, chunks)

    warnings: list[str] = []
    if not sources:
        warnings.append("No source registry entries are available.")
    if sources and not chunks:
        warnings.append("No indexed source chunks are available.")
    if stale_source_ids:
        warnings.append("Some indexed source chunks are stale.")
    if missing_chunk_source_ids:
        warnings.append("Some source registry entries do not have indexed chunks.")

    readiness = SourceIndexReadiness(
        source_count=len(sources),
        chunk_count=len(chunks),
        index_ready=bool(sources) and bool(chunks) and not stale_source_ids and not missing_chunk_source_ids,
        stale_source_ids=stale_source_ids,
        missing_chunk_source_ids=missing_chunk_source_ids,
        warnings=warnings,
    )

    if use_memo:
        # Re-read counts: an auto-reindex above may have changed them.
        signature = (source_store.get_source_count(), source_store.get_source_chunk_count())
        _READINESS_MEMO = (signature, readiness)
    return readiness


def _expected_hash_by_source(chunks: list[SourceChunk]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for chunk in chunks:
        hashes.setdefault(chunk.source_id, chunk.source_text_hash)
    return hashes


def _actual_hashes_by_source(chunks: list[SourceChunk]) -> dict[str, set[str]]:
    hashes: dict[str, set[str]] = {}
    for chunk in chunks:
        hashes.setdefault(chunk.source_id, set()).add(chunk.source_text_hash)
    return hashes


def _stale_source_ids(expected_chunks: list[SourceChunk], chunks: list[SourceChunk]) -> list[str]:
    expected = _expected_hash_by_source(expected_chunks)
    actual = _actual_hashes_by_source(chunks)
    return sorted(
        source_id
        for source_id, expected_hash in expected.items()
        if source_id in actual and actual[source_id] != {expected_hash}
    )


def _missing_chunk_source_ids(
    sources: list[SourceRegistryEntry],
    chunks: list[SourceChunk],
) -> list[str]:
    chunk_source_ids = {chunk.source_id for chunk in chunks}
    return sorted(source.source_id for source in sources if source.source_id not in chunk_source_ids)


def _auto_reindex_reason(stale_source_ids: list[str], missing_chunk_source_ids: list[str]) -> str:
    reasons: list[str] = []
    if stale_source_ids:
        reasons.append(f"stale={','.join(stale_source_ids)}")
    if missing_chunk_source_ids:
        reasons.append(f"missing={','.join(missing_chunk_source_ids)}")
    return "; ".join(reasons) or "empty-index"


class SourceRegistryRetrievalProvider:
    name = "source_registry"

    def __init__(self, source_store: SQLiteStore = store) -> None:
        self.source_store = source_store

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        ensure_source_index_ready(self.source_store)
        chunks = self.source_store.list_source_chunks_filtered(
            jurisdiction_id=request.jurisdiction_id,
            district=request.district,
            use=request.inferred_use,
        )
        hits: list[SourceCitation] = []
        for chunk in chunks[:5]:
            hits.append(
                SourceCitation(
                    source_id=chunk.source_id,
                    title=chunk.title,
                    excerpt=chunk.chunk_text,
                    section_ref=chunk.section_ref,
                    chunk_id=chunk.chunk_id,
                    jurisdiction_id=chunk.jurisdiction_id,
                    source_type=chunk.source_type,
                    url=chunk.url,
                    effective_date=chunk.effective_date,
                    retrieved_at=chunk.retrieved_at,
                    score=1.0,
                    metadata=chunk.metadata,
                )
            )

        return RetrievalProviderResult(citations=hits, chunks=chunks[:5])
