# Jurisdiction RAG Expansion Implementation Plan

Last updated: May 25, 2026

## Purpose

Build a scalable, trustworthy path from the current regional zoning assistant to broad US coverage without dumping unverified national documents into one large vector store.

The intended architecture is:

`jurisdiction registry -> source packs -> validated chunks -> jurisdiction-filtered vectors -> golden QA -> public support`

This plan is written for future agents that may not have the original chat context. The core decision is deliberate:

- Do not create one giant folder of every US zoning document and ingest it blindly.
- Do create repeatable jurisdiction source packs with official-source metadata.
- Do store vectors with strict jurisdiction, source, district, use, and freshness metadata.
- Do retrieve only from the relevant jurisdiction or approved parent jurisdiction.
- Do promote coverage only after source completeness and golden QA pass.

## Current Baseline

Repository: `C:\Users\abhih\Zoning-Agent-App`

Frontend:

- Vite React app in `apps/web`
- Main UI in `apps/web/src/App.tsx`
- API client in `apps/web/src/api.ts`
- Local dev URL usually `http://127.0.0.1:5173/`

Backend:

- FastAPI app in `apps/api/app`
- API routes in `apps/api/app/routers/api.py`
- Storage abstraction in `apps/api/app/repositories.py`
- SQLAlchemy schema in `apps/api/app/database.py`
- Alembic migrations in `apps/api/alembic/versions`
- Jurisdiction matching in `apps/api/app/jurisdictions.py` and `apps/api/app/tools/jurisdiction_tool.py`
- Source ingestion in `apps/api/app/ingestion.py`
- Seed source registry in `apps/api/app/data/source_registry.json`
- Jurisdiction seed data in `apps/api/app/data/jurisdictions.json`

Relevant docs already present:

- `docs/public-launch/plan.md`
- `docs/public-launch/nationwide-expansion-strategy.md`
- `docs/public-launch/sprint-1-auth-design.md`

Current coverage model:

- `public_supported`: Blacksburg, VA; Montgomery County, VA
- `source_indexed` / not public supported: Christiansburg, VA; Roanoke, VA; Roanoke County, VA
- Unknown US jurisdictions should be recognized as unsupported and routed into a request flow.

Current source-pack examples:

- `services/ingestion/source_packs/va/blacksburg-va/manifest.json`
- `services/ingestion/source_packs/va/montgomery-county-va/manifest.json`
- `services/ingestion/source_packs/va/christiansburg-va/manifest.json`
- `services/ingestion/source_packs/va/roanoke-va/manifest.json`
- `services/ingestion/source_packs/va/roanoke-county-va/manifest.json`

## Strategic Principles

1. Coverage is jurisdiction-scoped.
   A zoning answer must be grounded in the jurisdiction that controls the parcel, plus explicitly allowed parent or state sources.

2. Vectors are retrieval infrastructure, not truth.
   A vector hit is only useful if it carries correct jurisdiction, source type, effective date, URL, district, and use metadata.

3. Public support is a QA status.
   A jurisdiction is not public-supported just because documents were downloaded or embedded.

4. Expansion is demand-led.
   Use `jurisdiction_requests` and observed user demand to choose the next packs.

5. Parent sources are explicit.
   State health/building/fire sources may apply across jurisdictions, but they must be tagged as `jurisdiction_id="*"` or as an approved parent scope, not mixed into local zoning by accident.

6. Freshness matters.
   Official URLs, effective dates, retrieval timestamps, source versions, and content hashes are part of the product's trust layer.

## Recommended Workstreams

The plan is split into tasks that can be assigned to separate agents. Tasks are ordered by dependency. Do not skip the validation and QA tasks; they are what keep RAG from becoming a confident hallucination machine.

## Task 1: Stabilize and Commit the Public Launch Baseline

### Goal

Create a clean baseline branch/PR containing Sprint 1 and Sprint 2 work before deeper RAG expansion begins.

### Context

There are substantial uncommitted changes for auth, coverage statuses, source packs, jurisdiction requests, launch polish, and Playwright smoke tests. Future RAG work should not be mixed into that same review without a baseline.

### Relevant Files or References

- `apps/api/app/auth.py`
- `apps/api/app/database.py`
- `apps/api/app/repositories.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/data/source_registry.json`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `services/ingestion/source_packs`
- `tests/e2e/public-launch-smoke.mjs`
- `docs/public-launch`

### Proposed Approach

- Review current `git status --short`.
- Run the full backend and frontend checks.
- Commit only intended files.
- Open a PR that explicitly describes Sprint 1 and Sprint 2.
- Do not include beta keys, local temp env files, or generated screenshots.

### Acceptance Criteria

- A PR exists for the public launch baseline.
- The PR describes auth, coverage statuses, source packs, jurisdiction requests, legal pages, and Playwright smoke coverage.
- Tests pass locally before PR creation.
- No secrets are committed.

### Source Reference

The app needs a stable deployable foundation before scaling source ingestion.

### Verify

```powershell
git status --short
cd apps/api
pytest -q --basetemp ..\..\.tmp\pytest
cd ..\..
npm run typecheck:web
npm run build:web
npm run test:e2e
git diff --check
```

### Out of Scope

- New jurisdiction crawling.
- Production deployment changes beyond documenting the PR.

## Task 2: Define Source Pack Contract Version 1

### Goal

Make source packs a formal contract so agents can add jurisdictions consistently.

### Context

The repo has example `manifest.json` files, but the schema is currently implicit. Agents need a strict spec for required fields, allowed source types, parent/state sources, district tags, use tags, and verification notes.

### Relevant Files or References

- `services/ingestion/source_packs/**/manifest.json`
- `apps/api/app/ingestion.py`
- `apps/api/app/models.py`
- `docs/public-launch/nationwide-expansion-strategy.md`

### Proposed Approach

- Add `docs/public-launch/source-pack-spec.md`.
- Define manifest fields:
  - `schema_version`
  - `jurisdiction.jurisdiction_id`
  - `jurisdiction.name`
  - `jurisdiction.coverage_status`
  - `jurisdiction.state`
  - `jurisdiction.state_fips`
  - `jurisdiction.county_fips`
  - `jurisdiction.place_fips`
  - `jurisdiction.jurisdiction_type`
  - `jurisdiction.parent_jurisdiction_id`
  - `jurisdiction.official_source_urls`
  - `jurisdiction.zoning_map_url`
  - `jurisdiction.planning_contact`
  - `verification_notes`
  - `sources`
- Define required source fields:
  - `source_id`
  - `title`
  - `excerpt` or `full_text`
  - `section_ref`
  - `jurisdiction_id`
  - `url`
  - `effective_date`
  - `source_type`
  - `districts`
  - `uses`
- Define source types:
  - `zoning_ordinance`
  - `zoning_map`
  - `planning_page`
  - `permit_page`
  - `building_code`
  - `health_code`
  - `fire_code`
  - `gis_layer`
  - `fee_schedule`
  - `application_form`
  - `state_law`
- Define when `jurisdiction_id="*"` is allowed:
  - Statewide health, building, fire, or business licensing sources.
  - Must include `metadata.applies_to_states`.
  - Must not be used for municipal zoning ordinances.
- Define coverage promotion rules:
  - `source_discovery`: official links found, not indexed.
  - `source_indexed`: pack imports and chunks.
  - `qa_ready`: golden scenarios pass.
  - `public_supported`: promoted for users.

### Acceptance Criteria

- A future agent can add a jurisdiction pack by reading the spec alone.
- The spec states required fields and examples.
- The spec explains parent/state source handling.
- The spec states what blocks public support.

### Source Reference

User asked whether to gather all US docs into Chroma. This task defines the safer replacement: source packs.

### Verify

Manual doc review. No code test required.

### Out of Scope

- Automated schema validation code.

## Task 3: Add Source Pack Validation Command

### Goal

Provide a command that validates source packs before they are imported or embedded.

### Context

The importer currently validates some required fields at runtime. A dedicated validation command helps agents check packs without mutating the database.

### Relevant Files or References

- `apps/api/app/ingestion.py`
- `services/ingestion/source_packs`
- `apps/api/tests/test_services.py`
- Potential new script: `scripts/validate_source_packs.py`

### Proposed Approach

- Add `scripts/validate_source_packs.py`.
- It should:
  - Load all `manifest.json` files under `services/ingestion/source_packs`.
  - Validate required jurisdiction fields.
  - Validate required source fields.
  - Reject placeholder URLs like `example.gov`.
  - Reject non-HTTP URLs unless explicitly allowed for curated local fallback.
  - Validate `effective_date` is present.
  - Validate all source IDs are unique.
  - Validate every source has `jurisdiction_id` matching the pack or an explicit parent/global scope.
  - Warn, but do not fail, when source `districts` contains only `unknown`.
  - Print a summary by jurisdiction.
- Add tests covering valid and invalid manifests.

### Acceptance Criteria

- Invalid packs fail before database import.
- Missing official URL, title, effective date, or jurisdiction ID produces a clear error.
- The command never downloads external pages.
- The command can be run locally by any agent.

### Source Reference

Blind national ingestion would create bad vectors. Validation is the first gate.

### Verify

```powershell
python scripts/validate_source_packs.py
cd apps/api
pytest tests/test_services.py -q
```

### Out of Scope

- Crawling or URL freshness checks.
- Legal interpretation of sources.

## Task 4: Add Vector Index Namespace and Metadata Contract

### Goal

Ensure Chroma/vector retrieval is scoped by jurisdiction and source metadata.

### Context

The app already has RAG/vector code paths. The next step is to guarantee chunks carry the metadata needed for safe retrieval and that queries filter on that metadata.

### Relevant Files or References

- `apps/api/app/rag/vector_store.py`
- `apps/api/app/ai/source_registry_retriever.py`
- `apps/api/app/ingestion.py`
- `apps/api/app/models.py`
- `apps/api/app/data/source_registry.json`
- `services/ingestion/source_packs`

### Proposed Approach

- Define required vector metadata for every chunk:
  - `source_id`
  - `chunk_id`
  - `jurisdiction_id`
  - `jurisdiction_scope`
  - `state`
  - `county`
  - `municipality`
  - `source_type`
  - `source_version`
  - `content_hash`
  - `effective_date`
  - `retrieved_at`
  - `url`
  - `districts`
  - `uses`
  - `coverage_status`
- Add or confirm metadata is emitted in `build_source_chunks`.
- Add retrieval filters:
  - first filter: exact `jurisdiction_id`
  - second filter: approved parent jurisdiction or `jurisdiction_id="*"` with applicable state
  - then district/use relevance
- Ensure unsupported jurisdictions do not run compliance retrieval.
- Add tests where two jurisdictions have similar text and retrieval must not cross jurisdictions.

### Acceptance Criteria

- Chunks in the vector store can be filtered by jurisdiction.
- Retrieval for Roanoke cannot return Blacksburg municipal zoning unless explicitly global/parent.
- Statewide sources can be returned only when they declare applicable state metadata.
- Citation validation fails or downgrades if a citation comes from the wrong jurisdiction.

### Source Reference

RAG must be jurisdiction-filtered, not national free-for-all semantic search.

### Verify

```powershell
cd apps/api
pytest tests/test_rag_phase2.py tests/test_services.py -q
```

If `tests/test_rag_phase2.py` does not yet cover this, add focused tests there or create `tests/test_vector_metadata.py`.

### Out of Scope

- Production Chroma deployment.
- Large-scale ingestion.

## Task 5: Build Golden QA Scenario Contract

### Goal

Make public support dependent on repeatable golden scenario tests.

### Context

Golden scenarios already exist in `apps/api/tests/golden/scenarios.json`, but expansion requires a documented pattern and one or more scenarios per candidate jurisdiction.

### Relevant Files or References

- `apps/api/tests/golden/scenarios.json`
- `apps/api/tests/golden/runner.py`
- `apps/api/tests/golden/test_golden_scenarios.py`
- `docs/public-launch/nationwide-expansion-strategy.md`

### Proposed Approach

- Document golden scenario fields in `docs/public-launch/golden-scenario-spec.md`.
- Add one scenario each for:
  - Christiansburg, VA
  - Roanoke, VA
  - Roanoke County, VA
- For now, scenarios can assert `low_confidence` or `unknown` while those jurisdictions remain `source_indexed`.
- When a jurisdiction is promoted to `qa_ready`, add a happy-path scenario with at least one official citation.
- Update the runner if needed to assert:
  - expected coverage status
  - expected jurisdiction support flag
  - no citations from wrong jurisdictions
  - minimum citation count
  - warnings for unsupported or source-not-ready states

### Acceptance Criteria

- Every candidate expansion jurisdiction has at least one golden scenario.
- Public-supported jurisdictions have at least one successful happy path.
- Source-indexed but not public-supported jurisdictions do not accidentally produce confident answers.
- Golden scenarios are easy for agents to add.

### Source Reference

The product should not promote a jurisdiction because documents exist; it should promote after scenario QA.

### Verify

```powershell
cd apps/api
pytest tests/golden -q
```

### Out of Scope

- Exhaustive legal QA.
- Visual/browser tests.

## Task 6: Implement Coverage Promotion Guard

### Goal

Prevent admins or future agents from marking a jurisdiction `public_supported` unless source and QA gates pass.

### Context

The app now has coverage statuses, but promotion logic is mostly process-driven. A guard should enforce minimum machine-checkable requirements.

### Relevant Files or References

- `apps/api/app/jurisdictions.py`
- `apps/api/app/repositories.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/ingestion.py`
- `apps/api/tests/test_api.py`
- `apps/api/tests/golden`

### Proposed Approach

- Add a helper such as `validate_public_support_candidate(jurisdiction_id)`.
- It should check:
  - jurisdiction exists
  - has planning contact URL or email/phone
  - has official source URLs
  - source registry has at least one source for the jurisdiction
  - indexed chunks exist for the jurisdiction
  - sources have URL and effective date
  - at least one golden scenario exists for the jurisdiction
- If route/API support is added for status updates, call this helper before allowing `public_supported`.
- Add a CLI/report mode if no admin status route exists yet.

### Acceptance Criteria

- A jurisdiction cannot become public-supported through API/admin workflow unless required checks pass.
- Failure messages identify the missing gate.
- Existing public-supported jurisdictions pass the guard.
- Current source-indexed jurisdictions fail until QA criteria are complete.

### Source Reference

The trust model depends on public support being a gate, not a boolean someone can flip casually.

### Verify

```powershell
cd apps/api
pytest tests/test_jurisdiction_tool.py tests/test_api.py tests/golden -q
```

### Out of Scope

- Human legal review.

## Task 7: Add Demand-Led Coverage Backlog View

### Goal

Make jurisdiction requests actionable for admins.

### Context

Sprint 2 added a request endpoint and admin summary endpoint. The frontend should expose request counts and coverage candidates in the admin workspace.

### Relevant Files or References

- `apps/api/app/routers/api.py`
- `apps/web/src/api.ts`
- `apps/web/src/App.tsx`
- `apps/api/tests/test_api.py`

### Proposed Approach

- Add frontend API client for `GET /api/v1/admin/jurisdiction-requests`.
- Add an admin panel showing:
  - jurisdiction name
  - request count
  - state/county/locality
  - last requested date
  - current coverage status if known
- Add a short empty state.
- Keep this admin-only. Normal users only see the request CTA.

### Acceptance Criteria

- Admin can see top requested jurisdictions.
- Normal users cannot access the request summary endpoint.
- UI does not expose user emails or raw comments.
- Request counts can be used to choose the next source pack.

### Source Reference

Nationwide expansion should be guided by actual user demand.

### Verify

```powershell
cd apps/api
pytest tests/test_api.py -q
cd ..\..
npm run typecheck:web
npm run build:web
```

### Out of Scope

- CRM integration.
- Email notifications.

## Task 8: Build First Real Expansion Batch to QA Ready

### Goal

Move Christiansburg, Roanoke, and Roanoke County from `source_indexed` toward `qa_ready`.

### Context

These jurisdictions have starter source packs and official source metadata. They are not yet public-supported because district handling, source completeness, and golden scenarios need more work.

### Relevant Files or References

- `services/ingestion/source_packs/va/christiansburg-va/manifest.json`
- `services/ingestion/source_packs/va/roanoke-va/manifest.json`
- `services/ingestion/source_packs/va/roanoke-county-va/manifest.json`
- `apps/api/app/data/jurisdictions.json`
- `apps/api/tests/golden/scenarios.json`
- `apps/api/app/tools/parcel_tool.py`
- `apps/api/app/district_mapping.py`

### Proposed Approach

For each jurisdiction:

- Verify official planning page.
- Verify zoning ordinance/code URL.
- Verify zoning map/GIS URL.
- Verify permit/building page.
- Verify health/fire source where food or assembly use is in scenario.
- Add source pack entries for missing official sources.
- Add one golden scenario:
  - one common small-business or home-occupation scenario
  - expected answer should stay `unknown` or `low_confidence` until enough ordinance detail exists
  - after enough sources exist, update expected answer to a supported decision with citations
- Improve district mapping if official GIS/map handling is sufficient.

### Acceptance Criteria

- Each of the three jurisdictions has at least:
  - planning/contact source
  - zoning ordinance/code source
  - zoning map/GIS source
  - permit/building source
  - one golden scenario
- Source pack validation passes.
- Golden tests pass.
- None is promoted to `public_supported` until the promotion guard passes.

### Source Reference

This is the first expansion batch before attempting larger US coverage.

### Verify

```powershell
python scripts/validate_source_packs.py
cd apps/api
pytest tests/golden tests/test_services.py tests/test_jurisdiction_tool.py -q
```

### Out of Scope

- All Virginia jurisdictions.
- All use categories.

## Task 9: Add Document Acquisition Workflow

### Goal

Create a safe, repeatable way to gather official documents for a jurisdiction without blind ingestion.

### Context

Agents may need to research official pages and PDFs. The repo should define where to put raw documents, extracted text, and source-pack manifests.

### Relevant Files or References

- `services/ingestion/source_packs`
- `services/ingestion/documents`
- `apps/api/app/ingestion.py`
- `docs/public-launch/source-pack-spec.md`

### Proposed Approach

- Add `docs/public-launch/document-acquisition-workflow.md`.
- Define folder shape:
  - `services/ingestion/source_packs/<state>/<jurisdiction_id>/manifest.json`
  - `services/ingestion/source_packs/<state>/<jurisdiction_id>/raw/`
  - `services/ingestion/source_packs/<state>/<jurisdiction_id>/extracted/`
  - `services/ingestion/source_packs/<state>/<jurisdiction_id>/notes.md`
- Raw PDFs/HTML should be kept only when licensing and repo-size concerns are acceptable.
- Prefer manifests with official URLs and extracted excerpts over committing huge PDFs.
- Add rules:
  - never use unofficial blogs or SEO pages as zoning sources
  - prefer official city/county/state domains or official municipal code hosts
  - capture retrieval date
  - capture effective date separately from retrieval date
  - flag stale or uncertain dates

### Acceptance Criteria

- Agents know exactly where to store source-pack materials.
- The workflow discourages dumping huge files into the repo.
- The workflow separates official source URL, retrieval date, effective date, and verification notes.

### Source Reference

The user suggested a large US document folder. This task converts that impulse into a controlled acquisition process.

### Verify

Manual doc review. No code test required.

### Out of Scope

- Automated crawling.

## Task 10: Add Optional Official Source Discovery Helper

### Goal

Speed up source-pack creation while keeping human/QA approval.

### Context

Long-term, agents should not manually search every source from scratch. A helper can generate candidate official URLs, but it must not auto-promote or auto-ingest without validation.

### Relevant Files or References

- New script: `scripts/discover_jurisdiction_sources.py`
- `docs/public-launch/document-acquisition-workflow.md`
- `docs/public-launch/source-pack-spec.md`

### Proposed Approach

- Add a script that accepts:
  - `--jurisdiction-name`
  - `--state`
  - `--jurisdiction-type`
  - optional `--county`
- It can output a draft manifest skeleton with TODOs.
- It should not require paid APIs.
- If web search is unavailable in the runtime, the script should create a structured blank template.
- Candidate URL categories:
  - planning/zoning page
  - municipal code host
  - zoning map/GIS
  - building permits
  - business license
  - fire marshal
  - health department
- Every candidate should be marked `verification_status="candidate"` until reviewed.

### Acceptance Criteria

- The script creates a draft source-pack folder without mutating production data.
- Draft manifests cannot pass validation as public-ready until required fields are verified.
- Output makes missing categories obvious.

### Source Reference

Nationwide expansion needs speed, but still requires QA gates.

### Verify

```powershell
python scripts/discover_jurisdiction_sources.py --jurisdiction-name "Salem" --state VA --jurisdiction-type municipality
python scripts/validate_source_packs.py
```

The validation command may fail for draft TODOs; that is acceptable if the error messages are clear.

### Out of Scope

- Fully automated source crawling.
- Paid search APIs.

## Task 11: Production Vector Store Rollout Plan

### Goal

Decide how Chroma/vector storage runs in production without surprise cost.

### Context

The app should keep database costs free for now. Chroma may be local, file-backed, hosted, or replaced by Postgres vector later. The implementation must be explicit about persistence, rebuilds, and deployment constraints.

### Relevant Files or References

- `apps/api/app/rag/vector_store.py`
- `apps/api/app/settings.py`
- `docs/deployment.md`
- Render deployment configuration
- Free database operating policy in `docs/public-launch/plan.md`

### Proposed Approach

- Document current vector provider options and chosen short-term provider.
- If using Chroma:
  - define persistence path
  - define rebuild command
  - define backup/rebuild expectations
  - define collection naming convention
  - define metadata filter capabilities
- If using file-backed vectors on Render:
  - verify whether the filesystem persists across deploys/restarts
  - if not persistent, make startup rebuild safe or use external storage
- Add an admin reindex checklist.

### Acceptance Criteria

- The team knows whether vectors persist in production.
- Reindexing source packs is repeatable.
- Metadata filtering is supported by the chosen vector backend.
- Cost remains within the free/low-cost policy until usage justifies upgrade.

### Source Reference

RAG is useful only if the vector store is reliable and explainable in production.

### Verify

```powershell
cd apps/api
pytest tests/test_rag_phase2.py -q
```

Also run a local reindex and inspect vector readiness from `/api/v1/ingestion/status`.

### Out of Scope

- Paid managed vector database migration.

## Task 12: End-to-End Supported and Unsupported Browser QA

### Goal

Make browser QA cover the full public launch behavior, not just page load.

### Context

`tests/e2e/public-launch-smoke.mjs` currently checks rendered copy and console errors. It should evolve into a real coverage test.

### Relevant Files or References

- `tests/e2e/public-launch-smoke.mjs`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `scripts/smoke_public_api.py`

### Proposed Approach

- Add local test mode helpers if needed.
- Cover:
  - signed-out landing with coverage summary and legal links
  - normal workspace in disabled/local mode
  - supported Blacksburg review using fixture address
  - unsupported Richmond or Christiansburg flow showing request CTA
  - Source Admin hidden for normal Supabase user mode
  - no console errors
- Keep secrets out of test output.
- Make the command accept `WEB_BASE_URL`.

### Acceptance Criteria

- Browser tests fail on console errors.
- Browser tests catch old `three-agent` / `3 agents` copy.
- Browser tests prove supported and unsupported paths render correctly.
- Tests are documented and runnable locally.

### Source Reference

Public launch needs repeatable QA after every deploy.

### Verify

```powershell
npm run test:e2e
```

### Out of Scope

- Full visual regression testing.

## Task 13: Production Deployment and Smoke Run

### Goal

Deploy the baseline, run production smoke checks, and confirm the app is ready for real users.

### Context

Frontend deploys on Vercel. Backend deploys on Render. The production backend URL is `https://zoning-agent-api.onrender.com`, and frontend URL is `https://zoning-agent-platform.vercel.app/`.

### Relevant Files or References

- `vercel.json`
- Render dashboard/config
- `scripts/smoke_public_api.py`
- `tests/e2e/public-launch-smoke.mjs`
- `.tmp/production-qa.env` for local ignored secrets

### Proposed Approach

- Deploy backend after migrations are ready.
- Deploy frontend after Vercel env vars are set:
  - `VITE_API_URL=https://zoning-agent-api.onrender.com`
  - `VITE_AUTH_MODE=supabase`
  - `VITE_SUPABASE_URL`
  - `VITE_SUPABASE_ANON_KEY`
- Set backend env vars:
  - `AUTH_PROVIDER=supabase`
  - `AUTH_REQUIRED=true`
  - `SUPABASE_JWT_SECRET`
  - `ADMIN_USER_EMAILS`
  - `PUBLIC_SIGNUPS_ENABLED`
  - free-tier limits
- Run public smoke:
  - health
  - auth `/me`
  - coverage endpoint
  - source readiness
  - supported intake/analyze
  - unsupported request CTA/API if test auth token exists
- Run browser smoke against production.

### Acceptance Criteria

- Production frontend no longer depends on shared beta key for public use.
- Production backend accepts real user auth.
- Public-supported jurisdictions are visible and answerable.
- Unsupported jurisdictions do not run compliance analysis and can be requested.
- No console errors in production browser smoke.
- Smoke scripts do not print tokens or secrets.

### Source Reference

The app needs to move from test website to production-ready public app.

### Verify

```powershell
python scripts/smoke_public_api.py
$env:WEB_BASE_URL="https://zoning-agent-platform.vercel.app"
npm run test:e2e
```

### Out of Scope

- Custom domain.
- Paid plans.

## Task 14: Ongoing Expansion Loop

### Goal

Create a recurring workflow for expanding coverage without context loss.

### Context

The US has thousands of zoning authorities. The project needs a repeatable operating loop, not a one-time ingestion sprint.

### Relevant Files or References

- `docs/public-launch/nationwide-expansion-strategy.md`
- `docs/public-launch/source-pack-spec.md`
- `docs/public-launch/document-acquisition-workflow.md`
- `services/ingestion/source_packs`
- `apps/api/tests/golden/scenarios.json`

### Proposed Approach

For each weekly or per-batch expansion:

1. Review top jurisdiction requests.
2. Pick 1-3 jurisdictions.
3. Create or update source pack.
4. Validate source pack.
5. Import and reindex locally.
6. Add golden scenarios.
7. Run backend tests.
8. If QA passes, update status to `qa_ready`.
9. If human review confirms, promote to `public_supported`.
10. Deploy and run smoke checks.

### Acceptance Criteria

- Every new jurisdiction follows the same checklist.
- Demand data is used for prioritization.
- No jurisdiction skips source validation or golden QA.
- Agents can resume from docs without reading old chats.

### Source Reference

This is the long-term replacement for the "big US documents folder" idea.

### Verify

For every batch:

```powershell
python scripts/validate_source_packs.py
cd apps/api
pytest tests/golden tests/test_services.py tests/test_jurisdiction_tool.py -q
cd ..\..
npm run build:web
npm run test:e2e
```

### Out of Scope

- Completing nationwide coverage in one sprint.

## Delegation Guidance

Safe subagent splits:

- Agent A: source-pack spec, validation script, document acquisition workflow.
- Agent B: vector metadata/filtering tests and RAG retrieval changes.
- Agent C: golden scenarios and first Virginia QA batch.
- Agent D: frontend admin backlog view and browser E2E expansion.

Coordination rules:

- Do not let multiple agents edit the same large frontend file at the same time unless one agent owns final integration.
- Do not let a research/source-pack agent promote coverage status.
- Do not let a vector/RAG agent weaken citation validation to make tests pass.
- Require every subagent to report files changed, tests run, and any unverifiable assumptions.

## Definition of Done for This Program Stage

The next stage is complete when:

- Source-pack schema is documented.
- Source-pack validation command exists.
- Vector retrieval is jurisdiction-filtered by metadata.
- Golden scenarios exist for the first expansion batch.
- Admins can see jurisdiction demand.
- Production deployment passes public auth and browser smoke.
- Blacksburg and Montgomery County remain public-supported.
- Christiansburg, Roanoke, and Roanoke County either reach `qa_ready` or remain honestly labeled as `source_indexed`.
- No user-facing copy implies nationwide zoning answers are available before QA.
