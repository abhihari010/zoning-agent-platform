# Production Readiness Runbook

Last updated: June 1, 2026

## Architecture

- Frontend: Vercel project `zoning-agent-platform` at `https://zoning-agent-platform.vercel.app`.
- Backend: Render web service `zoning-agent-api` at `https://zoning-agent-api.onrender.com`.
- Database: Supabase free Postgres for public beta through `DATABASE_URL`.
- Retrieval: `hybrid_local` RAG over a **Qdrant** vector index (`VECTOR_PROVIDER=qdrant`), embeddings via **Gemini**, analysis via **Groq**. SQL source chunks remain the rebuildable source of truth; Qdrant is reindexed from them via the offline retag script.
- Auth: Supabase Auth bearer tokens. Beta keys are temporary QA/migration access only.

## Environment Matrix

Local:

- `APP_ENV=local` or unset.
- `AUTH_PROVIDER=disabled`, `AUTH_REQUIRED=false`.
- SQLite fallback through `ZONING_DB_PATH`.
- No Google, Supabase, OpenAI, WatsonX, Render, or Vercel credential required for tests.

CI:

- Runs pytest, source-pack validation, public-support guard, source freshness, web typecheck/build, browser fixture smoke, and `git diff --check`.
- Must not use production secrets.

Render production:

- `APP_ENV=production`
- `DATABASE_URL=<Supabase pooler URL>`
- `AUTH_PROVIDER=supabase`
- `AUTH_REQUIRED=true`
- `SUPABASE_PROJECT_URL=<Supabase project URL>`
- `SUPABASE_JWT_SECRET=<Supabase JWT secret>`
- `GOOGLE_MAPS_API_KEY=<restricted Google Maps key>`
- `CORS_ALLOW_ORIGINS=https://zoning-agent-platform.vercel.app`
- `AI_PROVIDER=groq`
- `GROQ_API_KEY=<Groq key>`
- `RAG_PROVIDER=hybrid_local`
- `EMBEDDING_PROVIDER=gemini`
- `GEMINI_API_KEY=<Gemini key>`
- `VECTOR_PROVIDER=qdrant`
- `QDRANT_URL=<Qdrant cluster URL>`
- `QDRANT_API_KEY=<Qdrant key>`
- `STARTUP_REINDEX_ENABLED=false` (boot-time reindex blocks Render's port scan — keep OFF; retag via the offline `scripts/update_source_classification.py`)
- `CORS_ALLOW_ORIGIN_REGEX=https://zoning-agent-platform[^.]*\.vercel\.app` (covers Vercel previews + production)
- Optional during migration: `BETA_ACCESS_KEYS`, `ADMIN_ACCESS_KEY`, `ADMIN_USER_EMAILS`

> Render is **blueprint-synced** via `render.yaml`. Dashboard edits get reset on the next deploy — change provider/env values in `render.yaml`, not the dashboard. Provider/DB secrets (`GROQ_API_KEY`, `GEMINI_API_KEY`, `QDRANT_API_KEY`, `DATABASE_URL` password) live only in the dashboard/secret store, never in the repo.

Vercel production:

- `VITE_API_URL=https://zoning-agent-api.onrender.com`
- `VITE_AUTH_MODE=supabase`
- `VITE_SUPABASE_URL=<Supabase project URL>`
- `VITE_SUPABASE_ANON_KEY=<Supabase anon key>`

## Deploy Checklist

1. Confirm CI is green on the candidate commit.
2. Export or back up Supabase data before migrations.
3. Confirm Render env vars match the production matrix.
4. Confirm Vercel env vars match the production matrix.
5. Deploy or merge to `main`.
6. Confirm Render service `srv-d87tlet7vvec7387j0og` is not suspended and still uses health path `/health`.
7. Confirm Vercel latest production deployment is `READY`.
8. Run source checks:

```powershell
python scripts\validate_source_packs.py
python scripts\check_public_support_candidates.py blacksburg-va montgomery-county-va
python scripts\check_source_freshness.py --max-age-days 90
```

9. Run config smoke:

```powershell
python scripts\check_production_config.py --api-url https://zoning-agent-api.onrender.com --web-origin https://zoning-agent-platform.vercel.app
```

10. Run authenticated API smoke with a dedicated Supabase smoke user:

```powershell
$env:PUBLIC_BASE_API_URL="https://zoning-agent-api.onrender.com"
$env:PUBLIC_AUTH_TOKEN="<redacted smoke user token>"
$env:PUBLIC_TEST_SUPPORTED_ADDRESS="<supported address>"
$env:PUBLIC_TEST_UNSUPPORTED_ADDRESS="<unsupported address>"
python scripts\smoke_public_api.py
```

11. Run browser smoke:

```powershell
$env:WEB_BASE_URL="https://zoning-agent-platform.vercel.app"
$env:E2E_MODE="live"
npm run test:e2e
```

## Rollback

1. Redeploy the previous Vercel production deployment.
2. Redeploy the previous Render commit or revert the offending commit on `main`.
3. If schema/data migration caused damage, restore from Supabase export/backup.
4. Rotate any exposed database, Supabase, Google, beta, or admin secrets immediately.
5. Re-run `check_production_config.py` and `smoke_public_api.py`.

## Backups And Upgrade Triggers

While using Supabase free:

- Export before every migration.
- Export weekly while real testers exist.
- Test restore once before inviting non-internal users.

Upgrade before:

- More than 25 regular testers.
- Any paid, contractual, municipal, or SLA-bound user.
- More than 1 GB storage or provider quota warning.
- Any need for point-in-time recovery, formal retention, or business-critical data.

## Incidents

API down:

- Check Render service health, recent deploy, and `/health`.
- Check `/ready` for database/source/vector warnings.
- Roll back Render if the latest deploy introduced the failure.

Frontend down:

- Check Vercel latest production deployment, domain status, and browser smoke.
- Roll back Vercel if needed.

Auth broken:

- Verify `AUTH_PROVIDER`, `AUTH_REQUIRED`, `SUPABASE_PROJECT_URL`, `SUPABASE_JWT_SECRET`.
- Run `/api/v1/me` without auth; production should return `401`.
- Rotate Supabase JWT secret only with coordinated Render update.

Source readiness broken:

- Run source pack validation and freshness checks.
- Run admin reindex after source updates.
- Do not promote jurisdictions without golden QA.

Citation quality issue:

- Demote affected jurisdiction below `public_supported`.
- Add or fix source pack metadata and golden scenario.
- Re-run golden tests before restoring support.

Quota or abuse issue:

- Confirm daily project/analysis limits.
- Temporarily lower limits if necessary.
- Remove beta keys before broad public launch.

## CI Expectations

Every PR should pass:

- Backend pytest.
- Source pack validation and public-support candidate guard.
- Source freshness check.
- Web typecheck/build.
- Browser fixture smoke.
- Whitespace hygiene.
