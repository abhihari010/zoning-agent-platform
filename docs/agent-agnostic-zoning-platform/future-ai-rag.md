# Future AI and Vector RAG Expansion

## Current Status

The app now has the first production-safe seams for future AI/RAG expansion:

- optional OpenAI analysis provider selected with `AI_PROVIDER=openai`
- embedding provider interface selected with `EMBEDDING_PROVIDER=none|local|openai`
- hybrid local retrieval selected with `RAG_PROVIDER=hybrid_local`
- chunked local source indexing through `/api/v1/ingestion/reindex`

The app still does not include:

- embeddings
- vector search
- hybrid keyword/vector retrieval
- Anthropic, Ollama, or other non-WatsonX LLM providers
- production-grade vector persistence beyond local chunk retrieval

The current defaults remain intentionally local and deterministic:

- `AI_PROVIDER=deterministic`
- `RAG_PROVIDER=source_registry`
- `EMBEDDING_PROVIDER=none`

WatsonX remains available only as an optional legacy adapter.

## Goal

Add a real provider-agnostic AI and RAG layer that can use external LLMs and embeddings while preserving the current safety guarantees: citation-first answers, clear confidence handling, offline tests, and deterministic fallback behavior.

## Recommended Implementation Order

### 1. Embedding Provider Interface

Add an embedding interface under `apps/api/app/ai/`, similar to the existing analysis and retrieval providers.

Suggested shape:

```python
class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
```

Add settings:

```text
EMBEDDING_PROVIDER=none|openai|local
EMBEDDING_MODEL=...
```

Default should remain `none` so tests and local development do not require API keys.

### 2. Chunked Document Index

Before vector search, create a stable local chunk index.

Requirements:

- stable chunk IDs
- source ID
- jurisdiction ID when available
- district tags
- use tags
- section reference
- URL
- effective date
- source text hash
- chunk text

This belongs near:

- `apps/api/app/ingestion.py`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`
- `apps/api/app/ai/source_registry_retriever.py`

### 3. Local Vector Store Adapter

Add vector storage behind a retrieval interface. Start with one implementation only.

Recommended first choice:

- SQLite-backed local table for chunks and embeddings, if practical.

Alternative later choices:

- ChromaDB for local prototyping.
- Postgres/pgvector for production.

Do not make the frontend depend on which vector store is selected.

### 4. Hybrid Retrieval Provider

Add a retrieval provider that combines:

- metadata filtering
- keyword search
- vector similarity search

Suggested setting:

```text
RAG_PROVIDER=source_registry|hybrid_local|watsonx
```

Acceptance behavior:

- If vector search fails, fall back to keyword/source registry retrieval.
- If no citations are found, analysis must remain `unknown` or `low_confidence`.
- Retrieval output must still be `SourceCitation` compatible.

### 5. External LLM Provider

Add a non-WatsonX analysis provider after retrieval is grounded.

Recommended first provider:

- OpenAI, because it has strong structured-output support and is easy to test behind mocks.

Possible later providers:

- Anthropic
- Ollama/local models
- Vercel AI Gateway if deployment/provider routing becomes important

Suggested setting:

```text
AI_PROVIDER=deterministic|openai|watsonx|local
AI_MODEL=...
```

Implementation requirements:

- Model responses must validate into `AnalysisProviderResult`.
- Invalid JSON or schema mismatch must fall back safely.
- No model provider should be allowed to create unsupported citations.
- Model output must not override citation coverage checks.

## Safety Requirements

- Tests must pass with no external API keys.
- External provider tests must use mocks.
- Missing citations must never produce a high-confidence positive zoning decision.
- Provider errors must become warnings plus fallback behavior.
- All new provider settings must be documented in `.env.example` and `README.md`.
- Implementation specs should verify current official provider docs before pinning model names or SDK versions.

## Suggested Future Tickets

1. Persist embeddings for indexed chunks.
2. Add vector similarity storage/querying beyond in-memory local ranking.
3. Add mocked provider tests for additional external providers.
4. Add richer source/jurisdiction metadata filters to hybrid retrieval.
5. Add admin controls for provider/index diagnostics.

## Out of Scope For The Next Immediate Step

- Multi-jurisdiction source crawling.
- Production deployment changes.
- User accounts or billing.
- Legal review automation.
- Replacing deterministic fallback.

## Handoff Note

When continuing in a new chat, start from:

- `docs/agent-agnostic-zoning-platform/spec.md`
- `docs/agent-agnostic-zoning-platform/plan.md`
- `docs/agent-agnostic-zoning-platform/handoff.md`
- this file

Recommended next implementation after Phase 1:

1. complete issue #7 and #8 if still open
2. implement issue #9 for local indexing
3. then split the work in this file into new issues
