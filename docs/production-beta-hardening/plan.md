# Production Readiness Ticket Plan

Source spec: `docs/production-beta-hardening/spec.md`

This plan breaks production readiness into parallelizable tickets. The ordering is intentional: establish database and deployment foundations first, then layer source readiness, jurisdiction expansion, access control, frontend polish, smoke tests, and final handoff docs.

## Shared Decisions

- Production storage target is Postgres, selected by `DATABASE_URL`.
- Local development and default tests must keep a SQLite fallback.
- Use SQLAlchemy 2.x, Alembic, and `psycopg` unless implementation discovery finds a concrete blocker.
- Render free web service plus free Render Postgres is staging only. Paid Postgres is required before storing real user beta data.
- Keep Vercel frontend and Render API as the deployment targets.
- Preserve the existing frontend-facing API response shapes unless a ticket explicitly coordinates a contract change.
- Expand regionally first: Montgomery County, Christiansburg, and Roanoke/Roanoke County.
- Do not mark a jurisdiction supported until official source coverage is available.
- Do not build municipal crawlers in this production-readiness pass; use curated official source documents first.

## Dependency Order

- Issues 1 and 2 form the persistence foundation and should be coordinated closely.
- Issue 3 can start once Issue 1 defines the expected database settings and migration command.
- Issues 4, 5, 6, and 8 can run in parallel after the repository/storage shape is clear, but they should avoid changing API response shapes without coordinating Issue 9.
- Issue 7 depends on Issue 6's jurisdiction model and Issue 5's source metadata pattern.
- Issue 9 should track API contract changes from Issues 4, 6, and 8.
- Issue 10 can begin early with existing endpoints, then expand as readiness/admin/jurisdiction behavior lands.
- Issue 11 should be finalized last, after implementation details and issue outcomes are known.

## Issue 1: Add Postgres Persistence Foundation With Migrations

Labels: `production-readiness`, `backend`, `database`

### Goal

Introduce Postgres-backed persistence with repeatable migrations while preserving a SQLite fallback for local development and offline tests.

### Context

The deployed Render API currently uses SQLite at `/tmp/app.sqlite3`, which is ephemeral on the free service. The app needs production-ready persistence before real beta users. The existing `apps/api/app/storage.py` stores JSON payloads in SQLite tables.

### Relevant Files or References

- `docs/production-beta-hardening/spec.md`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`
- `apps/api/pyproject.toml`
- `render.yaml`

### Proposed Approach

Add SQLAlchemy 2.x, Alembic, and `psycopg`. Create an explicit database configuration path that uses `DATABASE_URL` when set and local SQLite otherwise. Add migrations for sessions, projects, analyses, audit events, feedback, sources, source chunks, beta access events, and jurisdictions. Keep flexible JSON payload columns only for analysis results or audit details where preserving current response payloads is useful.

### Acceptance Criteria

- `DATABASE_URL` selects Postgres-backed storage.
- Local default storage still works without Postgres.
- Alembic can create the schema from an empty database.
- Existing API behavior can still be represented by the new schema.
- No credentials or database URLs are committed.

### Source Reference

Spec sections: `Track 1: Postgres Persistence and Migrations`, `Decision: Move to Postgres Now`, `Invariants`.

### Verify

- From repo root: `cd apps/api; pytest -q`
- With a local Postgres URL in `TEST_DATABASE_URL`, run the migration against an empty database.
- Confirm app import succeeds with no `DATABASE_URL`.

### Out of Scope

- Migrating deployed production data.
- Building user accounts or billing.

## Issue 2: Port Existing Storage Behavior to the Repository Layer

Labels: `production-readiness`, `backend`, `database`, `refactor`

### Goal

Move current storage operations behind the new database/repository layer without breaking intake, analysis, source admin, feedback, or trace behavior.

### Context

Routes and services currently import the global `store` from `apps/api/app/storage.py`. The new persistence layer should keep the same business behavior while allowing Postgres in staging/production and SQLite locally.

### Relevant Files or References

- `apps/api/app/storage.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/services.py`
- `apps/api/tests/test_api.py`
- `apps/api/tests/test_services.py`

### Proposed Approach

Define a repository/store interface that covers current operations: project create/read/update, analysis save/read, audit events, feedback, source upsert/list/count, chunk replace/list/count, and latest audit timestamp. Implement it through the new SQLAlchemy-backed layer, with SQLite-backed execution for local tests. Update route imports to depend on the interface rather than concrete SQLite implementation.

### Acceptance Criteria

- Existing API tests pass with the default local SQLite fallback.
- Current source admin, reindex, feedback, trace, intake, and analysis behavior is preserved.
- Repository parity tests cover key operations against SQLite and, when configured, Postgres.
- `SQLiteStore` is either removed or retained only as a compatibility wrapper around the new interface.

### Source Reference

Spec sections: `Track 1`, `Requirements`, `Invariants`.

### Verify

- `cd apps/api; pytest -q`
- Optional: `TEST_DATABASE_URL=<postgres-url> pytest -q`

### Out of Scope

- New public API fields.
- Production data migration from old SQLite files.

## Issue 3: Configure Render Staging and Production Database Paths

Labels: `production-readiness`, `deployment`, `docs`

### Goal

Make Render deployment config and docs reflect a free staging path with Postgres and a paid production upgrade path.

### Context

The current `render.yaml` uses a free web service and `/tmp/app.sqlite3`. Free Render web files are ephemeral. Free Render Postgres can support staging but expires after 30 days and has no backups.

### Relevant Files or References

- `render.yaml`
- `README.md`
- `.env.example`
- `docs/production-beta-hardening/spec.md`

### Proposed Approach

Update Render Blueprint/docs to use `DATABASE_URL` for the API, document free staging limitations, and document the paid production switch. If Blueprint-managed free Postgres is practical, include it in `render.yaml`; otherwise document the dashboard setup and required env vars. Keep `ZONING_DB_PATH` as local fallback only.

### Acceptance Criteria

- Render staging config uses Postgres instead of ephemeral SQLite.
- README clearly separates free staging from paid production.
- Required env vars are documented without secrets.
- CORS guidance locks production to `https://zoning-agent-platform.vercel.app`.
- Existing deployed frontend/backend URLs remain documented.

### Source Reference

Spec sections: `Track 2: Free Staging, Paid Production Path`, `Versions`, `Error Behavior`.

### Verify

- Render API boots with `DATABASE_URL`.
- `GET /health` returns OK.
- `pytest -q` still passes locally without `DATABASE_URL`.

### Out of Scope

- Enabling paid infrastructure.
- Secret rotation in Render dashboard.

## Issue 4: Add Automatic Source Seeding and Index Readiness

Labels: `production-readiness`, `backend`, `ingestion`, `data`

### Goal

Ensure a fresh deploy can become source-ready without an admin manually clicking Reindex.

### Context

The live smoke test showed Source Admin had 3 seed sources but 0 chunks until manual reindex. Production readiness requires automatic seed and chunk readiness.

### Relevant Files or References

- `apps/api/app/ai/source_registry_retriever.py`
- `apps/api/app/ingestion.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`

### Proposed Approach

Add settings such as `AUTO_SEED_SOURCES`, `AUTO_REINDEX_ON_EMPTY`, and optionally `SOURCE_REGISTRY_VERSION`. Seed sources when empty, build chunks when chunks are empty and sources exist, and detect stale chunks using source content hashes or source version changes. Keep manual reindex available for admin repair.

### Acceptance Criteria

- Fresh database with seed registry can produce nonzero sources and chunks without manual UI action.
- Reindex is idempotent and deterministic.
- Stale chunks are rebuilt when source content changes.
- Ingestion status exposes enough readiness detail for admins and smoke tests.
- Analysis warns or lowers confidence when source/index readiness is incomplete.

### Source Reference

Spec sections: `Track 5: Production-Grade Index Readiness`, `Error Behavior`.

### Verify

- `pytest -q`
- Test empty database -> status/retrieval path creates or reports ready chunks.
- Test changed source hash -> stale chunk rebuild.

### Out of Scope

- Background workers or queues.
- Municipal crawlers.

## Issue 5: Replace Placeholder Citations With Official Blacksburg Sources

Labels: `production-readiness`, `data`, `research`, `citations`

### Goal

Remove placeholder `example.gov` citations and replace them with real official Blacksburg source coverage.

### Context

The live app currently returns working citations, but they point to placeholder URLs. Production users need auditable official sources.

### Relevant Files or References

- `apps/api/app/data/source_registry.json`
- `services/ingestion/documents/*`
- `apps/api/app/models.py`
- `apps/api/app/ingestion.py`

### Proposed Approach

Gather official Blacksburg zoning/planning/building/fire-health sources and encode them as curated source registry entries or local markdown documents. Preserve `jurisdiction_id=blacksburg-va`, district/use tags, section references, URLs, effective dates when known, and concise excerpts. Update tests to assert no supported flow returns `example.gov`.

### Acceptance Criteria

- No seed source URL uses `example.gov`.
- Blacksburg source entries use official URLs or clearly labeled curated local documents.
- Source metadata includes jurisdiction, source type where available, district/use tags, and effective dates when known.
- A Blacksburg home-business analysis returns real cited sources.

### Source Reference

Spec sections: `Track 4: Real Source Coverage and Ingestion`, `Decision: Curated Official Sources Before Crawlers`.

### Verify

- `pytest -q`
- Search check: `rg "example\\.gov" apps/api services README.md docs`
- Browser or API smoke analysis returns real citation URLs.

### Out of Scope

- Legal verification of interpretations.
- Automated crawling.

## Issue 6: Expand Jurisdiction Model Beyond Blacksburg

Labels: `production-readiness`, `backend`, `jurisdictions`, `frontend`

### Goal

Add modeled jurisdiction support for nearby Virginia areas while preserving explicit unsupported behavior when source coverage is incomplete.

### Context

The app currently treats Blacksburg as the only meaningfully supported jurisdiction. The production-readiness spec targets Montgomery County, Christiansburg, and Roanoke/Roanoke County next.

### Relevant Files or References

- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/jurisdictions.py`
- `apps/api/app/services.py`
- `apps/api/app/district_mapping.py`
- `apps/web/src/App.tsx`

### Proposed Approach

Extend jurisdiction metadata with locality/county/state matching, supported status, official source URLs, planning contact details, and district mapping strategy. Recognize target jurisdictions even before all are supported. Keep unsupported-jurisdiction behavior distinct from invalid address. Persist/filter by `jurisdiction_id`.

### Acceptance Criteria

- Montgomery County, Christiansburg, and Roanoke/Roanoke County are represented in jurisdiction metadata.
- API can distinguish supported, recognized-unsupported, and invalid addresses.
- Frontend messaging no longer collapses all non-Blacksburg cases into invalid address copy.
- Retrieval remains scoped by jurisdiction.

### Source Reference

Spec sections: `Track 3: Multi-Jurisdiction Support`, `Decision: Expand Regionally First`.

### Verify

- `pytest -q`
- Mocked Google address tests for each target jurisdiction.
- Frontend typecheck/build if UI copy or API mapping changes.

### Out of Scope

- Marking a jurisdiction supported without source coverage.
- National expansion.

## Issue 7: Add Source Coverage for the First Expanded Jurisdiction

Labels: `production-readiness`, `data`, `jurisdictions`, `citations`

### Goal

Make one non-Blacksburg jurisdiction truly source-backed and supported.

### Context

Jurisdictions should not be marked supported until official source coverage exists. This ticket should pick the first target with the best source availability after research.

### Relevant Files or References

- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/data/source_registry.json`
- `services/ingestion/documents/*`
- `docs/production-beta-hardening/spec.md`

### Proposed Approach

Research Montgomery County, Christiansburg, and Roanoke/Roanoke County official sources. Pick the first one with sufficient zoning/planning/building/fire-health coverage. Add curated source entries/documents and mark that jurisdiction supported. Add at least one mocked or deterministic analysis test proving citations are scoped to the new jurisdiction.

### Acceptance Criteria

- One expanded jurisdiction is marked supported with official source-backed coverage.
- Supported analysis for that jurisdiction returns only relevant scoped citations.
- Unsupported targets remain recognized but unsupported.
- Tests prevent cross-jurisdiction citation leakage.

### Source Reference

Spec sections: `Track 3`, `Track 4`, `Requirements`.

### Verify

- `pytest -q`
- Source URL search confirms official/non-placeholder sources.
- API smoke test for the new jurisdiction.

### Out of Scope

- Supporting all three target jurisdictions in one ticket.
- Automated source crawling.

## Issue 8: Implement Multi-Key Beta Access and Admin Separation

Labels: `production-readiness`, `auth`, `backend`, `security`

### Goal

Replace the one shared beta key with rotatable invite/admin access while preserving current beta gate compatibility.

### Context

The deployed app uses one `BETA_ACCESS_KEY` sent as `X-Beta-Access-Key`. Production readiness needs rotation, tester attribution, and source-admin protection.

### Relevant Files or References

- `apps/api/app/main.py`
- `apps/api/app/settings.py`
- `apps/api/app/routers/api.py`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`

### Proposed Approach

Keep `BETA_ACCESS_KEY` compatibility. Add support for `BETA_ACCESS_KEYS` or persisted invite records with hashed keys and labels. Audit accepted/failed access without logging raw keys. Add admin-only protection for source write/reindex/import routes when admin access is configured. Keep assistant read/intake/analyze access simple for beta testers.

### Acceptance Criteria

- Missing beta key returns `401`; wrong key returns `403`; valid key succeeds.
- Multiple configured beta keys can be accepted.
- Raw beta keys are not stored in audit logs.
- Source write/reindex/import endpoints can require admin access.
- Existing frontend beta gate still works.

### Source Reference

Spec sections: `Track 6: Beta Access and Admin Boundary`, `Decision: Multi-Key Beta Gate Before Full Auth`.

### Verify

- `pytest -q`
- Tests for single-key compatibility, multi-key acceptance, invalid key rejection, and admin-only route protection.
- Frontend typecheck/build if admin key UI is touched.

### Out of Scope

- Full OAuth, passwords, billing, or accounts.

## Issue 9: Update Frontend for Jurisdiction, Readiness, and Admin Access

Labels: `production-readiness`, `frontend`, `ux`, `auth`

### Goal

Make production readiness visible and understandable in the frontend.

### Context

The current UI has beta gate, assistant workflow, source admin, evidence, and trace. It needs clearer jurisdiction status, index readiness, unsupported-jurisdiction handling, and admin access behavior.

### Relevant Files or References

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `packages/shared-schema/src/index.ts`
- `docs/production-beta-hardening/spec.md`

### Proposed Approach

Show jurisdiction support status near intake results. Surface source/index readiness in Source Admin and result warnings. If admin access is required for source actions, add minimal admin-key handling or disabled states. Improve unsupported-jurisdiction copy so users understand whether an address is invalid or valid-but-not-yet-covered.

### Acceptance Criteria

- Supported, unsupported, and invalid address states are visibly distinct.
- Source Admin clearly shows readiness and stale/incomplete index states.
- Admin-only source actions fail gracefully with actionable UI copy.
- Existing checklist/evidence/trace/feedback flows still work.

### Source Reference

Spec sections: `Track 3`, `Track 5`, `Track 6`.

### Verify

- `npm run typecheck:web`
- `npm run build:web`
- Browser smoke test for beta gate, source admin, reindex, supported analysis, unsupported jurisdiction, evidence, and trace.

### Out of Scope

- Major redesign.
- Full account UI.

## Issue 10: Add Deployed Production Smoke Test Script

Labels: `production-readiness`, `testing`, `deployment`

### Goal

Create a repeatable deployed smoke test that future agents can run after Render/Vercel changes.

### Context

The live beta was manually tested in the browser. Production readiness requires a scriptable smoke path that does not rely on manual clicking.

### Relevant Files or References

- `README.md`
- `apps/api/app/routers/api.py`
- `apps/web/src/api.ts`
- `docs/production-beta-hardening/spec.md`

### Proposed Approach

Add a script under `scripts/` or `services/` that reads `BETA_BASE_API_URL`, `BETA_ACCESS_KEY`, `BETA_TEST_SUPPORTED_ADDRESS`, and `BETA_TEST_UNSUPPORTED_ADDRESS`. It should call health, auth failure checks, ingestion status, reindex if needed, supported intake/analyze, unsupported jurisdiction behavior, result/evidence/trace checks. It must redact secrets in output.

### Acceptance Criteria

- Script exits nonzero on failed health/auth/source/analysis checks.
- Script never prints the beta key.
- Script can be run against `https://zoning-agent-api.onrender.com`.
- README documents how to run it.

### Source Reference

Spec sections: `Track 7: Deployed Smoke and Release Checks`, `Testing Strategy`.

### Verify

- Run script locally against deployed API with env vars.
- `pytest -q` if helper modules are added.

### Out of Scope

- Full browser E2E suite.
- CI secrets setup.

## Issue 11: Update Production Runbook and Handoff Docs

Labels: `production-readiness`, `docs`, `handoff`

### Goal

Create the documentation needed for future agents to continue production readiness without this chat context.

### Context

The existing `docs/agent-agnostic-zoning-platform/handoff.md` is stale. The new production-readiness work needs a current handoff and runbook.

### Relevant Files or References

- `README.md`
- `docs/production-beta-hardening/spec.md`
- `docs/production-beta-hardening/plan.md`
- `docs/agent-agnostic-zoning-platform/handoff.md`

### Proposed Approach

Create `docs/production-beta-hardening/handoff.md` or refresh the existing handoff with current deployed URLs, commits, storage direction, Render/Vercel setup, issue map, smoke-test instructions, and known limitations. Update README sections that still imply SQLite/free Render is production-ready.

### Acceptance Criteria

- Handoff includes current repo, deployed URLs, active production-readiness issue list, and verification commands.
- Free staging versus paid production is clearly explained.
- Another agent can pick an issue and start without reading this conversation.
- README and handoff agree on deployment and storage direction.

### Source Reference

Spec sections: `Delegation Plan`, `Testing Strategy`, `Versions`.

### Verify

- Read-through review of docs links and commands.
- Confirm referenced files/URLs exist.

### Out of Scope

- Creating or assigning all future PRs.
- Long-form product strategy.
