# Production Beta Handoff

Last updated: May 23, 2026

## Current Repo State

- Local repo: `C:\Users\abhih\Zoning-Agent-App`
- GitHub repo: `https://github.com/abhihari010/zoning-agent-platform`
- Main branch contains the production-readiness batch through `ba2902d` (`merge source coverage and frontend readiness`).
- Deployed frontend target: `https://zoning-agent-platform.vercel.app`
- Deployed API target: `https://zoning-agent-api.onrender.com`
- Primary planning docs:
  - `docs/production-beta-hardening/spec.md`
  - `docs/production-beta-hardening/plan.md`
  - `docs/production-beta-hardening/handoff.md`

## What Shipped In This Batch

- Issue #18: Postgres-backed persistence foundation with Alembic migrations, SQLAlchemy storage, and SQLite retained for local tests.
- Issue #19: Repository/service layer so app logic can use Postgres or SQLite without changing route behavior.
- Issue #20: Render/Supabase deployment documentation for free staging and paid production upgrade.
- Issue #21: Source readiness metadata, automatic seed/import/reindex support, and readiness warnings.
- Issue #22: Official Blacksburg source coverage replacing placeholder source URLs in supported seed data.
- Issue #23: Jurisdiction support states for Blacksburg, Montgomery County, Christiansburg, Roanoke, and Roanoke County.
- Issue #24: First expanded supported jurisdiction coverage for Montgomery County, VA, using official county and VDH sources.
- Issue #25: Rotatable beta access keys plus separate admin access for source write endpoints.
- Issue #26: Frontend visibility for jurisdiction status, source readiness, and source-admin access.
- Issue #27: Deployed beta smoke script for health, auth, source readiness, intake, analysis, evidence, and trace.
- Issue #28: Current handoff/runbook documentation.

Recent merge commits:

- `cf512bf` - `merge production persistence readiness`
- `7d87003` - `merge jurisdiction and access readiness`
- `ba2902d` - `merge source coverage and frontend readiness`

## Storage And Deployment Direction

Production code now expects `DATABASE_URL` to be the persistence source in deployed environments. `ZONING_DB_PATH` remains a local SQLite fallback only.

Current staging database:

- Provider: Supabase
- Project ref: `tzstkgifmftqcdguhshn`
- Region: `us-east-2`
- Plan intent: free staging only
- Render should use the Supabase session pooler URL because it is IPv4-compatible.

Never commit database passwords or full secret connection strings. If a full Supabase URL or password is pasted into chat or logs, rotate the database password in Supabase and update Render's `DATABASE_URL`.

Before real users or real customer data:

1. Move production to a paid Supabase or Render Postgres plan with backups.
2. Keep staging and production on separate database projects or instances.
3. Rotate the database password during cutover.
4. Run `alembic upgrade head` against the paid production database.
5. Confirm restore and rollback steps with the provider backup tooling.

## Required Runtime Configuration

Render API:

- `DATABASE_URL=<Supabase session pooler or paid Postgres URL>`
- `CORS_ALLOW_ORIGINS=https://zoning-agent-platform.vercel.app`
- `GOOGLE_MAPS_API_KEY=<restricted server key>`
- `BETA_ACCESS_KEY=<long random beta key>` or `BETA_ACCESS_KEYS=<label:key,label2:key2>`
- `ADMIN_ACCESS_KEY=<long random admin key for source writes>`
- `AI_PROVIDER=deterministic`
- `RAG_PROVIDER=hybrid_local`
- `EMBEDDING_PROVIDER=local`

Do not set `ZONING_DB_PATH` on Render. Leave `OPENAI_*` and `WATSONX_*` unset unless intentionally testing those providers.

Vercel frontend:

- `VITE_API_URL=https://zoning-agent-api.onrender.com`

The frontend stores beta and admin keys in browser `sessionStorage`; keys are not committed or stored in the repo.

## Database And Source Setup

Run migrations from the API app:

```powershell
cd C:\Users\abhih\Zoning-Agent-App\apps\api
$env:DATABASE_URL="<staging-or-production-postgres-url>"
alembic upgrade head
```

After deploy, seed/import and index sources:

1. Open the Vercel app.
2. Enter the beta access key.
3. Open Source Admin.
4. Enter the admin access key if write actions are enabled.
5. Import local documents if needed.
6. Run `Reindex sources`.
7. Confirm source readiness shows nonzero sources and chunks.

Supported source coverage now includes Blacksburg and Montgomery County. Christiansburg, Roanoke city, and Roanoke County are recognized but intentionally unsupported until official source coverage is added.

## Verification Commands

Local checks:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
npm run typecheck:web
npm run build:web

cd C:\Users\abhih\Zoning-Agent-App\apps\api
pytest -q
```

Secret and placeholder checks:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
rg "postgresql://[^\s]+:[^\[<\s][^@\s]+@|BETA_ACCESS_KEY=[A-Za-z0-9_*@!-]{8,}|ADMIN_ACCESS_KEY=[A-Za-z0-9_*@!-]{8,}" README.md .env.example render.yaml docs apps services -g "!apps/api/tests/**"
rg "example\.gov" apps\api\app\data services\ingestion apps\web packages
```

Deployed smoke test:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
$env:BETA_BASE_API_URL="https://zoning-agent-api.onrender.com"
$env:BETA_ACCESS_KEY="<private beta key>"
$env:BETA_TEST_SUPPORTED_ADDRESS="<supported Blacksburg or Montgomery County test address>"
$env:BETA_TEST_UNSUPPORTED_ADDRESS="<valid address in a recognized unsupported jurisdiction>"
python scripts\smoke_beta_api.py
```

The smoke script checks `/health`, beta auth failures/success, source readiness, reindex fallback, supported intake and analysis, citations/evidence, trace events, and unsupported-jurisdiction behavior.

## Known Limitations

- Free Supabase staging is not production-grade for real users because backups and retention are not sufficient for launch.
- Render free services can cold start; upgrade before time-sensitive beta usage.
- Google Maps is required for live address intake and suggestions.
- OpenAI and WatsonX providers are optional seams, not the recommended beta default yet.
- The frontend source admin can show source readiness, but full deployed browser E2E coverage is still a future improvement.
- Additional official source packs are still needed for Christiansburg, Roanoke city, and Roanoke County.

## Recommended Next Work

1. Confirm Render has the new `DATABASE_URL`, beta key, admin key, CORS origin, and Google Maps key.
2. Run `alembic upgrade head` against the deployed staging database after every schema change.
3. Deploy Vercel with `VITE_API_URL` pointed at Render.
4. Reindex sources in Source Admin and run `scripts\smoke_beta_api.py`.
5. Add official source packs for the remaining recognized unsupported jurisdictions.
6. Decide whether paid production uses Supabase or Render Postgres before inviting real beta users.
