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

        if settings.vector_provider == "chroma" and self.embedding_provider:
            try:
                result = self._retrieve_with_chroma(request, start)
            except Exception as exc:
                # Chroma failed; fall through to SQL-backed keyword retrieval.
                fallback_reason = str(exc)
                chunks = self.source_store.list_source_chunks_filtered(
                    jurisdiction_id=request.jurisdiction_id,
                    district=request.district,
                    use=request.inferred_use,
                )
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
                        fallback_used=True,
                        fallback_reason=f"Chroma error: {fallback_reason}",
                        elapsed_ms=(time.monotonic() - start) * 1000,
                    ),
                )

        if result is None:
            # No Chroma or no embedding provider; use SQL-backed keyword retrieval.
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
                for score, chunk in ranked[:5]
            ],
            chunks=[chunk for _, chunk in ranked[:5]],
        )

    def _retrieve_with_chroma(
        self,
        request: RetrievalProviderRequest,
        start: float,
    ) -> RetrievalProviderResult | None:
        if not self.embedding_provider:
            return None

        query_embedding = self.embedding_provider.embed(
            EmbeddingProviderRequest(texts=[request.query])
        ).embeddings[0]
        if not query_embedding:
            return None

        from app.rag.vector_store import ChromaVectorStore  # lazy import to avoid circular dependency

        settings = get_settings()
        chroma_filters = {
            "jurisdiction_id": request.jurisdiction_id,
            "district": request.district,
            "use": request.inferred_use,
        }
        vector_hits = ChromaVectorStore().query(
            query_embedding,
            filters=chroma_filters,
            limit=20,
        )

        if not vector_hits:
            diag = RetrievalDiagnostics(
                query_text=request.query,
                filters=chroma_filters,
                sql_chunk_count=0,
                vector_hit_count=0,
                vector_provider=settings.vector_provider,
                fallback_used=False,
                fallback_reason=None,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
            return RetrievalProviderResult(citations=[], chunks=[], diagnostics=diag)

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
            filters=chroma_filters,
            sql_chunk_count=len(chunks),
            vector_hit_count=len(vector_hits),
            vector_provider=settings.vector_provider,
            fallback_used=False,
            fallback_reason=None,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
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
                for score, chunk in ranked[:5]
            ],
            chunks=[chunk for _, chunk in ranked[:5]],
            diagnostics=diag,
        )


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
    if request.district in chunk.districts or "*" in chunk.districts or request.district == "unknown":
        score += 2.0
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
            }
            for chunk in sorted(chunks, key=lambda item: item.chunk_id)
        ],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
