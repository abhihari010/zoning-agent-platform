# Production Postgres Durability & Cutover Runbook

Last updated: July 3, 2026

## 1. Why / Current Risk

Production (`zoning-agent-api` on Render) currently points `DATABASE_URL` at a
**Supabase staging project's session pooler URL** with **no automated
backups**. Every user account, project, analysis, and feedback row lives only
in that one database. A dropped table, a bad migration, or Supabase reclaiming
the staging project loses all of it with no recovery path. This must move to a
durable, paid Postgres with automated backups (and PITR) before real/revenue
users land.

## 2. Target Options

| Option | Data migration required? | Auth impact | Backups/PITR | Notes |
| --- | --- | --- | --- | --- |
| **(a) Upgrade existing Supabase project to Pro** | None — in place | None — same project | Yes, once upgraded | **RECOMMENDED**. Zero data movement, zero auth risk. Check current Supabase pricing before committing to a plan tier. |
| (b) New dedicated Postgres (Render Postgres, Neon, etc.), keep Supabase Auth where it is | Yes — app schema only | None if done correctly (see §note below) | Yes, provider-dependent | Use if staging Supabase project itself is unsuitable long-term (e.g. wrong region, org). More moving parts than (a). |
| (c) New Supabase project | Yes — app schema + auth | **High** — auth users live in the old project's `auth` schema; `users.user_id` values are Supabase `sub` claims tied to that project | Yes | Avoid unless there's a specific reason to leave the old project entirely. Auth migration is out of scope for this runbook. |

Default recommendation: **(a)**. It eliminates the migration steps in §5
entirely — upgrade the plan, turn on backups/PITR, done. Sections 5–8 below
are written for the general case (b), since (a) needs no data cutover; skip to
§8 (backup/restore drill) if you choose (a).

## 3. What Must Move vs What Is Rebuildable

All tables are defined in `apps/api/app/database.py` (Table() definitions,
lines 29–201).

| Table | Rebuildable? | How |
| --- | --- | --- |
| `sessions` | No | User-generated — must migrate |
| `users` | No | User-generated — must migrate |
| `projects` | No | User-generated — must migrate |
| `analyses` | No | User-generated — must migrate |
| `audit_events` | No | User-generated — must migrate |
| `feedback` | No | User-generated — must migrate |
| `beta_access_events` | No | User-generated — must migrate |
| `usage_events` | No | User-generated — must migrate |
| `usage_counters` | No | User-generated — must migrate |
| `jurisdiction_requests` | No | User-generated — must migrate |
| `sources` | **Yes** | Rebuilt from committed source packs via reindex pipeline |
| `source_chunks` | **Yes** | Rebuilt from committed source packs via reindex pipeline |
| `jurisdictions` | **Yes** | Synced from `apps/api/app/data/jurisdictions.json` by the same reindex pipeline |
| `alembic_version` | N/A | Created by `alembic upgrade head` on the new DB — do not dump/restore this one |

Rebuild mechanism for the three rebuildable tables: either trigger
**Actions → Production Reindex → Run workflow** (manual, defaults — see
`docs/production-readiness/prod-reindex-workflow.md`) once `PROD_DATABASE_URL`
points at the new DB, or run `scripts/reindex_prod.py` locally from `apps/api`
with `DATABASE_URL`/`QDRANT_URL`/`QDRANT_API_KEY`/`GEMINI_API_KEY` set to prod
values. Expect the known-slow ~45-minute import phase either way.

## 4. Pre-Cutover Checklist

- [ ] Capture the **current** `DATABASE_URL` value from the Render dashboard
      (`zoning-agent-api` → Environment) into a password manager before
      touching anything. It is `sync: false` in `render.yaml` (line 14–15), so
      it exists only in the dashboard — there is no other copy.
- [ ] Confirm local `pg_dump`/`psql` client major version ≥ the source
      server's major version (`psql --version`, `SELECT version();` on the
      source DB). A newer client can dump an older server; the reverse is
      unsupported.
- [ ] Announce a short maintenance window. Writes to the old DB during the
      dump window are **not** captured unless you run a second delta pass —
      plan the dump for a low-traffic moment and keep it short.
- [ ] Confirm the **target** has automated backups + PITR enabled (or a clear
      plan to enable them) BEFORE cutover, not after.
- [ ] Confirm `apps/api` local venv has `alembic` available (`pip install -e
      .[dev]` from `apps/api` if not).

## 5. Cutover Steps (option (b): new dedicated Postgres, keeping Supabase Auth)

Skip this section entirely if you chose option (a) — there is no data to
move.

### 5.1 Provision the target

Provision the new Postgres instance in its dashboard (Render Postgres, Neon,
etc.) with automated backups/PITR turned on at creation time. Note the
connection string — accepts `postgres://`, `postgresql://`, or
`postgresql+psycopg://`; `apps/api/app/database.py` `normalize_database_url()`
(lines 204–209) rewrites the first two to `postgresql+psycopg://`
automatically, so paste whichever form the provider gives you.

### 5.2 Apply schema to the new DB

```powershell
cd apps/api
$env:DATABASE_URL = "<NEW_DATABASE_URL>"
alembic upgrade head
```

This creates all tables (including `alembic_version`) empty on the new DB.
`alembic.ini`'s `sqlalchemy.url` is intentionally blank; `alembic/env.py`
`_database_url()` (lines 19–21) falls back to `database_url_from_settings()`,
which reads the `DATABASE_URL` env var you just set.

### 5.3 Dump the must-migrate tables from the OLD DB

Chosen approach: **`--data-only --table=<name>` per must-migrate table**, one
dump file per table. This is used (rather than one full dump with
`--exclude-table-data` for the rebuildable tables) because it lets you dump
and restore the small, critical tables independently, reconcile row counts
one table at a time, and re-run a single table's dump/restore if something
goes wrong — without re-touching the multi-GB `source_chunks` data at all.

If the source is Supabase: use the **session pooler (port 5432)** or a direct
connection, **never the transaction pooler (port 6543)** — `pg_dump` needs
session-level features the transaction pooler doesn't support. Supabase direct
connections are IPv6-first; from an IPv4-only network use the session pooler
host/port instead.

```powershell
$OLD_DB = "<OLD_DATABASE_URL>"   # session pooler or direct, port 5432
$tables = @("sessions","users","projects","analyses","audit_events","feedback","beta_access_events","usage_events","usage_counters","jurisdiction_requests")

foreach ($t in $tables) {
  pg_dump --data-only --table=$t --format=custom --file="dump_$t.dump" $OLD_DB
}
```

### 5.4 Restore into the NEW DB

Restore in FK-safe order. Among the must-migrate tables the only enforced
foreign keys are `analyses.project_id` and `feedback.project_id`, both →
`projects.project_id` (`apps/api/app/database.py` lines 73, 94), so `projects`
must restore before `analyses` and `feedback`; every other table is
order-independent (`projects.session_id` and the `user_id` columns are plain
indexed columns, not FKs). The order below satisfies that.

```powershell
$NEW_DB = "<NEW_DATABASE_URL>"
$orderedTables = @("users","sessions","projects","analyses","audit_events","feedback","beta_access_events","usage_events","usage_counters","jurisdiction_requests")

foreach ($t in $orderedTables) {
  pg_restore --data-only --dbname=$NEW_DB "dump_$t.dump"
}
```

(No `--disable-triggers`: it requires superuser, which managed Postgres does
not grant — and the FK-safe ordering makes it unnecessary.)

### 5.5 Row-count reconciliation

Run against both OLD and NEW for every migrated table; every row confirms a
match before proceeding.

```powershell
$tables = @("sessions","users","projects","analyses","audit_events","feedback","beta_access_events","usage_events","usage_counters","jurisdiction_requests")
foreach ($t in $tables) {
  Write-Output "== $t =="
  psql -c "SELECT count(*) FROM $t;" $OLD_DB
  psql -c "SELECT count(*) FROM $t;" $NEW_DB
}
```

Do not proceed to §5.6 until every pair matches.

### 5.6 Rebuild the rebuildable tables on the new DB

Point the reindex pipeline at the new DB and repopulate `sources`,
`source_chunks`, `jurisdictions`:

- Preferred: update the GitHub Actions secret `PROD_DATABASE_URL` (repo →
  Settings → Secrets and variables → Actions) to the new DB's URL, then
  **Actions → Production Reindex → Run workflow** (defaults, both options
  off). Expect the known-slow ~45-minute import phase.
- Or locally from `apps/api`, with `DATABASE_URL` (new DB),
  `QDRANT_URL`/`QDRANT_API_KEY`/`GEMINI_API_KEY` set to prod values:
  `python ../../scripts/reindex_prod.py` (plus `EMBEDDING_PROVIDER=gemini`,
  `VECTOR_PROVIDER=qdrant`, `RAG_PROVIDER=hybrid_local`).

### 5.7 Swap `DATABASE_URL` in Render

`DATABASE_URL` is `sync: false` in `render.yaml` (lines 14–15) — it is
dashboard-only and blueprint syncs will NOT touch it, so the dashboard is the
correct and only place to change it. No `render.yaml` edit is needed.

Render dashboard → `zoning-agent-api` → Environment → edit `DATABASE_URL` →
paste `<NEW_DATABASE_URL>` → Save.

### 5.8 Update the GitHub Actions secret and local `.env`

- Repo → Settings → Secrets and variables → Actions → `PROD_DATABASE_URL` →
  update to `<NEW_DATABASE_URL>` (if not already updated in §5.6).
- Update your local `.env` (repo root) if it holds a prod-pointing
  `DATABASE_URL` for any manual scripts.

### 5.9 Redeploy

Render dashboard → `zoning-agent-api` → **Manual Deploy → Restart** (or
**Deploy latest commit** if you prefer a full redeploy). Health check path is
`/health` (`render.yaml` line 11) — Render will hold traffic until it passes.

## 6. Verification

Run all of the following after cutover, in order:

```powershell
curl.exe -sf https://zoning-agent-api.onrender.com/health
curl.exe -sf https://zoning-agent-api.onrender.com/ready
curl.exe -sf https://zoning-agent-api.onrender.com/api/v1/jurisdictions/coverage
```

- `/health` and `/ready` return 200.
- Jurisdiction coverage count matches the pre-cutover count (compare against a
  count captured before starting the cutover).
- One authenticated `POST` analyze round-trip succeeds end-to-end (intake →
  address → parcel → jurisdiction → compliance → citation → report stages all
  complete).
- Log in as a pre-existing user and confirm a project/analysis created
  **before** the cutover is still visible to that user (proves the migrated
  `projects`/`analyses` rows are intact and correctly keyed to `user_id`).

## 7. Rollback

Keep the OLD database untouched and reachable for **at least 7 days** after
cutover — do not deprovision it.

Rollback procedure: swap `DATABASE_URL` back to the OLD DB's URL in the Render
dashboard (same place as §5.7) → Manual Deploy → Restart. Any data written to
the NEW DB during the cutover window (new users, projects, analyses, feedback)
is **lost** on rollback — it is not merged back into the old DB. Communicate
this to stakeholders before rolling back if the new DB has taken live traffic.

## 8. Backup/Restore Drill

Do not consider the cutover complete until this drill has run once against
the NEW target (or the upgraded Supabase project, for option (a)):

1. Confirm automated backups are ON in the provider dashboard (Supabase:
   Database → Backups; Render Postgres: instance → Backups; Neon: project →
   Backups/branching).
2. Wait for at least one automated backup to complete.
3. Restore the latest backup into a **scratch** database (a separate,
   throwaway instance/branch — never restore over the live target).
4. Run the row-count reconciliation query from §5.5 against the scratch DB
   for every must-migrate table, comparing to the live target.
5. Delete the scratch database.

A backup that has never been restored is not a backup — this drill is what
turns "backups are configured" into "backups work."

## 9. STOP Boundary — Human-Only Steps

The following steps require dashboard access and real credentials this
runbook cannot see or set. An agent must not attempt them:

- Provisioning any paid plan (Supabase Pro upgrade, Render Postgres, Neon, or
  any other paid tier) — this is a billing action.
- Reading or setting the actual `DATABASE_URL` value anywhere (Render
  dashboard, GitHub secret, local `.env`) — the password/URL lives only in
  dashboards per project convention.
- Performing the `DATABASE_URL` swap in the Render dashboard (§5.7 / rollback
  in §7).
- Updating the `PROD_DATABASE_URL` GitHub Actions secret (§5.8).
- Enabling/confirming automated backups and PITR in the target provider's
  dashboard (§4, §8).

Everything else in this runbook (schema migration commands, dump/restore
commands, reconciliation queries, verification curls) can be executed by an
agent once the human has supplied the connection strings via environment
variables at the time of execution.
