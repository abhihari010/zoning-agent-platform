# Zoning Review Platform

Monorepo for a zoning feasibility assistant that helps a resident or business owner ask, in plain English, whether a project is likely allowed at a property and what permits or reviews come next.

The current build uses a React frontend and a FastAPI backend with a single zoning orchestrator that runs a staged review pipeline:

1. `Understand Project`: interprets the project description and flags missing details.
2. `Resolve Property`: normalizes location context, jurisdiction, and district metadata.
3. `Retrieve Sources`: retrieves district-relevant municipal source excerpts.
4. `Analyze Compliance`: synthesizes feasibility from structured facts and retrieved evidence.
5. `Generate Checklist`: formats permit steps, warnings, citations, and the user-facing checklist.

The frontend is designed to connect those stages together visibly for the user, including:

- intake form for project description and address
- progress tracker for each pipeline stage
- clarification modal when intake needs more information
- feasibility dashboard with citations and warnings
- downloadable permit checklist
- prominent legal disclaimer

## Current State

The product is live and taking paid subscriptions.

- **24 supported jurisdictions** (23 Virginia + Franklin, TN), all data-driven — see `apps/api/app/data/jurisdictions.json`.
- **Auth** is Supabase JWT. `ADMIN_ACCESS_KEY` separately gates source-admin writes.
- **Billing** is Stripe subscriptions: a free tier and a Pro tier, with per-user daily analysis caps.
- **Production providers**: Groq for analysis (with failover to Cerebras and OpenRouter), `hybrid_local` retrieval, Gemini embeddings, and a Qdrant vector index.
- **Data**: Render Postgres is the source of truth. Supabase is retained for Auth only.

Local development needs none of that. The default mode is deterministic analysis with source-registry retrieval and runs with zero external AI credentials; only Google Maps is needed for live address intake.

## Provider-Agnostic Operation

The backend routes analysis, retrieval, and embeddings through provider-neutral interfaces in `apps/api/app/ai/`, resolved at request time by `apps/api/app/ai/registry.py`. The same orchestrator runs against deterministic logic, Groq, any OpenAI-compatible endpoint, or a local model, so swapping providers is a config change rather than a code change.

### Guiding Principles

- Keep zoning answers citation-first. Every recommendation should link back to source text, effective dates, jurisdiction, and section references.
- Treat AI output as assisted drafting, not legal authority. The app should always explain uncertainty and route low-confidence cases to human review.
- Separate the orchestrated workflow from the model provider. The same staged pipeline should work with hosted providers, local models, or deterministic fallback logic.
- Make geography configurable. Blacksburg was the first supported jurisdiction, not a hard-coded boundary.
- Design for expansion through source data, not one-off conditionals. Adding a city should mostly mean adding jurisdiction metadata, parcel/district mapping, and ordinance documents.

### Pipeline Tools

1. `Intake Tool`
   - Understands the user's project description.
   - Extracts use type, construction scope, business operations, missing details, and risk factors.
   - Produces follow-up questions when the project is underspecified.

2. `Jurisdiction & Parcel Tool`
   - Normalizes the address.
   - Determines jurisdiction, parcel context, zoning district, overlays, and special areas when available.
   - Jurisdiction support is data-driven; there is no hard-coded city restriction.

3. `Retrieval Tool`
   - Searches the local zoning knowledge base.
   - Filters by jurisdiction, district, use, overlay, source type, and effective date.
   - Returns cited excerpts with enough metadata for auditability.

4. `Compliance Tool`
   - Synthesizes feasibility, likely permit path, review triggers, warnings, and next steps.
   - Must only make claims that can be traced to retrieved source excerpts or clearly marked assumptions.

5. `Review & Feedback Layer`
   - Shows confidence, source coverage, unresolved questions, and user feedback.
   - Stores traces so bad answers can be debugged and improved.

### What Shipped

The staged pipeline, the provider boundary, real document ingestion, multi-jurisdiction
support, and the trust/quality work are all implemented and running in production.

**Provider boundary.** Analysis and retrieval run through provider-neutral interfaces in
`apps/api/app/ai/`, and `ZoningOrchestrator` coordinates the staged review through tool
modules under `apps/api/app/tools/`. `apps/api/app/services.py` remains a compatibility
facade for older API routes and tests.

Implemented provider settings:

- `AI_PROVIDER=deterministic|openai|groq|cerebras|openrouter|local` (default `deterministic`)
- `RAG_PROVIDER=source_registry|hybrid_local` (default `source_registry`)
- `EMBEDDING_PROVIDER=none|local|openai|gemini` (default `none`)
- `VECTOR_PROVIDER=none|qdrant` (default `none`)

Analysis providers can be chained for resilience. `AI_PROVIDER_FALLBACKS` takes an ordered
comma-separated list; when the primary provider exhausts its retries, each fallback is tried
in turn before the request degrades to deterministic analysis. A fallback with no API key
configured is skipped rather than failing the chain. The eval gate never sets this, so
accuracy runs always execute against a single pinned provider for reproducibility.

**Retrieval.** SQL-backed source/chunk records are the durable source of truth; the vector
index is rebuildable state selected with `VECTOR_PROVIDER=qdrant`. `POST /api/v1/ingestion/reindex`
computes embeddings and syncs vectors, and `hybrid_local` combines vector search with keyword
scoring and metadata filters, falling back to SQL if the vector store is unavailable. The
vector index can be deleted and rebuilt from SQL at any time.

**Jurisdictions.** 24 jurisdictions are publicly supported. Adding one means adding
jurisdiction metadata, district mapping rules, and a source pack under
`apps/api/app/data/source_packs/` — not code. The app distinguishes "valid address,
unsupported jurisdiction" from "invalid address", and the UI shows which jurisdiction was analyzed.

**Trust and quality.** The compliance step returns structured JSON validated with Pydantic.
Citation IDs the model invents are stripped, and confidence is capped when no valid citation
survives. Traces record prompt inputs, retrieval filters, source IDs, and the resolved provider
name. An offline eval gate scores golden scenarios per jurisdiction and blocks regressions in CI.

The key invariant throughout: **no citations means no verdict.** If retrieval returns nothing,
the orchestrator returns `unknown` / low-confidence and recommends human planning review. It
never synthesizes a zoning conclusion from an empty evidence set.

### Roadmap

- Broaden jurisdiction coverage beyond Virginia; `docs/handoff-nationwide-expansion.md` is the living plan.
- Add an evidence viewer with filters by source, section, district, and confidence.
- Add document version history and source health checks to the admin area.
- Add saved-project comparison views.

Reference docs:

- `docs/PROJECT-STATUS.md` — current state and next steps
- `docs/single-orchestrator-architecture.md` — orchestrator design
- `docs/production-readiness/runbook.md` — operational runbook

## Structure

- `apps/web`: React + TypeScript + Vite frontend with Tailwind CSS
- `apps/api`: FastAPI backend
- `packages/shared-schema`: Shared TypeScript contracts
- `services/ingestion`: Source-seeding helpers and local documents for the ingestion pipeline

## Quick Start

### Web

1. `npm install`
2. `npm run dev:web`
3. `npm run build:web`

### API

1. `cd apps/api`
2. `python -m venv .venv`
3. `.venv\\Scripts\\activate`
4. `pip install -e .[dev]`
5. Optional: from the repo root, copy `.env.example` to `.env` if you want persistent local settings
6. `uvicorn app.main:app --reload --port 8000`

The default backend provider mode needs no AI credentials at all:

- `AI_PROVIDER=deterministic`
- `RAG_PROVIDER=source_registry`

Google Maps is still required for live address intake and suggestions. Backend tests can run without a `.env` file because they mock external calls.

Set environment variables before starting the API when needed:

- `GOOGLE_MAPS_API_KEY`: required Google Maps API key with Geocoding and Places enabled
- `GOOGLE_MAPS_TIMEOUT_SECONDS`: optional timeout (default `8`)
- `DATABASE_URL`: optional SQLAlchemy-compatible database URL. Staging and production must set this to Postgres.
- `ZONING_DB_PATH`: optional SQLite database path for local fallback only (default `apps/api/app/data/app.sqlite3`)
- `AUTH_PROVIDER`: `supabase` to require Supabase JWT auth, or unset/`disabled` for local development
- `AUTH_REQUIRED`: when `true`, every `/api/v1/*` request needs a valid bearer token
- `SUPABASE_PROJECT_URL`: Supabase project URL; also used to verify the JWT issuer and fetch JWKS for ES256 tokens
- `SUPABASE_ANON_KEY`: sent as the `apikey` header when fetching JWKS
- `SUPABASE_JWT_SECRET`: fallback for HS256 tokens; ES256 (the current default) does not need it
- `ADMIN_ACCESS_KEY`: optional source-admin key. When set, `POST /api/v1/ingestion/sources`, `POST /api/v1/ingestion/reindex`, and `POST /api/v1/ingestion/import-local-docs` require `X-Admin-Access-Key`.
- `ADMIN_USER_EMAILS`: comma-separated emails granted the `admin` role on login
- `AI_PROVIDER`: optional analysis provider (`deterministic`, `openai`, `groq`, `cerebras`, `openrouter`, or `local`, default `deterministic`)
- `AI_PROVIDER_FALLBACKS`: optional ordered comma-separated fallback providers tried when the primary fails, for example `cerebras,openrouter`. Empty disables failover.
- `RAG_PROVIDER`: optional retrieval provider (`source_registry` or `hybrid_local`, default `source_registry`)
- `EMBEDDING_PROVIDER`: optional embedding provider (`none`, `local`, `openai`, or `gemini`, default `none`)
- `EMBEDDING_MODEL`: model name used when `EMBEDDING_PROVIDER=openai`
- `VECTOR_PROVIDER`: optional vector index provider (`none` or `qdrant`, default `none`; use `qdrant` with `RAG_PROVIDER=hybrid_local`)
- `QDRANT_URL`: Qdrant cluster URL, required when `VECTOR_PROVIDER=qdrant`
- `QDRANT_API_KEY`: Qdrant API key
- `QDRANT_COLLECTION`: Qdrant collection name (default `zoning_source_chunks`)
- `STARTUP_REINDEX_ENABLED`: whether to warm/repair the source index during API startup. Must stay `false` in production — re-embedding the corpus at boot blocks the platform port scan.
- `GROQ_API_KEY`: required when `AI_PROVIDER=groq`
- `GROQ_MODEL`: model name used when `AI_PROVIDER=groq` (default `llama-3.3-70b-versatile`)
- `GEMINI_API_KEY`: required when `EMBEDDING_PROVIDER=gemini`
- `GEMINI_EMBEDDING_MODEL`: embedding model used when `EMBEDDING_PROVIDER=gemini` (default `gemini-embedding-001`)
- `OPENAI_API_KEY`: required when `AI_PROVIDER=openai` or `EMBEDDING_PROVIDER=openai`
- `OPENAI_MODEL`: model name used when `AI_PROVIDER=openai`
- `OPENAI_BASE_URL`: optional OpenAI-compatible API base URL
- `OPENAI_TIMEOUT_SECONDS`: optional timeout for OpenAI HTTP calls
- `CEREBRAS_API_KEY` / `OPENROUTER_API_KEY`: required to activate those providers, whether as primary or as a fallback
- `LOCAL_MODEL_BASE_URL`, `LOCAL_MODEL_NAME`, `LOCAL_MODEL_TIMEOUT_SECONDS`: used when `AI_PROVIDER=local` against an OpenAI-compatible server such as Ollama, vLLM, or LM Studio
- `BURST_LLM_LIMIT_PER_MIN`: per-IP burst limit on the expensive intake/analyze endpoints
- `DAILY_ANALYSIS_LIMIT_FREE` / `DAILY_ANALYSIS_LIMIT_PRO`: per-user daily analysis caps by subscription tier
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_PRO`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`: subscription billing. Leave empty to keep billing inert.
- `SENTRY_DSN`: optional backend error reporting
- `GOOGLE_DISTRICT_KEYWORD_MAP`: optional JSON mapping used when district cannot be inferred from components, example:
  - `{"downtown":"mixed-use-core","industrial":"industrial-zone"}`
- `IBM_ZONING_DB_PATH`: legacy local fallback for `ZONING_DB_PATH`, still read but deprecated


`.env` loading:

- The API now loads environment values automatically from:
  - repo root `.env`
  - repo root `.env.local`
  - `apps/api/.env`
  - `apps/api/.env.local`
- Recommended setup: keep a single repo-root `.env` based on `.env.example`

District and retrieval data sources:

- `apps/api/app/data/district_rules.json`: district mapping rules from Google components
- `apps/api/app/data/source_registry.json`: source registry used by zoning retrieval/citations

Available API additions:

- `GET /api/v1/address/suggest?query=...`: Google Places autocomplete-backed address suggestions
- `GET /api/v1/ingestion/sources`: list persistent source registry entries
- `POST /api/v1/ingestion/sources`: create or update a source registry entry
- `POST /api/v1/ingestion/reindex`: request source reindex
- `GET /api/v1/ingestion/status`: inspect source count, chunk count, SQL index status, vector index status, and source metadata health
- `POST /api/v1/ingestion/import-local-docs`: parse local `.md`, `.txt`, or `.json` documents into source entries
- `GET /health`: unauthenticated backend health check for deployment platforms

Analysis behavior:

- If no provider variables are set, analysis uses deterministic local logic and retrieval uses the source registry.
- If `AI_PROVIDER=openai`, analysis attempts an OpenAI Responses API structured-output call.
- If `AI_PROVIDER=groq`, analysis calls Groq's OpenAI-compatible endpoint, retrying rate limits with backoff before giving up.
- If `RAG_PROVIDER=hybrid_local`, retrieval ranks indexed chunks with metadata filters, keyword overlap, and vector search when `VECTOR_PROVIDER=qdrant`.
- If the analysis provider fails and `AI_PROVIDER_FALLBACKS` is set, each fallback provider is tried in order.
- If every analysis provider fails, the backend falls back to deterministic analysis and records a warning rather than failing the request.
- If retrieval returns no citations, the backend returns an `unknown` or low-confidence result and recommends human planning review.
- `POST /api/v1/projects/{project_id}/analyze` also accepts `clarification_answers`, allowing the frontend to pause for follow-up questions and re-run the orchestration with added user detail.

Run backend tests:

- `cd apps/api`
- `pytest -q`

Frontend expects backend at `http://localhost:8000`.

## Production Runbook

Detailed operational docs: `docs/production-readiness/runbook.md`.

Deployment shape:

- Vercel hosts the Vite frontend.
- Render hosts the FastAPI backend from `apps/api/Dockerfile`, defined declaratively in `render.yaml`.
- Render Postgres (`zoning-agent-db`) is the source of truth, reached over Render's private network so
  API-to-database traffic is never metered as egress.
- Supabase is retained for Auth only.
- `ZONING_DB_PATH` is local fallback only and must not be set on Render.
- User auth is Supabase JWT. `ADMIN_ACCESS_KEY` separately gates source write/import/reindex routes.

Current deployed targets:

- Frontend: `https://zoning-agent-platform.vercel.app`
- API: `https://zoning-agent-api.onrender.com`

### Deploy API to Render

Render is blueprint-synced: `render.yaml` is the source of truth and a sync resets dashboard drift.
Change service or environment configuration there, not in the dashboard, except for secrets — those
are declared with `sync: false` (name only, no value) and pasted into the dashboard.

Note that saving an environment variable in the Render dashboard does **not** trigger a deploy on its
own. Deploy afterward for the change to take effect.

Production provider configuration lives in `render.yaml`:

- `AI_PROVIDER=groq` with `AI_PROVIDER_FALLBACKS=cerebras,openrouter`
- `RAG_PROVIDER=hybrid_local`
- `EMBEDDING_PROVIDER=gemini`
- `VECTOR_PROVIDER=qdrant`
- `STARTUP_REINDEX_ENABLED=false` — reindexing is an explicit admin action via
  `POST /api/v1/ingestion/reindex`, never a boot-time task. Re-embedding the corpus during startup
  blocks the lifespan long enough for Render's port scan to time out.

Secrets pasted in the dashboard: `DATABASE_URL` is wired automatically from the database resource;
`GROQ_API_KEY`, `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `GOOGLE_MAPS_API_KEY`,
`SUPABASE_*`, `ADMIN_ACCESS_KEY`, `STRIPE_*`, and `SENTRY_DSN`.

If a database password contains reserved URL characters such as `@`, `:`, `/`, `?`, or `#`,
percent-encode them in `DATABASE_URL` — `@` becomes `%40`. Otherwise the driver parses part of the
password as the host. If SQLAlchemy receives a `postgres://` URL, the API normalizes it to
`postgresql+psycopg://` internally. Never commit a real password or full connection string.

The Docker image runs `alembic upgrade head` before starting Uvicorn, so migrations apply on deploy.
To run them manually against a target database:

```powershell
cd apps/api
$env:DATABASE_URL="<connection string from the dashboard>"
alembic upgrade head
```

Restrict the Google Maps key in Google Cloud to the Geocoding and Places APIs. Keep production CORS
locked to `https://zoning-agent-platform.vercel.app`.


### Deploy Web to Vercel

This repo includes a root `vercel.json` for the Vite frontend:

- Build command: `npm run build:web`
- Output directory: `apps/web/dist`
- Install command: `npm install`

Production builds should set the deployed API URL explicitly:

- `VITE_API_URL=https://your-render-api.onrender.com`

Auth is Supabase, so builds also need:

- `VITE_SUPABASE_URL=<Supabase project URL>`
- `VITE_SUPABASE_ANON_KEY=<Supabase anon key>`

Optional: `VITE_SENTRY_DSN` for frontend error reporting.

These are inlined at build time, so changing any `VITE_*` value requires a redeploy to take effect.

To avoid browser CORS failures, set this variable in the API host after Vercel gives you a deployment URL:

- `CORS_ALLOW_ORIGINS=https://zoning-agent-platform.vercel.app`

### Deployed API Smoke Test

Run the smoke scripts after Render deploys, database migrations, or source registry changes. They use only redacted tokens and should never print secrets.

```powershell
$env:PUBLIC_BASE_API_URL="https://zoning-agent-api.onrender.com"
$env:PUBLIC_AUTH_TOKEN="<Supabase smoke user access token>"
$env:PUBLIC_TEST_SUPPORTED_ADDRESS="<supported test address>"
$env:PUBLIC_TEST_UNSUPPORTED_ADDRESS="<valid unsupported-jurisdiction test address>"
python scripts/smoke_public_api.py

python scripts/check_production_config.py --api-url https://zoning-agent-api.onrender.com --web-origin https://zoning-agent-platform.vercel.app
```

The script verifies:

- unauthenticated `GET /health` and `GET /ready`
- missing auth returns `401`
- valid Supabase auth can call `/api/v1/me` and `/api/v1/projects`
- source and chunk counts are nonzero
- supported intake and analysis complete
- citations/evidence are returned after analysis
- feedback can be submitted
- unsupported-jurisdiction intake is distinguishable from supported intake

The supported and unsupported address values should be harmless non-user test addresses; do not use real customer data.

### Release Checklist

1. Confirm GitHub Actions CI is green.
2. Deploy the API and confirm `GET /health` and `GET /ready` return healthy JSON.
3. Run `alembic upgrade head` against the staging or production `DATABASE_URL`.
4. Deploy the web app with Supabase auth env vars and `VITE_API_URL` set to the Render API URL.
5. Confirm `/api/v1/ingestion/status` reports nonzero sources and chunks.
6. Run `python scripts/check_production_config.py`.
7. Run `python scripts/smoke_public_api.py` with the smoke-test environment variables above.
8. Run browser smoke with `E2E_MODE=live`.
9. Roll back by redeploying the previous Render/Vercel deployment and restoring from the database provider's backup/export if needed.
