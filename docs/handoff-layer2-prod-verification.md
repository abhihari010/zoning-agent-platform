# Handoff — Verify Layer 2 Source-Classification Migration in Production

_Written: 2026-06-01. Hand this to the next agent picking up post-migration verification._

---

## What Just Happened

The Layer 2 source-classification work (PR #44, merged to `main` as merge commit `4c8f78f`) is done, and the **production migration has already been run successfully**. The operator ran `scripts/update_source_classification.py` against the prod stack and got:

```
classified 629 source-pack sources.
upserted 629 sources to Postgres.
replaced chunk rows for 644 sources (1719 chunks).
updated 1719 Qdrant point payloads (no re-embedding).
```

So all 1719 Qdrant points now carry `districts` / `uses` payload tags. No re-embedding occurred (Gemini embeddings are billed — the tags are payload-only metadata, so `chunk_id`/vector are unchanged). The A5 cache-version hash now includes districts/uses, so stale cached retrieval results self-invalidate on the next query.

### What Layer 2 does (one-paragraph refresher)
Additive district/use tagging on source chunks for retrieval precision **without sacrificing recall**. The classifier (`apps/api/app/source_classifier.py`, first-match rules engine) preserves `unknown`/`general` wildcards and *adds* canonical tags (e.g. `commercial-employment`, `mixed-use-core`, `residential-low-density`, `industrial-zone`; uses like `food-service`). `hybrid_local_retriever.py` does tiered district scoring (exact district `+2.0`, `unknown` wildcard scored lower). The orchestrator gates the effective district on confidence (≥0.7 passes a concrete district, else `unknown`). Rule ordering matters: in `data/source_packs/va/blacksburg-va/classification_rules.json`, mixed-use/downtown rules precede the broad COMMERCIAL rule so "DOWNTOWN COMMERCIAL DISTRICT" maps to `mixed-use-core`, not `commercial-employment`.

---

## Your Job: Confirm the Migration Actually Improved Retrieval

The migration **writes** succeeded, but **retrieval quality has not been verified against the deployed app yet.** Run the golden Blacksburg scenarios and confirm Layer 2 works end-to-end in prod.

**Production URLs:**
- Frontend: `https://zoning-agent-platform.vercel.app`
- API: `https://zoning-agent-api.onrender.com`

**Prod stack** (confirmed via project memory — do **NOT** trust `docs/production-readiness/runbook.md`, it's stale and contradicts reality):
- `AI_PROVIDER` = Groq analysis
- `EMBEDDING_PROVIDER` = Gemini
- `VECTOR_PROVIDER=qdrant`
- `RAG_PROVIDER=hybrid_local`
- Startup reindex stays **OFF**
- Postgres on Supabase
- Render is **blueprint-synced** via `render.yaml` (dashboard drift gets reset — change env in the blueprint, not the dashboard)

---

## Two Checks To Run

### Check 1 — Golden coffee-shop / bakery query
- **Address:** `400 Clay St NW, Blacksburg, VA 24060`
- **Description:** "Convert attached garage to a small bakery with two employees and weekday pickup hours"
- **Pass criteria:** citations come back with `source_ids`, and **Sec. 4555** (the food-service use standard) surfaces in the results. This is the canonical golden case.

### Check 2 — Residential ranking
- Run a residential-zoned query and confirm residential sections now rank **above** commercial ones. That ranking shift is the whole point of Layer 2 district tagging.

---

## How To Run It

The operator prefers you **drive it in the browser** using the gstack `/browse` skill. CLAUDE.md mandates `/browse` for all web browsing — **never use `mcp__claude-in-chrome__*` tools.**

- Browse binary: `~/.claude/skills/gstack/browse/dist/browse` (resolves to repo-local copy if present).
- First `/browse` call triggers a one-time build (~10s) — **ask the operator before building.**

### Auth wall to expect
The prod app sits behind Supabase login (JWT; token in `localStorage` as `sb-tzstkgifmftqcdguhshn-auth-token`). Headless browse can't log in cold. Options:
1. Import the operator's existing browser cookies: `browse cookie-import-browser` (or `--domain`).
2. `browse handoff "<reason>"` → operator logs in manually in the visible window → `browse resume`.

Coordinate with the operator on which path. State (cookies/localStorage) persists across handoff.

### Fallback if browser verification is blocked
Walk the operator through running the two queries themselves in their already-logged-in session and reporting back the citations + ranking.

---

## Constraints (project memory + CLAUDE.md)

- Never put "Co-Authored-By: Claude" in commit messages or PR descriptions.
- `progress.md` / `testing-progress.md` are local-only tracking files — **never stage or push them.**
- Edit agent-reference docs (handoff/planning `.md`) but **don't commit/push them unless asked.**
- Postgres password lives only in dashboards — never commit it.
- `gh` auth can flip to the wrong account. If you see `403 denied to abhihari10`, run:
  `gh auth switch --user abhihari010 && gh auth setup-git`

---

## After Verification — Broader Production-Readiness Backlog (not blocking)

1. Run beta-path smoke **Tests 3 & 4** (supported full pipeline + unsupported jurisdiction) against prod; check `/health` and `/ready` for warnings (a prior session saw `vector_count: 0` and an OpenAI 429 — both should be re-checked now that Qdrant is populated and Groq is the analysis provider).
2. **Reconcile the stale `docs/production-readiness/runbook.md`** — it still lists `AI_PROVIDER=deterministic`, `VECTOR_PROVIDER=none`, `EMBEDDING_PROVIDER=local`, and `STARTUP_REINDEX_ENABLED=true`, all wrong vs the actual Groq/Gemini/Qdrant stack with reindex off. This is a safe, no-secrets cleanup.
3. Move off Supabase **free** Postgres to a paid plan with backups before real users land (trigger: >25 testers, or any paid/contractual/municipal/SLA-bound user).
4. Pre-launch checklist scripts: `validate_source_packs.py`, `check_public_support_candidates.py`, `check_source_freshness.py`, `check_production_config.py`, `smoke_public_api.py`. Enforce rate limits; remove beta keys before broad public launch.
