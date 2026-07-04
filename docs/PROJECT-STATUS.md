# Project Status — Zoning Feasibility Platform

_Last updated: 2026-07-04_

A single source of truth for "where are we and what's next." Update this doc at the end of
a working session instead of leaving point-in-time handoff files scattered in `docs/`.

---

## TL;DR

The product is **live in production** and serving real jurisdiction coverage: **26 jurisdictions**
in total — **3 `public_supported`** (blacksburg-va, christiansburg-va, montgomery-county-va) and
**23 `source_indexed`** (served with a preliminary-coverage abstention caveat), the newest being
loudoun-county-va (977 sources, 2,463 chunks, merged 2026-07-03). CI now includes an automated
offline retrieval-regression gate, and prod reindexing is automated via a GitHub Actions workflow
(not yet run for a real source change). Current focus is a validation pass (real-provider eval run,
live prod smoke, first real execution of the prod-reindex workflow), then depth: promoting 1–2
flagship jurisdictions (richmond-va first candidate) from `source_indexed` to `public_supported`.

**Live URLs**
- Frontend: https://zoning-agent-platform.vercel.app
- API: https://zoning-agent-api.onrender.com

**Production stack**
- `AI_PROVIDER=groq` (llama-3.3-70b-versatile) · `RAG_PROVIDER=hybrid_local` · `EMBEDDING_PROVIDER=gemini` · `VECTOR_PROVIDER=qdrant`
- Postgres via Supabase (session pooler, `DATABASE_URL`) · Qdrant Cloud (27,952 points total) · Render API (starter, blueprint-synced via `render.yaml`) · Vercel frontend
- Auth: Supabase JWT for the public beta, plus a legacy beta-key gate; `ADMIN_ACCESS_KEY` gates source-admin writes
- `STARTUP_REINDEX_ENABLED=false` — reindexing happens offline / via the `prod-reindex` workflow, never at boot

---

## Architecture (one-paragraph version)

The backend is a provider-agnostic, five-stage pipeline coordinated by
`apps/api/app/orchestrator/zoning_orchestrator.py` (`ZoningOrchestrator`), with each stage
implemented as a tool under `apps/api/app/tools/` (intake, address, parcel, jurisdiction,
compliance, citation, report). AI/retrieval/embedding providers are resolved through
`apps/api/app/ai/registry.py` against `AI_PROVIDER` / `RAG_PROVIDER` / `EMBEDDING_PROVIDER` /
`VECTOR_PROVIDER` settings, so the same orchestrator runs against deterministic logic, Groq,
OpenAI-compatible, local, or legacy watsonx backends. Jurisdiction support is entirely data-driven
via `apps/api/app/data/jurisdictions.json` and `apps/api/app/data/source_registry.json` (per-
jurisdiction packs live under `apps/api/app/data/source_packs/`) — no hard-coded city checks.
The key invariant: if retrieval returns no citations, the orchestrator returns `unknown` /
low-confidence rather than synthesizing a zoning conclusion. See `docs/single-orchestrator-architecture.md`
for the full design.

---

## What Shipped Recently

- **PR #75** — memoized corpus-loading hot paths, stopping an OOM crash loop on the 512MB Render instance.
- **PR #82** — fixed the retrieval-cache fingerprint to compute the source-index version from a DB
  fingerprint instead of a full corpus load, removing that load from the serving hot path (fixed
  both the OOM loop and a Supabase egress overage).
- **PR #84** — promoted loudoun-county-va to `source_indexed` (977 sources, 2,463 chunks), verified
  live in prod.
- **PR #85** — added `.github/workflows/prod-reindex.yml`, automating prod corpus reindexing on
  source-pack merges plus manual dispatch (runbook: `docs/production-readiness/prod-reindex-workflow.md`).
- **PR #86** — added an offline retrieval-regression eval gate to CI
  (`apps/api/tests/eval/ci_gate.py` + the `eval-gate` job in `.github/workflows/ci.yml`).
- **PR #87** — documented the Postgres durability & cutover runbook
  (`docs/production-readiness/postgres-cutover-runbook.md`) ahead of the eventual paid-plan cutover.

---

## CI / Automation Posture

`.github/workflows/ci.yml` runs 6 jobs on every change: Backend pytest, Source quality (source-pack
validation + public-support-candidate + freshness checks), Web build (typecheck + build), Browser
fixture smoke, Eval retrieval gate (offline regression gate against golden scenarios), and Hygiene.

Two additional workflows run independently of the main CI pipeline:
- `.github/workflows/production-smoke.yml` — `workflow_dispatch` smoke test against the deployed
  Render/Vercel pair.
- `.github/workflows/source-freshness.yml` — scheduled source-freshness checks.
- `.github/workflows/prod-reindex.yml` — reindexes the production corpus on source-pack merges or
  manual dispatch; see `docs/production-readiness/prod-reindex-workflow.md`. This has not yet been
  exercised for a real source-pack change — that's part of the current validation pass.

---

## Next Steps

### Now — validation pass
1. Run a real-provider (non-deterministic) five-gate eval run against the golden scenarios.
2. Run a live prod smoke test (`scripts/smoke_public_api.py`) to confirm current coverage end to end.
3. Execute the `prod-reindex` workflow for real against a live source-pack change, to confirm the
   automation added in PR #85 works outside of CI.

### Next — flagship depth
- Promote 1–2 `source_indexed` jurisdictions to `public_supported`, using the pilot playbook in
  `docs/handoff-pilot-city-eval-gate.md`. **richmond-va** is the first candidate.
- Continue to add jurisdictions via source packs
  (`docs/public-launch/source-pack-spec.md`); promote only after a golden scenario passes
  (`docs/public-launch/golden-scenario-spec.md`). Do **not** hard-code city checks — extend
  `data/source_registry.json` and the district mappings.

### Deliberately deferred (pre-revenue decision, 2026-07-03)
- **Supabase Pro upgrade** (paid plan, backups/durability) — cutover runbook is ready
  (`docs/production-readiness/postgres-cutover-runbook.md`); a manual baseline `pg_dump` of the 10
  user-data tables was taken 2026-07-04 as an interim safety net. Trigger: revenue / real users.
- **Render RAM bump** (one-line `plan:` change in `render.yaml`) — deferred until the same trigger.

---

## Key References
- `CLAUDE.md` — repo shape, commands, architecture, provider modes, working conventions.
- `AGENT.md` — commit exclusions, branch/PR conventions.
- `docs/single-orchestrator-architecture.md` — orchestrator/tool design.
- `docs/production-readiness/runbook.md` — deploy checklist, env matrix, rollback, incidents.
- `docs/production-readiness/prod-reindex-workflow.md` — prod reindex automation runbook.
- `docs/production-readiness/postgres-cutover-runbook.md` — paid-plan Postgres cutover runbook.
- `docs/handoff-pilot-city-eval-gate.md` — pilot-city promotion playbook (public_supported gate).

## Operational gotchas (from project memory)
- Render is **blueprint-synced** — change env in `render.yaml`, not the dashboard (drift is reset).
- Startup reindex must stay **OFF** (boot-time reindex blocks Render's port scan → failed deploy).
- `progress.md` / `testing-progress.md` are local-only — never commit (gitignored).
- Never put "Co-Authored-By: Claude" in commits/PRs.
- Running `pytest -q` from the main tree loads the repo-root `.env`, which points at production —
  run backend tests in a `.env`-free worktree for a clean baseline.
- Missing `QDRANT_URL`/`QDRANT_API_KEY` during a reindex silently falls back to `localhost`,
  producing a connection-refused error that looks like "0 chunks in Qdrant."
- `gh` auth can flip accounts: on `403 denied to abhihari10`, run
  `gh auth switch --user abhihari010 && gh auth setup-git`.
