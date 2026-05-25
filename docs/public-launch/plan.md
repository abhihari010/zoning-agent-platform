# Public Launch Implementation Plan

Last updated: May 24, 2026

## Purpose

Move Zoning Review Platform from a QA-only beta-key website into a real public application that people can use, while keeping infrastructure spend close to zero until real usage justifies paid upgrades.

This plan covers two near-term sprints:

1. Public access foundation: replace the shared beta gate with account-based access, protect user data, add operational guardrails, and keep the current free database posture.
2. Jurisdiction expansion and launch polish: make the product feel public-ready, expand supported coverage beyond the current Virginia starter set, and build the architecture for eventual nationwide coverage.

## Current Baseline

- Frontend: Vercel at `https://zoning-agent-platform.vercel.app`.
- Backend: Render at `https://zoning-agent-api.onrender.com`.
- Persistence: SQLAlchemy-backed storage with SQLite local fallback and Postgres support through `DATABASE_URL`.
- Current free database direction: Supabase project `tzstkgifmftqcdguhshn` is documented as free staging.
- Access today: shared `BETA_ACCESS_KEY` / `BETA_ACCESS_KEYS`, plus separate `ADMIN_ACCESS_KEY` for source writes.
- Existing tables include `sessions`, `projects`, `analyses`, `audit_events`, `feedback`, `sources`, `source_chunks`, `beta_access_events`, and `jurisdictions`.
- Current supported jurisdictions: Blacksburg, VA and Montgomery County, VA.
- Recognized but unsupported jurisdictions: Christiansburg, VA; Roanoke, VA; Roanoke County, VA.

## Guiding Decisions

- Keep the database free for now by using the current free Supabase Postgres project as production-beta storage, with explicit usage caps and an upgrade trigger.
- Do not promise nationwide zoning answers immediately. Build the data model and onboarding flow for all US jurisdictions, but only mark jurisdictions as `supported` when official source coverage, district mapping, and QA scenarios exist.
- Replace the beta key with authentication before broad public access. A shared secret is not enough for real users because projects, feedback, quota, support, and abuse handling need user identity.
- Prefer Supabase Auth for this phase because the app already has Supabase/Postgres context and the free tier can cover early usage. Revisit Clerk/Auth0 later only if product polish or enterprise requirements justify it.
- Keep admin source management out of the normal user workspace. Public users should never see or carry an admin key.
- Keep deterministic/local analysis for launch unless a paid LLM budget is approved. The first public launch should prioritize trusted citations and jurisdiction coverage over model sophistication.

## Free Database Operating Policy

Use the free database as long as all of the following are true:

- Data is low-volume early-access data.
- Daily active users are small enough that cold starts and free-tier limits do not degrade the experience.
- No contractual customer, paid usage, or sensitive document upload commitment exists.
- Backups are manually exported at least weekly and before every schema migration.
- Restore from export has been tested once in a separate local or staging database.

Upgrade trigger:

- More than 25 regular users, paid users, or municipal/contractual users.
- More than 1 GB storage or any provider warning about free-tier limits.
- User data becomes business-critical.
- Need for point-in-time recovery, formal retention, or support SLA.

## Sprint 1: Public Access Foundation

Goal: Let real people create accounts, run reviews, and return to their work without using a shared beta key, while preserving free database infrastructure and locking down admin capabilities.

Suggested duration: 1-2 weeks.

### Task 1: Choose and Document Auth Architecture

Goal: Decide the account system and document the request/auth contract before coding.

Context:
The backend currently gates `/api/v1/*` with `X-Beta-Access-Key` middleware in `apps/api/app/main.py`. The frontend stores beta/admin keys in `sessionStorage` in `apps/web/src/api.ts`. Real users need identity, project ownership, and role separation.

Relevant files or references:

- `apps/api/app/main.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/database.py`
- `apps/web/src/api.ts`
- `docs/production-beta-hardening/handoff.md`

Proposed approach:

- Use Supabase Auth for Sprint 1.
- Frontend signs users in with email magic link or email/password.
- Frontend sends `Authorization: Bearer <jwt>` to the FastAPI backend.
- Backend validates Supabase JWT using JWKS or configured JWT secret.
- Backend attaches `user_id`, `email`, and `role` to each request.
- Keep `BETA_ACCESS_KEY` only as a temporary invite/kill-switch option during migration, not as the public access model.
- Define roles: `user`, `admin`.

Acceptance criteria:

- A short design note exists describing auth provider, token validation, roles, migration behavior, and local-development behavior.
- The plan explicitly says whether beta keys remain enabled during the transition.
- The plan defines how admin users are identified.

Source reference:
User request to move beyond a beta-key test website while keeping the database free.

Verify:

- Review the design note with the repo owner before implementation.

Out of scope:

- Billing, subscriptions, SSO, organization accounts.

### Task 2: Add User Identity Schema

Goal: Store ownership and role metadata without breaking existing project records.

Context:
Current projects are session-owned, not user-owned. Existing tables can persist analyses and feedback, but they do not attach records to an authenticated user.

Relevant files or references:

- `apps/api/app/database.py`
- `apps/api/app/repositories.py`
- `apps/api/alembic/versions/`
- `apps/api/tests/test_database.py`
- `apps/api/tests/test_repositories.py`

Proposed approach:

- Add a `users` table keyed by Supabase `user_id` UUID string.
- Add nullable `user_id` columns to `sessions`, `projects`, `analyses` if needed, `feedback`, and `audit_events`.
- Add `role`, `email`, `created_at`, `last_seen_at`, and `disabled_at` fields to `users`.
- Add indexes for `projects.user_id`, `feedback.user_id`, and `audit_events.user_id`.
- Keep nullable ownership columns initially so legacy beta-created records keep working.
- Add repository methods for upserting current user, listing user projects, and enforcing ownership.

Acceptance criteria:

- Alembic migration applies cleanly to Postgres and SQLite test databases.
- Existing tests still pass without auth.
- New repository tests prove projects and feedback can be associated with a user.
- Existing beta records do not need backfill to remain readable by admin tools.

Source reference:
Current schema in `apps/api/app/database.py` has project persistence but no user ownership.

Verify:

```powershell
cd apps/api
pytest tests/test_database.py tests/test_repositories.py -q
```

Out of scope:

- Public user profile pages.
- Team or organization ownership.

### Task 3: Implement Backend Auth Middleware

Goal: Replace public API beta-key dependence with authenticated user requests.

Context:
`require_beta_access_key` currently protects all `/api/v1/*` requests. The new path should accept Supabase JWTs and preserve local/test ergonomics.

Relevant files or references:

- `apps/api/app/main.py`
- `apps/api/app/settings.py`
- `apps/api/app/routers/api.py`
- `apps/api/tests/test_api.py`
- `apps/api/tests/test_settings.py`

Proposed approach:

- Add settings:
  - `AUTH_PROVIDER=supabase|disabled`
  - `SUPABASE_PROJECT_URL`
  - `SUPABASE_JWT_SECRET` or `SUPABASE_JWKS_URL`
  - `AUTH_REQUIRED=true|false`
  - `ADMIN_USER_EMAILS=comma,separated`
- Implement a dependency or middleware that validates JWTs when `AUTH_REQUIRED=true`.
- Attach auth context to `request.state.user`.
- Keep `/health` unauthenticated.
- Keep local tests easy with `AUTH_REQUIRED=false`.
- During migration, allow either valid JWT or valid beta key when `BETA_ACCESS_KEYS` is configured, but mark beta-key access as legacy.
- Audit accepted/failed auth attempts without storing raw tokens.

Acceptance criteria:

- Missing auth returns `401` on protected routes when auth is required.
- Invalid JWT returns `403`.
- Valid JWT can call `/api/v1/sessions`, `/api/v1/projects/intake`, `/api/v1/projects/{id}/analyze`.
- `/health` remains unauthenticated.
- Legacy beta key still works only when explicitly configured.
- No raw JWT or beta key is logged or persisted.

Source reference:
Current beta-key middleware in `apps/api/app/main.py`.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py tests/test_settings.py -q
```

Out of scope:

- OAuth provider UI.
- Billing enforcement.

### Task 4: Enforce Project Ownership and Admin Roles

Goal: Prevent one authenticated user from reading or modifying another user's projects, analyses, feedback, or traces.

Context:
Current route handlers fetch projects by project ID only. Public usage requires ownership checks. Trace and source write actions must be admin-only.

Relevant files or references:

- `apps/api/app/routers/api.py`
- `apps/api/app/repositories.py`
- `apps/api/app/database.py`
- `apps/api/tests/test_api.py`

Proposed approach:

- Create helper dependencies:
  - `require_user`
  - `require_admin`
  - `require_project_owner_or_admin`
- Bind `session_id` and `project_id` to `user_id` on create.
- Apply ownership checks to:
  - `GET /projects/{project_id}/result`
  - `POST /projects/{project_id}/analyze`
  - `GET /projects/{project_id}/trace`
  - `POST /projects/{project_id}/feedback`
- Convert Source Admin endpoints from `ADMIN_ACCESS_KEY` to `require_admin`, while retaining `ADMIN_ACCESS_KEY` only for emergency migration if configured.
- Add `GET /api/v1/projects` for the authenticated user's project history.

Acceptance criteria:

- User A cannot access User B's project result, analysis, trace, or feedback endpoint.
- Admin can access trace/source management.
- Normal users cannot call source write/reindex/import endpoints.
- User project list returns only the authenticated user's projects.
- Legacy unauthenticated local tests remain possible when auth is disabled.

Source reference:
Current route handlers in `apps/api/app/routers/api.py`.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py -q
```

Out of scope:

- Organization-level sharing.
- Public share links.

### Task 5: Add Frontend Sign-In and Authenticated API Client

Goal: Replace the beta-key screen with a real sign-in flow and send bearer tokens to the backend.

Context:
The frontend currently uses `sessionStorage` keys and shows a private beta gate when `VITE_API_URL` is non-localhost.

Relevant files or references:

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/web/package.json`
- `README.md`

Proposed approach:

- Add Supabase JS client to the web app.
- Add environment variables:
  - `VITE_SUPABASE_URL`
  - `VITE_SUPABASE_ANON_KEY`
  - `VITE_AUTH_MODE=supabase|beta|disabled`
- Create a sign-in screen for email magic link or email/password.
- Store auth session through Supabase client, not custom sessionStorage.
- Update `requestHeaders()` to attach `Authorization: Bearer <access_token>`.
- Keep beta mode available only for local/QA with `VITE_AUTH_MODE=beta`.
- Add signed-in user menu with sign out.
- Hide Source Admin unless the backend reports admin role or an admin profile flag.

Acceptance criteria:

- Public production mode shows sign-in, not beta-key unlock.
- Authenticated users can run the existing zoning review flow.
- Signed-out users cannot call protected API routes.
- Source Admin is not visible to normal users.
- Local beta mode still supports the existing QA workflow.

Source reference:
Current beta-key API client in `apps/web/src/api.ts`.

Verify:

```powershell
npm run typecheck:web
npm run build:web
```

Out of scope:

- Multi-provider login.
- Account settings page beyond sign out.

### Task 6: Add Saved Projects Workspace

Goal: Make the app useful after the first session by letting users return to prior reviews.

Context:
The backend already stores projects and analyses. The frontend currently behaves like a single active workspace.

Relevant files or references:

- `apps/api/app/routers/api.py`
- `apps/api/app/repositories.py`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`

Proposed approach:

- Add backend endpoint `GET /api/v1/projects`.
- Return project summary fields: project ID, normalized address, jurisdiction, district, created date, latest decision, confidence, status.
- Add frontend "Projects" view/sidebar for signed-in users.
- Let users open a saved project result.
- Keep editing/reanalysis out of the first pass unless already supported naturally.

Acceptance criteria:

- A signed-in user sees a list of their prior projects.
- Opening a project shows its saved result if analysis exists.
- Empty state is clear for first-time users.
- Users cannot see projects from another account.

Source reference:
Current persisted `projects` and `analyses` tables.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py tests/test_repositories.py -q
npm run build:web
```

Out of scope:

- Project folders, collaboration, sharing, editing history.

### Task 7: Add Free-Tier Usage Guardrails

Goal: Keep infrastructure free while preventing abuse and surprise quota exhaustion.

Context:
The user wants to keep the database free until real users appear. Public access increases abuse and cost risk.

Relevant files or references:

- `apps/api/app/database.py`
- `apps/api/app/routers/api.py`
- `apps/api/app/repositories.py`
- `apps/api/app/settings.py`

Proposed approach:

- Add simple database-backed usage counters:
  - requests per user per day
  - analyses per user per day
  - address suggestions per user per day if feasible
- Add settings:
  - `DAILY_ANALYSIS_LIMIT_FREE`
  - `DAILY_PROJECT_LIMIT_FREE`
  - `PUBLIC_SIGNUPS_ENABLED`
- Rate limit analysis and intake before expensive Google/API calls where possible.
- Add a friendly frontend message when limits are reached.
- Add admin-visible metrics endpoint for counts by day.

Acceptance criteria:

- A user exceeding the configured daily analysis limit gets a clear `429`.
- Limits are configurable by environment.
- Admin can see aggregate daily usage without exposing secrets.
- Local tests can disable limits.

Source reference:
Free database constraint in the current user request.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py -q
```

Out of scope:

- Stripe billing.
- Distributed edge rate limiting.

### Task 8: Add Minimal Observability and Operational Checks

Goal: Know when production is broken before users report it.

Context:
There is a smoke script and `/health`, but public access needs repeatable operational checks and error visibility.

Relevant files or references:

- `scripts/smoke_beta_api.py`
- `apps/api/app/startup.py`
- `docs/deployment.md`
- Vercel and Render dashboards

Proposed approach:

- Create a public smoke script variant that uses auth instead of beta key.
- Keep the old beta smoke script for migration until beta mode is retired.
- Add structured server logs for auth failures, analysis failures, unsupported jurisdictions, and source readiness warnings.
- Add a scheduled manual or automated daily smoke run.
- Document the smoke run command and expected outputs.
- Add alert checklist for Render health, Vercel deployment, and database quota.

Acceptance criteria:

- Smoke test verifies auth, health, source readiness, supported intake, analysis, citations, feedback, and unsupported jurisdiction handling.
- Smoke test never prints access tokens or secrets.
- Operational runbook includes where to check logs and what to do on failure.

Source reference:
Existing smoke testing documented in `README.md` and `docs/production-beta-hardening/handoff.md`.

Verify:

```powershell
python scripts/smoke_public_api.py
```

Out of scope:

- Paid observability vendors.
- Full incident management process.

### Sprint 1 Exit Criteria

- Users can sign up/sign in without a beta key.
- Backend associates projects, analyses, feedback, and audit records with a user.
- Normal users cannot access Source Admin.
- Users can return to saved projects.
- Free-tier limits and upgrade triggers are documented and enforced.
- Production browser QA passes with auth mode.
- The old beta-key flow is retained only as a temporary QA/migration mode.

## Sprint 2: Jurisdiction Expansion and Launch Polish

Goal: Make the product trustworthy and polished enough for a wider public launch, while building a scalable path toward all US jurisdictions.

Suggested duration: 2-4 weeks for launch polish plus first expansion; nationwide coverage is an ongoing data program, not a single sprint deliverable.

### Task 9: Redesign Jurisdiction Coverage Model for National Scale

Goal: Represent every US jurisdiction as discoverable, but only some as answerable.

Context:
Current jurisdiction data is a small JSON list. Nationwide expansion requires a more formal hierarchy: state, county, municipality, unincorporated areas, source status, and launch status.

Relevant files or references:

- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/jurisdictions.py`
- `apps/api/app/database.py`
- `apps/api/app/models.py`
- `apps/api/tests/test_jurisdiction_tool.py`

Proposed approach:

- Add a jurisdiction status model:
  - `unsupported`: recognized but no answer
  - `source_discovery`: official sources identified
  - `source_indexed`: sources imported and chunked
  - `qa_ready`: golden scenario tests pass
  - `public_supported`: visible as supported in product
- Add fields:
  - `state_fips`, `county_fips`, `place_fips`
  - `jurisdiction_type`
  - `parent_jurisdiction_id`
  - `coverage_status`
  - `official_source_urls`
  - `zoning_map_url`
  - `planning_contact`
  - `last_verified_at`
- Store jurisdictions in Postgres while retaining JSON seed data.
- Add seed/import path for jurisdiction records.

Acceptance criteria:

- Current VA jurisdictions migrate into the new model.
- Unsupported recognized jurisdictions still produce clear unsupported messages.
- Supported jurisdictions require `public_supported`, not just a boolean.
- The frontend can display coverage state near the address field.

Source reference:
User goal to eventually expand to all of America.

Verify:

```powershell
cd apps/api
pytest tests/test_jurisdiction_tool.py tests/test_api.py -q
```

Out of scope:

- Loading all US jurisdictions in this task.

### Task 10: Build Jurisdiction Source Pack Format

Goal: Make adding a jurisdiction repeatable instead of hand-editing ad hoc source records.

Context:
Nationwide support depends on official source collection and metadata quality. Each jurisdiction needs a consistent package of code, zoning map, permit, contact, and health/fire/building sources.

Relevant files or references:

- `apps/api/app/data/source_registry.json`
- `services/ingestion`
- `apps/api/app/ingestion.py`
- `docs/production-beta-hardening/plan.md`

Proposed approach:

- Define `services/ingestion/source_packs/<state>/<jurisdiction_id>/manifest.json`.
- Manifest includes:
  - jurisdiction metadata
  - official URLs
  - source documents
  - effective dates
  - source type
  - districts
  - use tags
  - verification notes
- Add importer that validates manifests before inserting sources.
- Add metadata completeness checks that block `public_supported` when required fields are missing.
- Include examples for Blacksburg and Montgomery County.

Acceptance criteria:

- Blacksburg and Montgomery County can be represented as source packs.
- Importer rejects a pack with missing jurisdiction ID, source URL, title, or effective date unless explicitly marked as curated local fallback.
- Reindex after import creates chunks with jurisdiction metadata.
- Source Admin shows pack/import status.

Source reference:
Need to scale source coverage beyond hand-maintained seed entries.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py tests/test_rag_phase2.py -q
```

Out of scope:

- Automated web crawling.
- Legal interpretation of source terms.

### Task 11: Add First Expansion Batch for Virginia

Goal: Expand beyond the current supported jurisdictions with a focused, QA-able regional batch.

Context:
The app already recognizes Christiansburg, Roanoke, and Roanoke County as unsupported. These are natural next candidates before attempting national coverage.

Relevant files or references:

- `apps/api/app/data/jurisdictions.json`
- `apps/api/app/data/source_registry.json`
- `apps/api/tests/golden/scenarios.json`
- `apps/api/tests/test_services.py`
- `docs/production-beta-hardening/handoff.md`

Proposed approach:

- Add official source packs for:
  - Christiansburg, VA
  - Roanoke, VA
  - Roanoke County, VA
- For each jurisdiction, collect:
  - zoning ordinance/code
  - zoning map/GIS source
  - planning/zoning permit page
  - building permit page
  - health/fire review source where relevant
  - planning department contact
- Add at least one golden scenario per jurisdiction.
- Keep jurisdictions as `source_indexed` until QA passes.
- Promote only passing jurisdictions to `public_supported`.

Acceptance criteria:

- Each expansion jurisdiction has official source metadata and no placeholder URLs.
- Each jurisdiction has at least one supported happy-path golden scenario.
- Unsupported addresses outside supported jurisdictions still refuse gracefully.
- Source readiness reports all public-supported jurisdictions as indexed.

Source reference:
Existing recognized unsupported Virginia jurisdictions in `apps/api/app/data/jurisdictions.json`.

Verify:

```powershell
cd apps/api
pytest tests/test_services.py tests/test_orchestrator.py -q
```

Out of scope:

- All Virginia jurisdictions.
- All use categories.

### Task 12: Add National Discovery Data, Not National Answers

Goal: Let users enter addresses anywhere in the United States and receive honest coverage status.

Context:
The long-term goal is all of America. The immediate product should recognize location broadly but only answer where source packs are ready.

Relevant files or references:

- `apps/api/app/services.py`
- `apps/api/app/tools/address_tool.py`
- `apps/api/app/tools/jurisdiction_tool.py`
- `apps/web/src/App.tsx`

Proposed approach:

- Remove Blacksburg-biased autocomplete in public mode and bias by user input/country instead.
- Use Google address components to derive city, county, state, and country for US addresses.
- Add a fallback jurisdiction ID shape for unknown jurisdictions, such as `us-<state>-<county>-<place>`.
- Return `unsupported` with planning contact/source discovery status where no source pack exists.
- Add frontend copy: "We recognize this jurisdiction, but source coverage is not ready yet."
- Add "Request support for this jurisdiction" CTA.

Acceptance criteria:

- US addresses outside supported jurisdictions do not look like invalid addresses.
- Unsupported jurisdiction results are differentiated from invalid/ambiguous addresses.
- User can request support for an unsupported jurisdiction.
- The backend does not run compliance analysis for unsupported jurisdictions.

Source reference:
User goal to expand to all of America while preserving trust.

Verify:

```powershell
cd apps/api
pytest tests/test_services.py tests/test_jurisdiction_tool.py -q
npm run build:web
```

Out of scope:

- Actual compliance answers for unsupported jurisdictions.

### Task 13: Create Jurisdiction Request and Triage Flow

Goal: Turn user demand into a prioritized source-coverage backlog.

Context:
Nationwide expansion should be demand-led. The free database can store lightweight requests without committing to immediate support.

Relevant files or references:

- `apps/api/app/database.py`
- `apps/api/app/routers/api.py`
- `apps/web/src/App.tsx`

Proposed approach:

- Add `jurisdiction_requests` table with user ID, normalized address, jurisdiction fields, requested use type, optional comment, and created date.
- Add `POST /api/v1/jurisdiction-requests`.
- Add CTA in unsupported jurisdiction UI.
- Add admin list endpoint for request counts by jurisdiction.
- Use this data to decide which source packs to build next.

Acceptance criteria:

- Signed-in users can request support for unsupported jurisdictions.
- Duplicate requests by the same user and jurisdiction are deduplicated or idempotent.
- Admin can see top requested jurisdictions.
- No request stores raw secrets or unnecessary sensitive data.

Source reference:
Nationwide expansion should prioritize real user demand.

Verify:

```powershell
cd apps/api
pytest tests/test_api.py tests/test_database.py -q
```

Out of scope:

- Email notifications.
- CRM integration.

### Task 14: Polish Public Landing and Onboarding

Goal: Make the first experience explain what the app can and cannot do.

Context:
The current frontend is a workspace, not a launch-ready public product. It should not over-promise national coverage.

Relevant files or references:

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/web/src/index.css`

Proposed approach:

- Add a signed-out landing/onboarding view with:
  - product name and clear value proposition
  - supported coverage summary
  - "not legal advice / verify with planning office" statement
  - sign-in CTA
- After sign-in, start in the review workspace.
- Add coverage badge near address input.
- Add trust panel showing sources, last verified date, and jurisdiction support level.
- Improve empty/error states for invalid address, unsupported jurisdiction, and source-not-ready.

Acceptance criteria:

- Users understand supported coverage before running a review.
- Unsupported jurisdictions have a useful CTA instead of a dead end.
- The workspace does not look like an internal beta tool.
- Existing happy path remains fast and clear.

Source reference:
User asks for launch polish and public availability.

Verify:

```powershell
npm run typecheck:web
npm run build:web
```

Out of scope:

- Full marketing site.
- Payment pages.

### Task 15: Add Public Legal and Privacy Pages

Goal: Provide minimum public-facing legal and privacy disclosures before onboarding users.

Context:
The app handles addresses, project descriptions, analyses, and feedback. Public users need terms and privacy expectations even before paid launch.

Relevant files or references:

- `apps/web/src/App.tsx`
- `README.md`
- `docs/deployment.md`

Proposed approach:

- Add static pages or routes for:
  - Terms of Use
  - Privacy Policy
  - Disclaimer
- Clearly state:
  - not legal advice
  - not official municipal approval
  - data stored for saved projects and product improvement
  - how users can request deletion
  - supported jurisdictions may change
- Add footer links in signed-out and signed-in views.

Acceptance criteria:

- Terms, privacy, and disclaimer are reachable without sign-in.
- The review workflow links to the disclaimer before analysis.
- Copy does not imply official government affiliation.

Source reference:
Public launch readiness for a zoning guidance app.

Verify:

```powershell
npm run build:web
```

Out of scope:

- Lawyer-approved final language. Human legal review remains required before broad public launch.

### Task 16: Add Launch QA Matrix and Browser E2E Coverage

Goal: Prevent regressions across auth, supported analysis, unsupported jurisdictions, and admin boundaries.

Context:
Manual production QA passed after redeploy. Public launch needs repeatable browser tests.

Relevant files or references:

- `.tmp/production-qa.spec.js` from manual QA pattern
- `scripts/smoke_beta_api.py`
- `apps/web`
- `apps/api/tests`

Proposed approach:

- Add committed Playwright test setup if acceptable for the repo.
- Cover:
  - signed-out landing
  - sign-in mock or test auth mode
  - supported review
  - unsupported jurisdiction request CTA
  - saved project list
  - admin-only source management hidden from normal user
  - no console errors
- Add API smoke script for production public auth.
- Add docs for local and production test env variables.

Acceptance criteria:

- CI/local command can run the browser suite.
- Browser suite covers at least one supported and one unsupported jurisdiction.
- Tests do not print secrets.
- Console errors fail the suite.

Source reference:
Production QA requirements from the preceding deployment work.

Verify:

```powershell
npm run build:web
cd apps/api
pytest -q
```

Plus the new browser test command defined by this task.

Out of scope:

- Visual regression testing.

### Task 17: Define Nationwide Expansion Operating Model

Goal: Make "all of America" a tractable data and QA program instead of a vague feature.

Context:
The US has thousands of zoning authorities. Many zoning rules live at municipal level, county level, special district level, or in PDFs/GIS systems. Nationwide support requires staged coverage and source verification.

Relevant files or references:

- `docs/public-launch/plan.md`
- `services/ingestion`
- `apps/api/app/data/jurisdictions.json`
- `apps/api/tests/golden/scenarios.json`

Proposed approach:

- Create a coverage backlog structure:
  - state
  - jurisdiction
  - demand count
  - official sources found
  - source pack status
  - QA status
  - public support status
- Define expansion tiers:
  - Tier 0: recognized only, no answer
  - Tier 1: official source links and planning contact
  - Tier 2: indexed source pack, internal QA only
  - Tier 3: public-supported common-use reviews
  - Tier 4: deeper parcel/GIS integration
- Prioritize by user demand, population, and source availability.
- Add a rule: no jurisdiction becomes public-supported without at least one golden scenario and no placeholder sources.

Acceptance criteria:

- A nationwide coverage strategy doc exists.
- The doc defines what "supported" means.
- The doc defines how to promote/demote a jurisdiction.
- The doc includes the first 10 target jurisdictions or target metros based on expected users.

Source reference:
User goal to expand to all of America.

Verify:

- Review the strategy doc and confirm target geography for the next expansion batch.

Out of scope:

- Completing national coverage in one sprint.

### Sprint 2 Exit Criteria

- Product presents as a public app, not a QA beta.
- Signed-in users understand coverage before relying on a result.
- Unsupported US jurisdictions are recognized and routed into a request flow.
- At least one new source-backed jurisdiction beyond the current two is promoted to public-supported, or all three current VA unsupported jurisdictions are source-indexed and ready for QA.
- Source pack format exists and can be used for repeatable jurisdiction onboarding.
- Launch QA matrix covers auth, supported review, unsupported review, saved projects, and admin boundaries.
- Nationwide expansion strategy is documented with tiered coverage statuses.

## Post-Sprint Backlog

- Paid infrastructure cutover once upgrade trigger is met.
- Billing or paid plans.
- Organization/team accounts.
- Human expert review marketplace or escalation workflow.
- Automated official-source monitoring and change detection.
- Parcel-level GIS integrations beyond Google address components.
- OpenAI or other LLM provider rollout with cost controls.
- Custom domain and brand/SEO work.
- Email notifications for jurisdiction support requests.
