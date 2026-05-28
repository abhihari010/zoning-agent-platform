# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Shape

Monorepo with two deployable apps and a shared schema package:

- `apps/web` — React 18 + TypeScript + Vite + Tailwind frontend (npm workspace `@zoning-agent/web`).
- `apps/api` — FastAPI backend, standalone Python package (`zoning-agent-api`, Python ≥3.11). Not part of the npm workspace.
- `packages/shared-schema` — Shared TypeScript contracts (`@zoning-agent/shared-schema`), workspaced for the web app.
- `services/ingestion` — placeholder for a future document ingestion service.
- `scripts/` — operational Python scripts (smoke tests, config checks, source discovery/validation). Run from repo root.
- `tests/e2e/` — Playwright-based end-to-end smoke test (`public-launch-smoke.mjs`).

`AGENT.md` rule: `.agents/`, `.codex/`, `skills-lock.json`, and the many `.tmp-*` directories at the repo root are local/private scratch state and must stay out of commits.

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
- `python scripts/smoke_public_api.py` — public-beta smoke test driven by `PUBLIC_BASE_API_URL`, `PUBLIC_AUTH_TOKEN`, `PUBLIC_TEST_SUPPORTED_ADDRESS`, `PUBLIC_TEST_UNSUPPORTED_ADDRESS`.
- `scripts/smoke_beta_api.py` is the legacy beta-key variant — keep it only while invite keys still exist.
- `scripts/discover_jurisdiction_sources.py`, `validate_source_packs.py`, `check_source_freshness.py`, `check_public_support_candidates.py` — source registry maintenance.

CI lives in `.github/workflows/` (`ci.yml`, `production-smoke.yml`, `source-freshness.yml`).

## Architecture

The product is a staged zoning-feasibility pipeline. The backend is intentionally **provider-agnostic**: the same orchestrator runs against deterministic logic, an OpenAI-compatible endpoint, a local OpenAI-compatible model, or legacy IBM watsonx. The frontend treats the API as the single integration surface.

### Backend pipeline (apps/api/app)

- `orchestrator/zoning_orchestrator.py` — `ZoningOrchestrator` is the single coordinator. It runs five stages and emits a `PipelineStageReport` per stage so the frontend can show progress.
- `tools/` — each pipeline stage lives here: `intake_tool`, `address_tool`, `parcel_tool`, `jurisdiction_tool`, `compliance_tool`, `citation_tool`, `report_tool`. Tools are pure-ish callables consumed by the orchestrator; do not call AI providers directly from routers.
- `ai/` — provider boundary. `registry.py` resolves analysis/retrieval/embedding providers from settings; `interfaces.py` defines the contracts. Concrete providers: `deterministic_provider`, `openai_provider`, `local_model_provider`, `watsonx_provider`, plus `source_registry_retriever` and `hybrid_local_retriever`.
- `rag/vector_store.py` — embedded ChromaDB wrapper used when `VECTOR_PROVIDER=chroma`. SQL remains source of truth; Chroma is a rebuildable index.
- `services.py` — legacy compatibility facade kept for existing routes/tests. New code should call orchestrator/tools directly, not the facade.
- `routers/api.py` — all `/api/v1/*` endpoints. `main.py` wires CORS, auth dependencies, and includes the router. `/health` and `/ready` are unauthenticated.
- `repositories.py` / `storage.py` / `database.py` — SQLAlchemy 2.x. Production uses Postgres via `DATABASE_URL`; local fallback is SQLite at `ZONING_DB_PATH` (default `apps/api/app/data/app.sqlite3`). The settings layer normalizes `postgres://` → `postgresql+psycopg://` automatically.
- `auth.py` — two auth modes coexist: a private-beta header gate (`X-Beta-Access-Key` matched against `BETA_ACCESS_KEY` and labeled `BETA_ACCESS_KEYS`) and Supabase JWT auth for the public beta. `ADMIN_ACCESS_KEY` separately gates source-admin write endpoints.
- `jurisdictions.py` / `district_mapping.py` / `data/district_rules.json` / `data/source_registry.json` — jurisdiction support is data-driven; do not hard-code city checks. The address flow distinguishes "valid address, unsupported jurisdiction" from "invalid address".
- `alembic/` — schema migrations. Always add a new revision rather than editing existing ones; run `alembic upgrade head` before deploying.

### Provider modes (settings.py)

- `AI_PROVIDER` ∈ `deterministic` (default) | `openai` | `local` | `watsonx`
- `RAG_PROVIDER` ∈ `source_registry` (default) | `hybrid_local` | `watsonx`
- `EMBEDDING_PROVIDER` ∈ `none` (default) | `local` | `openai`
- `VECTOR_PROVIDER` ∈ `none` (default) | `chroma` — only meaningful with `hybrid_local`

Key invariant: if retrieval returns no citations, the orchestrator must return `unknown` / low-confidence — it must not synthesize a zoning conclusion. Watsonx failures fall back to deterministic analysis and add a warning rather than failing the request. Tests rely on this.

`.env` is loaded from the repo root (`.env`, `.env.local`) and from `apps/api/.env(.local)`. Prefer a single repo-root `.env` based on `.env.example`.

### Frontend (apps/web/src)

- `App.tsx` is the assembly point; feature-specific UI lives in `features/{admin,assistant,auth,landing,projects,results}` and reusable hooks in `hooks/` (`useBetaAccess`, `useSupabaseAuth`, `useAddressAutocomplete`, `useCoverage`, `useFeedback`, `useSourcesAdmin`, `useTrace`).
- `api.ts` is the single API client; it injects beta and/or Supabase auth headers and points at `VITE_API_URL` (defaults to `http://localhost:8000`).
- Shared response/intake types live in `packages/shared-schema` — keep TS contracts in sync with the Pydantic models in `apps/api/app/models.py`.

### Deployment topology

- Frontend → Vercel, configured by root `vercel.json` (build `npm run build:web`, output `apps/web/dist`).
- API → Render, Docker build from `apps/api/Dockerfile` (see `render.yaml`). Health check path `/health`. Do not depend on a Render disk — Postgres is the source of truth.
- Staging DB is Supabase via the session pooler URL; production must be a paid DB plan with backups before real users land. Postgres password lives only in dashboards; do not commit it.
- CORS is locked to the deployed Vercel origin via `CORS_ALLOW_ORIGINS` on the API host.

## Working in This Repo

- Follow `AGENT.md`: tie branches/PRs to GitHub issue numbers, keep changes small, and check open issues / latest handoff in `docs/` (especially `docs/production-beta-hardening/handoff.md` and `docs/single-orchestrator-architecture.md`) before starting new work.
- When adding a new provider, register it in `app/ai/registry.py` and cover it with `tests/test_ai_providers.py`-style tests; existing tests assume the deterministic path is the default.
- When adding a jurisdiction, extend `data/source_registry.json` and the jurisdiction/district mappings — do not add Blacksburg-style hard-coded checks.
- When changing API shapes, update both `apps/api/app/models.py` and `packages/shared-schema/src/index.ts`, and check `apps/web/src/api.ts` callers.
- Many `.tmp-*` directories at the repo root are old worktree leftovers; ignore them and never commit them.
