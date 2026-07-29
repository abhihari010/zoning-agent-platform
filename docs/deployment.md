# Deployment Notes

## Runtime Shape

The production path is a single FastAPI zoning pipeline behind the React client:

- `AI_PROVIDER=deterministic`, `local`, `openai`, `groq`, `cerebras`, or `openrouter`
- `RAG_PROVIDER=source_registry` or `hybrid_local`
- `EMBEDDING_PROVIDER=none`, `local`, `openai`, or `gemini`
- `VECTOR_PROVIDER=none` or `qdrant`

Production runs `AI_PROVIDER=groq` with `AI_PROVIDER_FALLBACKS=cerebras,openrouter`,
`RAG_PROVIDER=hybrid_local`, `EMBEDDING_PROVIDER=gemini`, and `VECTOR_PROVIDER=qdrant`.
SQL source chunks remain the durable source of truth; the Qdrant index is rebuildable state
that can be dropped and reconstructed from SQL at any time.

Local development defaults to `deterministic` + `source_registry` and needs no AI credentials.

## Required Environment

- `DATABASE_URL`: production database connection string. Use `ZONING_DB_PATH` only for local SQLite.
- `APP_ENV=production`: enables strict production configuration validation.
- `GOOGLE_MAPS_API_KEY`: required for live address validation and autocomplete.
- `CORS_ALLOW_ORIGINS`: set to the deployed frontend origin.
- `AUTH_PROVIDER=supabase`, `AUTH_REQUIRED=true`, `SUPABASE_PROJECT_URL`, `SUPABASE_ANON_KEY`, and
  `SUPABASE_JWT_SECRET`: required for user auth. `SUPABASE_JWT_SECRET` is only the HS256 fallback;
  ES256 tokens (the current default) are verified via JWKS.
- `ADMIN_ACCESS_KEY`: enables source write, import, and reindex routes.
- `STARTUP_REINDEX_ENABLED=false`: **must stay false in production.** Re-embedding the corpus during
  startup blocks the lifespan long enough for the platform port scan to time out. Reindexing is an
  explicit admin action via `POST /api/v1/ingestion/reindex`.

Optional provider keys:

- `GROQ_API_KEY` when using Groq analysis (the production default).
- `CEREBRAS_API_KEY` and `OPENROUTER_API_KEY` to activate the failover chain. A fallback with no key
  is skipped rather than breaking the chain, so the blueprint can declare them before the keys exist.
- `GEMINI_API_KEY` when using Gemini embeddings.
- `QDRANT_URL` and `QDRANT_API_KEY` when `VECTOR_PROVIDER=qdrant`.
- `OPENAI_API_KEY` when using OpenAI analysis or embeddings.

If the database password contains reserved URL characters such as `@`, `:`, `/`, `?`, or `#`,
percent-encode them in `DATABASE_URL`. For example, `@` must become `%40`. Otherwise the database
driver can parse part of the password as the host and fail with an error like `failed to resolve
host '...@aws-...pooler.supabase.com'`.

## Startup Readiness

The Docker image runs `alembic upgrade head` before starting Uvicorn. After migrations complete, the
API calls `prepare_source_index_for_startup()` — but only when `STARTUP_REINDEX_ENABLED=true`, which
production leaves off:

1. Seed bundled source records when the source registry is empty or the configured registry version
   has not been applied.
2. Rebuild stale or missing source chunks.
3. Sync the vector index when `VECTOR_PROVIDER` is enabled.
4. Audit `source.startup_reindex.completed` with source, chunk, vector, and warning counts.

Startup readiness is fail-soft. If the warmup cannot complete, the API still starts and reports the
issue in `/health` so the deployment platform can surface it.

## Health Checks

Use `GET /health` for public platform liveness checks. It does not require auth and returns the last
known startup/source summary without forcing a deep reindex. Use `GET /ready` for deeper smoke checks.
Readiness returns:

- `status`: `ok` when source chunks are ready, otherwise `warning`
- `source_index_ready`, `source_count`, `chunk_count`
- `vector_provider`, `vector_index_ready`, `vector_count`
- `warnings`

Use `GET /api/v1/ingestion/status` from the admin UI for the full source registry readiness report.

## Release Checklist

1. Run database migrations against the target database.
2. Confirm `/health` returns `status: ok` or a known non-blocking warning.
3. Run `POST /api/v1/ingestion/reindex` with the admin key after source updates.
4. Run the golden scenario tests before promoting a provider or source registry change.
5. Verify a supported jurisdiction and an unsupported jurisdiction in the frontend before launch.
