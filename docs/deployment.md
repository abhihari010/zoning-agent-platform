# Deployment Notes

## Runtime Shape

The production path is a single FastAPI zoning pipeline behind the React client:

- `AI_PROVIDER=deterministic`, `local`, `openai`, or `watsonx`
- `RAG_PROVIDER=source_registry` or `hybrid_local`
- `EMBEDDING_PROVIDER=none`, `local`, or `openai`
- `VECTOR_PROVIDER=none` or `chroma`

For the public beta, prefer `RAG_PROVIDER=hybrid_local`, `EMBEDDING_PROVIDER=local`, and
`VECTOR_PROVIDER=none`. SQL source chunks are the production retrieval baseline until vector
persistence is deliberately added. Chroma remains a rebuildable local/staging option.

## Required Environment

- `DATABASE_URL`: production database connection string. Use `ZONING_DB_PATH` only for local SQLite.
- `APP_ENV=production`: enables strict production configuration validation.
- `GOOGLE_MAPS_API_KEY`: required for live address validation and autocomplete.
- `CORS_ALLOW_ORIGINS`: set to the deployed frontend origin.
- `AUTH_PROVIDER=supabase`, `AUTH_REQUIRED=true`, `SUPABASE_PROJECT_URL`, and
  `SUPABASE_JWT_SECRET`: required for public-beta user auth.
- `BETA_ACCESS_KEYS`: temporary comma-separated `label:key` entries for QA/migration access only.
- `ADMIN_ACCESS_KEY`: enables source write, import, and reindex routes.
- `STARTUP_REINDEX_ENABLED=true`: warms and repairs the source index on API startup.

Optional provider keys:

- `OPENAI_API_KEY` when using OpenAI analysis or embeddings.
- `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_MODEL_ID`, and
  `WATSONX_VECTOR_INDEX_ID` only when selecting watsonx providers.

If the database password contains reserved URL characters such as `@`, `:`, `/`, `?`, or `#`,
percent-encode them in `DATABASE_URL`. For example, `@` must become `%40`. Otherwise the database
driver can parse part of the password as the host and fail with an error like `failed to resolve
host '...@aws-...pooler.supabase.com'`.

## Startup Readiness

The Docker image runs `alembic upgrade head` before starting Uvicorn. After migrations complete, the
API calls `prepare_source_index_for_startup()`:

1. Seed bundled source records when the source registry is empty or the configured registry version
   has not been applied.
2. Rebuild stale or missing source chunks.
3. Sync the vector index when `VECTOR_PROVIDER` is enabled. Public beta should leave it disabled.
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
