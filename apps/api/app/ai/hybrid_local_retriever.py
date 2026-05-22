from __future__ import annotations

import re

from app.ai.embedding_provider import cosine_similarity
from app.ai.interfaces import (
    EmbeddingProvider,
    EmbeddingProviderRequest,
    RetrievalProviderRequest,
    RetrievalProviderResult,
)
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider, ensure_source_index_ready
from app.models import SourceChunk, SourceCitation
from app.storage import SQLiteStore, store


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


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
        ensure_source_index_ready(self.source_store)
        chunks = self.source_store.list_source_chunks()
        if not chunks:
            return SourceRegistryRetrievalProvider(self.source_store).retrieve(request)

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
        ranked = [chunk for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]

        return RetrievalProviderResult(
            citations=[
                SourceCitation(
                    source_id=chunk.source_id,
                    title=chunk.title,
                    excerpt=chunk.chunk_text,
                    section_ref=chunk.section_ref,
                    url=chunk.url,
                    effective_date=chunk.effective_date,
                )
                for chunk in ranked[:5]
            ]
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
