# CLAUDE.md

## Repository Shape

Monorepo with two deployable apps and a shared schema package:

- `apps/web` — React 18 + TypeScript + Vite + Tailwind frontend (npm workspace `@zoning-agent/web`).
- `apps/api` — FastAPI backend, standalone Python package (`zoning-agent-api`, Python ≥3.11). Not part of the npm workspace.
- `packages/shared-schema` — Shared TypeScript contracts (`@zoning-agent/shared-schema`), workspaced for the web app.
- `services/ingestion` — source-seeding helpers and local documents; the API owns parsing/chunking/indexing.
- `scripts/` — operational Python scripts (smoke tests, config checks, source discovery/validation). Run from repo root.
- `tests/e2e/` — Playwright-based end-to-end smoke test (`public-launch-smoke.mjs`).

See `AGENT.md` for what to exclude from commits (scratch dirs, codex state, etc.).

## Common Commands

### Web (run from repo root unless noted)

- `npm install` — installs all npm workspaces.
- `npm run dev:web` — Vite dev server for the frontend (expects backend at `http://localhost:8000`).
- `npm run build:web` — `tsc -b` then `vite build`. Output goes to `apps/web/dist` (this is what `vercel.json` deploys).
- `npm run typecheck:web` — `tsc --noEmit` for the web app.
- `npm run test:e2e` — runs `tests/e2e/public-launch-smoke.mjs` (Playwright). Honors `E2E_MODE=live` for hitting deployed URLs.

### API (run from `apps/api`)

- `python -m venv .venv && .venv\Scripts\activate` (Windows) / `source .venv/bin/activate` (POSIX).
- `pip install -e .[dev]` — installs the API plus pytest/pytest-mock.
- `uvicorn app.main:app --reload --port 8000` — local dev server.
- `pytest -q` — runs the full backend test suite.
- `pytest tests/test_orchestrator.py -q` — run a single test file. Use `-k name` to filter by test name.
- `alembic upgrade head` — apply DB migrations. Reads `DATABASE_URL` from the environment; falls back to SQLite at `ZONING_DB_PATH` when unset.

Backend tests do not require any external credentials; the deterministic provider mode is the default and external calls are mocked.

### Operational Scripts (from repo root, with the API venv active)

- `python scripts/check_production_config.py --api-url <url> --web-origin <url>` — sanity-checks a deployed API/web pair.
- `python scripts/smoke_public_api.py` — public smoke test driven by `PUBLIC_BASE_API_URL`, `PUBLIC_AUTH_TOKEN`, `PUBLIC_TEST_SUPPORTED_ADDRESS`, `PUBLIC_TEST_UNSUPPORTED_ADDRESS`.
- `scripts/discover_jurisdiction_sources.py`, `validate_source_packs.py`, `check_source_freshness.py`, `check_public_support_candidates.py` — source registry maintenance.

## Architecture

The product is a staged zoning-feasibility pipeline. The backend is intentionally **provider-agnostic**: the same orchestrator runs against deterministic logic, Groq, any OpenAI-compatible endpoint, or a local OpenAI-compatible model. The frontend treats the API as the single integration surface.

### Backend pipeline (apps/api/app)

- `orchestrator/zoning_orchestrator.py` — `ZoningOrchestrator` is the single coordinator. It runs five stages and emits a `PipelineStageReport` per stage so the frontend can show progress.
- `tools/` — each pipeline stage lives here: `intake_tool`, `address_tool`, `parcel_tool`, `jurisdiction_tool`, `compliance_tool`, `citation_tool`, `report_tool`. Tools are pure-ish callables consumed by the orchestrator; do not call AI providers directly from routers.
- `ai/` — provider boundary. `registry.py` resolves analysis/retrieval/embedding providers from settings; `interfaces.py` defines the contracts. Concrete providers: `deterministic_provider`, `openai_provider`, `groq_provider`, `local_model_provider`, and `openai_compatible` (the shared base, which also backs the Cerebras and OpenRouter fallbacks), plus `source_registry_retriever`, `hybrid_local_retriever`, `embedding_provider`, and `gemini_batch_embedding`. `failover_provider.py` chains analysis providers when `AI_PROVIDER_FALLBACKS` is set.
- `rag/vector_store.py` — Qdrant wrapper used when `VECTOR_PROVIDER=qdrant`. SQL remains source of truth; the vector index is rebuildable.
- `services.py` — legacy compatibility facade kept for existing routes/tests. New code should call orchestrator/tools directly, not the facade.
- `routers/api.py` — all `/api/v1/*` endpoints. `main.py` wires CORS, auth dependencies, and includes the router. `/health` and `/ready` are unauthenticated.
- `repositories.py` / `storage.py` / `database.py` — SQLAlchemy 2.x. Production uses Postgres via `DATABASE_URL`; local fallback is SQLite at `ZONING_DB_PATH` (default `apps/api/app/data/app.sqlite3`). The settings layer normalizes `postgres://` → `postgresql+psycopg://` automatically.
- `auth.py` — Supabase JWT auth (`AUTH_PROVIDER=supabase`), verifying ES256 via JWKS with an HS256 fallback. `AUTH_PROVIDER` is otherwise `disabled` for local development. `ADMIN_ACCESS_KEY` separately gates source-admin write endpoints, and `ADMIN_USER_EMAILS` grants the `admin` role on login.
- `jurisdictions.py` / `district_mapping.py` / `data/district_rules.json` / `data/source_registry.json` — jurisdiction support is data-driven; do not hard-code city checks. The address flow distinguishes "valid address, unsupported jurisdiction" from "invalid address".
- `alembic/` — schema migrations. Always add a new revision rather than editing existing ones; run `alembic upgrade head` before deploying.

### Provider modes (settings.py)

- `AI_PROVIDER` ∈ `deterministic` (default) | `openai` | `groq` | `cerebras` | `openrouter` | `local`
- `AI_PROVIDER_FALLBACKS` — ordered CSV of analysis providers tried when the primary fails; empty (default) disables failover. A fallback with no API key is skipped, not fatal. The eval gate never sets this, so accuracy runs stay reproducible against a single pinned provider.
- `RAG_PROVIDER` ∈ `source_registry` (default) | `hybrid_local`
- `EMBEDDING_PROVIDER` ∈ `none` (default) | `local` | `openai` | `gemini`
- `VECTOR_PROVIDER` ∈ `none` (default) | `qdrant` — only meaningful with `hybrid_local`

Production runs `groq` + `cerebras,openrouter` fallbacks, `hybrid_local`, `gemini` embeddings, and `qdrant`.

Key invariant: if retrieval returns no citations, the orchestrator must return `unknown` / low-confidence — it must not synthesize a zoning conclusion. Analysis-provider failures fall back to deterministic analysis and add a warning rather than failing the request. Tests rely on both.

`.env` is loaded from the repo root (`.env`, `.env.local`) and from `apps/api/.env(.local)`. Prefer a single repo-root `.env` based on `.env.example`.

### Frontend (apps/web/src)

- `App.tsx` is the assembly point; feature-specific UI lives in `features/{admin,assistant,auth,landing,projects,results}` and reusable hooks in `hooks/` (`useSupabaseAuth`, `useAddressAutocomplete`, `useCheckout`, `useCoverage`, `useFeedback`, `useLegalAck`, `useSourcesAdmin`, `useTrace`).
- `api.ts` is the single API client; it injects the Supabase auth header and points at `VITE_API_URL` (defaults to `http://localhost:8000`).
- Shared response/intake types live in `packages/shared-schema` — keep TS contracts in sync with the Pydantic models in `apps/api/app/models.py`.

### Deployment topology

- Frontend → Vercel, configured by root `vercel.json` (build `npm run build:web`, output `apps/web/dist`).
- API → Render, Docker build from `apps/api/Dockerfile` (see `render.yaml`). Health check path `/health`. Do not depend on a Render disk — Postgres is the source of truth.
- Staging DB is Supabase via the session pooler URL; production must be a paid DB plan with backups before real users land. Postgres password lives only in dashboards; do not commit it.
- CORS is locked to the deployed Vercel origin via `CORS_ALLOW_ORIGINS` on the API host.

## Working in This Repo

- Follow `AGENT.md`: tie branches/PRs to GitHub issue numbers, keep changes small, and check open issues / latest handoff in `docs/` (especially `docs/PROJECT-STATUS.md` and `docs/single-orchestrator-architecture.md`) before starting new work.
- When adding a new provider, register it in `app/ai/registry.py` and cover it with `tests/test_ai_providers.py`-style tests; existing tests assume the deterministic path is the default.
- When adding a jurisdiction, extend `data/source_registry.json` and the jurisdiction/district mappings — do not add Blacksburg-style hard-coded checks.
- When changing API shapes, update both `apps/api/app/models.py` and `packages/shared-schema/src/index.ts`, and check `apps/web/src/api.ts` callers.

## gstack

Use `/browse` from gstack for all web browsing tasks. Never use `mcp__claude-in-chrome__*` tools.
