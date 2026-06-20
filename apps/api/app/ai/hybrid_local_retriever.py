from __future__ import annotations

import hashlib
import json
import re
import time

from app.ai.embedding_provider import cosine_similarity
from app.ai.interfaces import (
    EmbeddingProvider,
    EmbeddingProviderRequest,
    RetrievalProviderRequest,
    RetrievalProviderResult,
)
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider, ensure_source_index_ready
from app.models import RetrievalDiagnostics, SourceChunk, SourceCitation
from app.settings import get_settings
from app.storage import SQLiteStore, store


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_CACHE_NAMESPACE = "retrieval"


class HybridLocalRetrievalProvider:
    name = "hybrid_local"

    def __init__(
        self,
        source_store: SQLiteStore = store,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.source_store = source_store
        self.embedding_provider = embedding_provider

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        start = time.monotonic()
        ensure_source_index_ready(self.source_store)
        settings = get_settings()
        source_index_version = _source_index_version(self.source_store, settings.source_index_version)

        # ------------------------------------------------------------------ #
        # Cache check
        # ------------------------------------------------------------------ #
        cache_key: str | None = None
        if settings.cache_enabled:
            try:
                from app.cache import get_cache

                cache = get_cache()
                cache_key = _build_retrieval_cache_key(request, source_index_version)
                cached = cache.get(_CACHE_NAMESPACE, cache_key)
                if cached is not None:
                    # Deserialize citations from cached JSON
                    from app.models import SourceChunk as _SCH
                    from app.models import SourceCitation as _SC

                    cached_citations = cached.get("citations", cached) if isinstance(cached, dict) else cached
                    cached_chunks = cached.get("chunks", []) if isinstance(cached, dict) else []
                    citations = [_SC.model_validate(c) for c in cached_citations]
                    chunks = [_SCH.model_validate(c) for c in cached_chunks]
                    return RetrievalProviderResult(
                        citations=citations,
                        chunks=chunks,
                        diagnostics=RetrievalDiagnostics(
                            query_text=request.query,
                            filters={
                                "jurisdiction_id": request.jurisdiction_id,
                                "district": request.district,
                                "use": request.inferred_use,
                            },
                            sql_chunk_count=0,
                            vector_hit_count=None,
                            vector_provider=settings.vector_provider,
                            fallback_used=False,
                            fallback_reason="cache_hit",
                            elapsed_ms=(time.monotonic() - start) * 1000,
                        ),
                    )
            except Exception:
                cache_key = None  # Cache unavailable; continue without it.

        # ------------------------------------------------------------------ #
        # Live retrieval
        # ------------------------------------------------------------------ #
        result: RetrievalProviderResult | None = None

        if settings.vector_provider == "qdrant" and self.embedding_provider:
            try:
                result = self._retrieve_with_qdrant(request, start)
            except Exception as exc:
                # Qdrant failed; fall through to SQL-backed keyword retrieval.
                result = self._fallback_to_sql(
                    request,
                    start,
                    vector_hit_count=None,
                    reason=f"Qdrant error: {exc}",
                )

        if result is None:
            # No Qdrant or no embedding provider; use SQL-backed keyword retrieval.
            chunks = self.source_store.list_source_chunks_filtered(
                jurisdiction_id=request.jurisdiction_id,
                district=request.district,
                use=request.inferred_use,
            )
            if not chunks:
                fallback = SourceRegistryRetrievalProvider(self.source_store).retrieve(request)
                result = RetrievalProviderResult(
                    citations=fallback.citations,
                    diagnostics=RetrievalDiagnostics(
                        query_text=request.query,
                        filters={
                            "jurisdiction_id": request.jurisdiction_id,
                            "district": request.district,
                            "use": request.inferred_use,
                        },
                        sql_chunk_count=0,
                        vector_hit_count=None,
                        vector_provider=settings.vector_provider,
                        fallback_used=True,
                        fallback_reason="no SQL chunks matched filters",
                        elapsed_ms=(time.monotonic() - start) * 1000,
                    ),
                )
            else:
                sql_result = self._sql_keyword_retrieve(request, chunks, start)
                result = RetrievalProviderResult(
                    citations=sql_result.citations,
                    diagnostics=RetrievalDiagnostics(
                        query_text=request.query,
                        filters={
                            "jurisdiction_id": request.jurisdiction_id,
                            "district": request.district,
                            "use": request.inferred_use,
                        },
                        sql_chunk_count=len(chunks),
                        vector_hit_count=None,
                        vector_provider=settings.vector_provider,
                        fallback_used=False,
                        fallback_reason=None,
                        elapsed_ms=(time.monotonic() - start) * 1000,
                    ),
                )

        # ------------------------------------------------------------------ #
        # Cache store
        # ------------------------------------------------------------------ #
        if cache_key and settings.cache_enabled and result.citations:
            try:
                from app.cache import get_cache

                cache = get_cache()
                cache.put(
                    _CACHE_NAMESPACE,
                    cache_key,
                    {
                        "citations": [c.model_dump() for c in result.citations],
                        "chunks": [c.model_dump() for c in result.chunks],
                    },
                    version=source_index_version or None,
                    ttl_seconds=settings.cache_default_ttl,
                )
            except Exception:
                pass  # Cache write failure is non-fatal.

        return result

    def _sql_keyword_retrieve(
        self,
        request: RetrievalProviderRequest,
        chunks: list[SourceChunk],
        start: float,
    ) -> RetrievalProviderResult:
        query = request.query
        query_tokens = _tokens(query)
        chunk_vectors = [[] for _ in chunks]
        query_vector: list[float] = []

        if self.embedding_provider:
            embeddings = self.embedding_provider.embed(
                EmbeddingProviderRequest(texts=[query, *[chunk.chunk_text for chunk in chunks]])
            ).embeddings
            if embeddings:
                query_vector = embeddings[0]
                chunk_vectors = embeddings[1:]

        scored = [
            (
                _score_chunk(chunk, request, query_tokens)
                + cosine_similarity(query_vector, chunk_vectors[index]),
                chunk,
            )
            for index, chunk in enumerate(chunks)
        ]
        ranked = [(score, chunk) for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]

        top = _diversify_ranked(ranked)
        return RetrievalProviderResult(
            citations=[
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
                    score=round(score, 4),
                    metadata=chunk.metadata,
                )
                for score, chunk in top
            ],
            chunks=[chunk for _, chunk in top],
        )

    # Secondary query injected alongside the primary to ensure procedural and
    # use-classification chapters surface even when the project description is
    # too use-specific to rank them densely on its own.
    _PERMIT_PATH_QUERY = (
        "permitted uses additional use regulations site plan "
        "planning commission FMPC approval permit requirements"
    )

    # Tertiary query that surfaces the zoning-district definitions ("legend").
    # Permitted-use tables list districts by code (e.g. DD, NC, RC4) while a
    # request names the district in prose (e.g. "Downtown District", "regional
    # commercial corridor"). A jurisdiction-neutral analysis prompt can only map
    # name->code when this legend is in the excerpts, so we retrieve and reserve
    # a slot for it (see _ensure_district_definitions).
    _DISTRICT_DEFINITIONS_QUERY = (
        "zoning district definitions and designations: names, codes, and "
        "purpose of each residential, commercial, mixed-use, and industrial "
        "zoning district in the jurisdiction"
    )

    def _retrieve_with_qdrant(
        self,
        request: RetrievalProviderRequest,
        start: float,
    ) -> RetrievalProviderResult | None:
        if not self.embedding_provider:
            return None

        # Batch all supplementary embeddings in one API call to avoid extra round-trips.
        emb_resp = self.embedding_provider.embed(
            EmbeddingProviderRequest(
                texts=[request.query, self._PERMIT_PATH_QUERY, self._DISTRICT_DEFINITIONS_QUERY]
            )
        ).embeddings
        if not emb_resp:
            return None
        query_embedding = emb_resp[0]
        if not query_embedding:
            return None
        permit_embedding = emb_resp[1] if len(emb_resp) > 1 else None
        district_embedding = emb_resp[2] if len(emb_resp) > 2 else None

        from app.rag.vector_store import QdrantVectorStore  # lazy import to avoid circular dependency

        settings = get_settings()
        vector_filters = {
            "jurisdiction_id": request.jurisdiction_id,
            "district": request.district,
            "use": request.inferred_use,
        }
        vs = QdrantVectorStore()
        primary_hits = vs.query(query_embedding, filters=vector_filters, limit=20)

        # Supplement with a permit-path query so procedural chapters (e.g.
        # site-plan requirements) are not crowded out by use-type chunks.
        permit_hits = (
            vs.query(permit_embedding, filters=vector_filters, limit=10)
            if permit_embedding
            else []
        )

        # Supplement with a district-definitions query so the district "legend"
        # (name->code mapping) is available for district inference.
        district_hits = (
            vs.query(district_embedding, filters=vector_filters, limit=6)
            if district_embedding
            else []
        )

        # Merge: keep the highest score seen for each chunk across all queries.
        hit_by_id: dict[str, object] = {}
        for hit in primary_hits + permit_hits + district_hits:
            existing = hit_by_id.get(hit.chunk_id)
            if existing is None or hit.score > existing.score:
                hit_by_id[hit.chunk_id] = hit
        vector_hits = list(hit_by_id.values())

        if not vector_hits:
            return self._fallback_to_sql(
                request,
                start,
                vector_hit_count=0,
                reason="Qdrant returned no matching points",
            )

        chunks = self.source_store.get_source_chunks_by_ids([hit.chunk_id for hit in vector_hits])
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        query_tokens = _tokens(request.query)
        scored: list[tuple[float, SourceChunk]] = []
        vector_score_by_id = {hit.chunk_id: hit.score for hit in vector_hits}

        for hit in vector_hits:
            chunk = chunk_by_id.get(hit.chunk_id)
            if not chunk:
                continue
            keyword_score = _score_chunk(chunk, request, query_tokens)
            if keyword_score <= 0:
                continue
            scored.append((vector_score_by_id.get(chunk.chunk_id, 0.0) + keyword_score, chunk))

        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        diag = RetrievalDiagnostics(
            query_text=request.query,
            filters=vector_filters,
            sql_chunk_count=len(chunks),
            vector_hit_count=len(vector_hits),
            vector_provider=settings.vector_provider,
            fallback_used=False,
            fallback_reason=None,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
        top = _diversify_ranked(ranked)
        # Guarantee the district legend is present even when the keyword gate or
        # the top_n cutoff would otherwise drop it (it rarely shares tokens with a
        # use-specific request), so a generic prompt can map district name->code.
        top = _ensure_district_definitions(top, district_hits, chunk_by_id, vector_score_by_id)
        # Guarantee the permitted-use table row for the inferred use survives: it
        # is the primary evidence for the decision but shares a section_ref with
        # the chapter narrative, so the per-section diversify cap can drop it.
        top = _ensure_use_table_rows(top, ranked)
        return RetrievalProviderResult(
            citations=[
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
                    score=round(score, 4),
                    metadata=chunk.metadata,
                )
                for score, chunk in top
            ],
            chunks=[chunk for _, chunk in top],
            diagnostics=diag,
        )

    def _fallback_to_sql(
        self,
        request: RetrievalProviderRequest,
        start: float,
        *,
        vector_hit_count: int | None,
        reason: str,
    ) -> RetrievalProviderResult:
        settings = get_settings()
        chunks = self.source_store.list_source_chunks_filtered(
            jurisdiction_id=request.jurisdiction_id,
            district=request.district,
            use=request.inferred_use,
        )
        sql_result = self._sql_keyword_retrieve(request, chunks, start)
        return RetrievalProviderResult(
            citations=sql_result.citations,
            chunks=sql_result.chunks,
            diagnostics=RetrievalDiagnostics(
                query_text=request.query,
                filters={
                    "jurisdiction_id": request.jurisdiction_id,
                    "district": request.district,
                    "use": request.inferred_use,
                },
                sql_chunk_count=len(chunks),
                vector_hit_count=vector_hit_count,
                vector_provider=settings.vector_provider,
                fallback_used=True,
                fallback_reason=reason,
                elapsed_ms=(time.monotonic() - start) * 1000,
            ),
        )


def _ensure_district_definitions(
    top: list[tuple[float, "SourceChunk"]],
    district_hits: list,
    chunk_by_id: dict[str, "SourceChunk"],
    vector_score_by_id: dict[str, float],
    *,
    reserve: int = 2,
) -> list[tuple[float, "SourceChunk"]]:
    """Append the best district-definition chunk(s) when not already included.

    Permitted-use tables list districts by code (DD, NC, RC4, ...) while a request
    names the district in prose ("Downtown District", "regional commercial
    corridor"). A jurisdiction-neutral analysis prompt can only bridge name->code
    when the district-definitions section is in the excerpts. That section seldom
    shares tokens with a use-specific request, so the keyword gate and the top_n
    cutoff tend to drop it; reserve up to ``reserve`` slots for it here, ranked by
    the district-definitions query. Generic (no hard-coded chapter/section names).
    """
    if not district_hits:
        return top
    existing = {chunk.chunk_id for _, chunk in top}
    augmented = list(top)
    added = 0
    for hit in district_hits:
        if added >= reserve:
            break
        chunk = chunk_by_id.get(hit.chunk_id)
        if chunk is None or chunk.chunk_id in existing:
            continue
        score = vector_score_by_id.get(chunk.chunk_id, getattr(hit, "score", 0.0))
        augmented.append((score, chunk))
        existing.add(chunk.chunk_id)
        added += 1
    return augmented


def _ensure_use_table_rows(
    top: list[tuple[float, "SourceChunk"]],
    ranked: list[tuple[float, "SourceChunk"]],
    *,
    reserve: int = 2,
) -> list[tuple[float, "SourceChunk"]]:
    """Guarantee the permitted-use table row(s) for the inferred use are present.

    The permitted-use matrix is the primary evidence for a use decision, yet it is
    typically split across many chunks that share one section_ref with the
    chapter's narrative and additional-use-regulation text. The per-section
    diversify cap can therefore drop the matching table row, leaving only narrative
    conditions — which makes a use look merely "conditional" when the table in fact
    does not permit it in the identified district at all. Reserve up to ``reserve``
    slots for the highest-ranked permitted-use-table chunks (tagged via the
    ingestion-level ``principal_uses`` use marker). Generic across jurisdictions.
    """
    present = sum(1 for _, chunk in top if "principal_uses" in chunk.uses)
    need = reserve - present
    if need <= 0:
        return top
    existing = {chunk.chunk_id for _, chunk in top}
    augmented = list(top)
    for score, chunk in ranked:
        if need <= 0:
            break
        if "principal_uses" not in chunk.uses or chunk.chunk_id in existing:
            continue
        augmented.append((score, chunk))
        existing.add(chunk.chunk_id)
        need -= 1
    return augmented


def _diversify_ranked(
    ranked: list[tuple[float, "SourceChunk"]],
    *,
    top_n: int = 8,
    max_per_section: int = 2,
) -> list[tuple[float, "SourceChunk"]]:
    """Return up to top_n chunks, capping at max_per_section per section_ref.

    Prevents a single high-scoring chapter from crowding out procedural or
    classification chapters that are needed for conditional/restricted decisions.
    Chunks without a section_ref are each counted as their own group so they
    are never unfairly penalised.
    """
    section_counts: dict[str, int] = {}
    result: list[tuple[float, "SourceChunk"]] = []
    for score, chunk in ranked:
        key = chunk.section_ref or chunk.chunk_id
        if section_counts.get(key, 0) < max_per_section:
            result.append((score, chunk))
            section_counts[key] = section_counts.get(key, 0) + 1
        if len(result) >= top_n:
            break
    return result


def _tokens(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


def _score_chunk(
    chunk: SourceChunk,
    request: RetrievalProviderRequest,
    query_tokens: set[str],
) -> float:
    if (
        request.jurisdiction_id
        and chunk.jurisdiction_id
        and chunk.jurisdiction_id not in {request.jurisdiction_id, "*"}
    ):
        return 0.0

    score = 0.0
    # Exact district matches rank ahead of the "unknown" wildcard, but unknown
    # still receives enough credit to preserve recall for unclassified sections.
    if request.district == "unknown":
        score += 1.0
    elif request.district in chunk.districts or "*" in chunk.districts:
        score += 2.0
    elif "unknown" in chunk.districts:
        score += 1.2
    if request.inferred_use in chunk.uses or "general" in chunk.uses:
        score += 2.0

    chunk_tokens = _tokens(chunk.chunk_text)
    if query_tokens and chunk_tokens:
        score += len(query_tokens.intersection(chunk_tokens)) / max(1, len(query_tokens))

    return score


def _build_retrieval_cache_key(request: RetrievalProviderRequest, source_index_version: str) -> str:
    """Produce a stable cache key for a retrieval request.

    The key incorporates all parameters that affect the result so that
    changing any of them produces a different cache entry.
    """
    raw = json.dumps(
        {
            "jurisdiction_id": request.jurisdiction_id,
            "district": request.district,
            "inferred_use": request.inferred_use,
            "query": request.query,
            "source_index_version": source_index_version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _source_index_version(source_store: SQLiteStore, configured_version: str) -> str:
    """Return a content-derived source index version for cache keys."""
    chunks = source_store.list_source_chunks()
    if not chunks:
        return configured_version
    raw = json.dumps(
        [
            {
                "chunk_id": chunk.chunk_id,
                "source_text_hash": chunk.source_text_hash,
                "source_version": chunk.source_version,
                "districts": sorted(chunk.districts),
                "uses": sorted(chunk.uses),
            }
            for chunk in sorted(chunks, key=lambda item: item.chunk_id)
        ],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
