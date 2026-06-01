# Production Readiness Spec

## What

Move the deployed zoning assistant from a live smoke-test beta into a production-ready application architecture as quickly as practical. The next work should stop optimizing for small transitional steps and instead introduce the core production foundations now: Postgres-backed persistence, repeatable data migrations, broader jurisdiction support, real official source coverage, automated source indexing, stronger beta access, deployed smoke tests, and a clear free-staging-to-paid-production path.

## Context

The app is currently live:

- Frontend: `https://zoning-agent-platform.vercel.app`
- Backend: `https://zoning-agent-api.onrender.com`
- GitHub repo: `https://github.com/abhihari010/zoning-agent-platform`

The live smoke test on May 22, 2026 passed the core beta flow:

- beta gate unlocked with `BETA_ACCESS_KEY`
- Vercel frontend reached the Render API
- Source Admin loaded 3 seed sources
- `/api/v1/ingestion/reindex` created 3 chunks
- a Blacksburg home-bakery analysis completed successfully
- result included a `conditional` decision, `0.97` confidence, 3 checklist steps, 3 citations, evidence tab, and audit trace
- browser console showed no errors

Current limitations:

- Render is running a free web service with `ZONING_DB_PATH=/tmp/app.sqlite3`; data can reset whenever the service redeploys, restarts, or spins down.
- Free Render web services cannot attach persistent disks.
- Render does support free Postgres, but free databases expire after 30 days, have a 1 GB storage cap, and do not include backups; they are appropriate for staging, not real production data.
- Source chunks are created only after a manual Source Admin reindex action.
- Seed citations still point to `example.gov`, not official municipal sources.
- Only Blacksburg, VA is meaningfully supported.
- Private beta access is one shared key stored in browser `sessionStorage`.
- There is no repeatable deployed smoke-test script.
- The original `docs/agent-agnostic-zoning-platform/spec.md` is historical and describes earlier provider-boundary work.

Relevant files:

- `render.yaml`: Render API Blueprint.
- `vercel.json`: Vercel frontend deployment.
- `apps/api/app/storage.py`: current SQLite persistence.
- `apps/api/app/models.py`: Pydantic models and API payloads.
- `apps/api/app/routers/api.py`: intake, analysis, ingestion, source admin routes.
- `apps/api/app/services.py`: address normalization and analysis orchestration.
- `apps/api/app/data/jurisdictions.json`: current jurisdiction metadata.
- `apps/api/app/data/source_registry.json`: current seed source registry.
- `apps/web/src/App.tsx`: beta gate, assistant workflow, source admin UI.
- `apps/web/src/api.ts`: deployed API client and beta header handling.

## Requirements

1. The app must gain production-grade persistence through Postgres, while keeping local offline tests easy to run.
2. The current free Render deployment should remain usable as a pre-user staging environment until paid infrastructure is turned on.
3. Production data must not depend on SQLite files in ephemeral Render storage.
4. Database schema changes must be explicit, repeatable, and safe to run during deploys.
5. The app must support multiple jurisdictions through data/config and source scoping, not new hard-coded address branches.
6. The next supported jurisdictions should be planned and implemented beyond Blacksburg, starting with nearby Virginia areas unless source availability blocks them.
7. User-facing citations must come from real official sources or clearly labeled curated local source documents.
8. Source import/reindex must be automatic enough that a fresh deployment can become ready without manual browser clicking.
9. Missing or weak evidence must still produce `unknown` or low-confidence outcomes rather than fabricated zoning conclusions.
10. Beta access must be rotatable and auditable before opening the app to testers.
11. The production deployment must have repeatable smoke tests for health, auth, source readiness, intake, analysis, evidence, and trace.
12. Vercel frontend and Render backend deployment must remain supported.
13. Existing frontend-facing API response shapes should remain backward-compatible unless a specific issue coordinates a contract change.

## Design

### Track 1: Postgres Persistence and Migrations

Replace production persistence with Postgres-backed storage.

Target behavior:

- local development and offline tests can continue using SQLite or an in-memory/temp database
- Render staging uses free Render Postgres while no real users are onboarded
- paid production later upgrades to paid Render Postgres without changing app code
- runtime storage is selected with `DATABASE_URL`; `ZONING_DB_PATH` becomes local/legacy fallback

Implementation approach:

- introduce a database layer that supports Postgres and local SQLite through one repository interface
- migrate current persisted objects from JSON-in-SQLite tables into explicit relational tables where practical
- keep JSON payload columns only where they intentionally preserve flexible trace/result payloads
- add migration tooling, preferably Alembic if SQLAlchemy is adopted
- add startup or deploy documentation for applying migrations
- update tests to run against local SQLite by default and optionally Postgres in CI/manual verification

Minimum tables/entities:

- sessions
- projects
- analyses
- audit_events
- feedback
- sources
- source_chunks
- beta_access_events or equivalent audit metadata
- jurisdictions or a loaded data/config table if file-backed config remains simpler

### Track 2: Free Staging, Paid Production Path

Keep the current Render free plan useful before onboarding users, but make the code production-ready.

Free staging:

- Render web service remains `plan: free`
- use free Render Postgres only for staging preview data
- document that free Postgres expires after 30 days and has no backups
- expect cold starts and service spin-down

Paid production switch:

- upgrade Render web service from free once real users are invited
- upgrade Render Postgres before storing real beta data
- enable backups/retention available on the chosen paid database plan
- lock `CORS_ALLOW_ORIGINS` to the Vercel production domain
- set production secrets in Render and Vercel dashboards, never in Git

The same app code should run in both modes.

### Track 3: Multi-Jurisdiction Support

Expand beyond Blacksburg with a jurisdiction model that controls address support, source filtering, and planning fallback messaging.

Target first expansion set:

- Blacksburg, VA remains supported
- Montgomery County, VA
- Christiansburg, VA
- Roanoke, VA or Roanoke County, VA, depending on source availability

Implementation approach:

- extend `jurisdictions.json` or migrate jurisdiction metadata into Postgres
- add per-jurisdiction metadata:
  - `jurisdiction_id`
  - display name
  - locality/county/state matching rules
  - supported status
  - official zoning/source URLs
  - planning department contact URL/phone/email when available
  - district mapping strategy
- persist `jurisdiction_id` on projects and sources
- filter retrieval by `jurisdiction_id`
- distinguish supported, unsupported, and invalid addresses in both API behavior and UI copy

Acceptance behavior:

- supported jurisdiction: proceed to district/source retrieval
- unsupported but recognized jurisdiction: explain that the address is valid but source coverage is not ready
- invalid address: explain that the address could not be validated

### Track 4: Real Source Coverage and Ingestion

Replace placeholder citations with real source coverage for each supported jurisdiction.

Minimum source coverage per jurisdiction:

- zoning ordinance or municipal code
- zoning map or district reference when available
- planning/zoning permit process source
- building/fire/health review source for use types that can trigger those reviews

Implementation approach:

- start with curated official source entries and local markdown excerpts
- add source metadata fields if needed:
  - `source_type`
  - `jurisdiction_id`
  - `retrieved_at`
  - `effective_date`
  - `official_url`
  - `document_path`
  - `coverage_notes`
- improve import tooling to load jurisdiction-scoped local documents
- reindex automatically when seed source version changes or chunks are empty
- keep manual Source Admin reindex for admin repair

Do not build municipal crawlers until curated official sources and metadata are working.

### Track 5: Production-Grade Index Readiness

Make retrieval ready automatically after deploy.

Minimum behavior:

- seed source records when database is empty
- build chunks when sources exist and no chunks exist
- detect stale chunks when source content hash changes
- expose source/index readiness through `/api/v1/ingestion/status`
- add warnings to analysis if source/index readiness is incomplete

Suggested settings:

- `AUTO_SEED_SOURCES=true`
- `AUTO_REINDEX_ON_EMPTY=true`
- optional `SOURCE_REGISTRY_VERSION` to force controlled reindexing after source changes

### Track 6: Beta Access and Admin Boundary

Improve access control now, without overbuilding full user accounts.

Minimum behavior:

- keep `BETA_ACCESS_KEY` compatibility
- add `BETA_ACCESS_KEYS` or invite-code records in Postgres
- support key labels so testers can be identified without storing raw keys in logs
- hash beta keys server-side
- audit accepted/failed access attempts without exposing secrets
- separate future admin-only source actions from ordinary assistant use

Recommended progression:

1. multi-key beta gate with hashed keys and labels
2. admin key or role for source/reindex endpoints
3. later full auth provider only when public onboarding starts

### Track 7: Deployed Smoke and Release Checks

Create a repeatable smoke-test command that an agent can run after deployment.

The smoke test should verify:

- `GET /health`
- missing beta key returns `401`
- invalid beta key returns `403`
- valid beta key can call `/api/v1/ingestion/status`
- source count is nonzero
- chunk count is nonzero or reindex succeeds
- one supported jurisdiction intake/analyze flow completes
- one unsupported jurisdiction flow is distinguishable from invalid address
- evidence and trace endpoints/data are available after analysis

Inputs:

- `BETA_BASE_API_URL`
- `BETA_ACCESS_KEY`
- `BETA_TEST_SUPPORTED_ADDRESS`
- `BETA_TEST_UNSUPPORTED_ADDRESS`

The script must never print real beta keys.

## Decisions

### Decision: Move to Postgres Now

Choice: Add Postgres persistence as the production storage target instead of extending SQLite further.

Alternatives considered:

- keep SQLite with a persistent disk
- stay on free ephemeral SQLite until users arrive

Why:

- Postgres is the right production baseline for multi-user beta data
- it avoids paying down a SQLite-specific persistence path later
- Render free Postgres can support staging before paid production, with known limitations

Reversible: partially. SQLite should remain useful for tests/local development, but production should converge on Postgres.

### Decision: Keep Render Free as Staging Only

Choice: Maintain the free Render web service and free Postgres option for pre-user staging, not true production data.

Alternatives considered:

- immediately switch all infrastructure to paid
- keep free web plus ephemeral SQLite

Why:

- the user wants to avoid paying before testers/users exist
- free Render services are useful for smoke testing and demos
- official Render docs state free web service files are ephemeral and free Postgres expires after 30 days with no backups

Reversible: yes. Upgrade Render service/database plans when user testing begins.

### Decision: Expand Regionally First

Choice: Add nearby Virginia jurisdictions before arbitrary uploaded jurisdictions.

Alternatives considered:

- support arbitrary uploaded jurisdictions first
- expand nationally

Why:

- regional source patterns and zoning terminology are easier to validate
- nearby jurisdictions are likely relevant to early testers
- source coverage quality matters more than a broad unsupported map

Reversible: yes. The jurisdiction model should later support arbitrary configured jurisdictions.

### Decision: Curated Official Sources Before Crawlers

Choice: Add reviewed official source entries and local documents before building crawlers.

Alternatives considered:

- build municipal web/PDF crawlers immediately
- keep placeholder citations during infrastructure work

Why:

- source trust is the biggest product gap
- crawlers are brittle before the schema and review process are mature
- curated docs provide reliable fixtures for tests and evaluation

Reversible: yes. Curated sources can become crawler test fixtures later.

### Decision: Multi-Key Beta Gate Before Full Auth

Choice: Implement rotatable invite keys and admin separation before adding full accounts.

Alternatives considered:

- keep one shared beta key
- immediately integrate Clerk/Auth0/custom auth

Why:

- key rotation and tester attribution are needed soon
- full auth is larger than necessary before source coverage and persistence are stable
- the current header-based gate can evolve without breaking the frontend

Reversible: yes. Full auth can replace the gate later.

### Assumption: Vercel and Render Remain the Deployment Targets

The spec assumes:

- frontend remains on Vercel
- backend remains on Render
- production API remains separate from the static frontend

If this changes, the deployment plan should be rewritten before implementation.

## Versions

Current baseline:

- Python API: `>=3.11`
- FastAPI, Uvicorn, Pydantic 2, HTTPX, python-dotenv
- React 18, TypeScript, Vite 5
- npm with `package-lock.json`
- Render Docker web service
- Vercel static frontend

New likely dependencies:

- SQLAlchemy 2.x or another explicit database abstraction
- Alembic for migrations if SQLAlchemy is chosen
- PostgreSQL driver such as `psycopg` or `asyncpg`, depending on sync/async storage design

Final implementation plans should verify current dependency versions before pinning.

Render constraints verified from official docs:

- free web services have ephemeral filesystems and cannot attach persistent disks
- paid services can attach persistent disks
- paid and free services can persist relational data in Render Postgres
- free Render Postgres has a 1 GB limit, expires after 30 days, and has no backups

Sources:

- `https://render.com/docs/free`
- `https://render.com/docs/disks`

## Invariants

- Local tests must pass without Google, OpenAI, WatsonX, Vercel, or Render credentials.
- API response shapes used by `apps/web/src/api.ts` must remain compatible unless explicitly coordinated.
- Missing citations must never produce a high-confidence positive answer.
- `/health` must remain unauthenticated.
- `/api/v1/*` must remain protected when beta access is configured.
- Admin source/reindex endpoints must not become publicly writable.
- Source retrieval must be scoped by `jurisdiction_id`.
- Secrets must not be committed, printed in smoke logs, or embedded in screenshots.
- Vercel production must continue pointing to the Render API.

## Error Behavior

- If `DATABASE_URL` is set but unavailable, startup or first database access should fail with a clear database configuration error.
- If migrations are pending, the API should fail clearly or expose a readiness warning; it should not silently use a mismatched schema.
- If free Postgres expires, the runbook should describe recreating staging data and upgrading before real users.
- If source/index readiness is incomplete, analysis should add warnings and lower confidence.
- If a jurisdiction is recognized but unsupported, the user should see unsupported-jurisdiction guidance, not invalid-address copy.
- If beta keys are invalid, protected routes should return `401` for missing credentials and `403` for wrong credentials.

## Testing Strategy

Backend:

- `pytest -q`
- storage repository tests for SQLite/local mode
- optional Postgres integration tests gated by `TEST_DATABASE_URL`
- migration tests against an empty database
- tests for seed source import and auto-reindex
- tests for jurisdiction detection and retrieval scoping
- tests for multi-key beta gate and admin-only routes
- tests that missing citations force unknown/low-confidence behavior

Frontend:

- `npm run typecheck:web`
- `npm run build:web`
- browser verification of beta gate, source admin, reindex, supported analysis, unsupported jurisdiction, evidence, and trace

Deployment:

- deployed smoke test against `https://zoning-agent-api.onrender.com`
- verify Vercel production frontend at `https://zoning-agent-platform.vercel.app`
- verify CORS is locked to Vercel before real testers
- verify Render free staging limitations are documented in handoff

Acceptance criteria:

- app runs against Postgres in Render staging
- schema can be recreated from migrations
- source/index readiness is automatic after fresh deploy
- real official sources replace placeholder citations for the first supported jurisdictions
- at least one jurisdiction beyond Blacksburg has modeled support or explicit source-backed unsupported handling
- deployed smoke test can be run by a future agent in under 10 minutes

## Delegation Plan

Suggested issue/agent split for the future `plan.md`:

- Database agent: Postgres storage layer, migrations, local fallback.
- Deployment agent: Render free staging config, paid production runbook, Vercel env/config validation.
- Jurisdiction agent: jurisdiction model expansion and supported/unsupported address behavior.
- Source coverage agent: official source gathering, registry updates, local docs, citation metadata.
- Ingestion/index agent: automatic seed/reindex, stale chunk detection, readiness warnings.
- Access-control agent: multi-key beta gate, admin separation, audit labels.
- Smoke-test agent: deployed smoke script and verification docs.
- Frontend agent: UI updates for jurisdiction status, admin permissions, source readiness, and production polish.

Shared files requiring coordination:

- `apps/api/app/models.py`
- `apps/api/app/storage.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/services.py`
- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/data/source_registry.json`
- `apps/web/src/api.ts`
- `apps/web/src/App.tsx`
- `render.yaml`
- `README.md`

## Out of Scope

- Public launch before paid production infrastructure is enabled.
- Billing/subscriptions.
- Full OAuth or password accounts in the first production-readiness pass.
- Automated municipal crawling before curated official sources are working.
- National jurisdiction coverage.
- Legal review automation.
- Replacing deterministic analysis as the default safe fallback.
