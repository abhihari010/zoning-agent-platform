# Project Status — Zoning Feasibility Platform

_Last updated: 2026-06-01_

A single source of truth for "where are we and what's next." Update this doc at the end of
a working session instead of leaving point-in-time handoff files scattered in `docs/`.

---

## TL;DR

The product is a **deployed, working zoning-feasibility RAG platform** for the Blacksburg, VA
region. The retrieval pipeline now has two-layer district/use precision (Layer 1 recall fix +
Layer 2 source classification), both shipped and **verified live in production**. The next
gate is **production hardening for real users** (smoke tests, paid Postgres, pre-launch checks),
then **jurisdiction expansion** beyond the current VA corpus.

**Live URLs**
- Frontend: https://zoning-agent-platform.vercel.app
- API: https://zoning-agent-api.onrender.com

**Production stack** (authoritative — `docs/production-readiness/runbook.md` now matches this)
- `AI_PROVIDER=groq` · `RAG_PROVIDER=hybrid_local` · `EMBEDDING_PROVIDER=gemini` · `VECTOR_PROVIDER=qdrant`
- Postgres on Supabase (free tier) · Render API (blueprint-synced via `render.yaml`) · Vercel frontend
- `STARTUP_REINDEX_ENABLED=false` — retag offline via `scripts/update_source_classification.py`

---

## Current Stage: Layer 2 shipped + verified in prod

### What just landed
- **Layer 1** (PR #43) — made `"unknown"` a district wildcard so the scraped Blacksburg corpus
  (406/412 sources tagged `districts:["unknown"]`) stops being filtered out. Restored recall.
- **Layer 2** (PR #44) — additive district/use classification. The classifier
  (`apps/api/app/source_classifier.py`) adds canonical tags (`commercial-employment`,
  `mixed-use-core`, `residential-low-density`, `industrial-zone`; uses like `food-service`)
  on top of the `unknown`/`general` wildcards, so the re-ranker can score exact-district matches
  above wildcards (precision) without ever hard-excluding (recall stays safe).
- **Production migration run** — `scripts/update_source_classification.py` retagged **1719 Qdrant
  point payloads** (payload-only, no re-embedding — Gemini embeddings are billed). The A5
  cache-version hash now includes districts/uses, so stale cached results self-invalidate.

### Verification (2026-06-01) — Layer 2 confirmed working in prod

**Check 1 — Golden bakery query** (`400 Clay St SW, Blacksburg, VA`)

| Criterion | Result |
|---|---|
| Pipeline ran end-to-end | ✓ All 5 stages completed, 200 OK |
| Citations returned with source IDs | ✓ 5 excerpts, chunk IDs present (e.g. `blacksburg-va-sec-3405:chunk:7:…`) |
| District correctly classified | ✓ `district-downtown` — Layer 2 working |
| Provider stack | ✓ `groq` / `hybrid_local` (matches prod blueprint) |
| Sec. 4555 surfacing | Conditional pass (see note) |

> **Sec. 4555 note (correct behavior, not a bug).** With use type **"Home-based food business"**,
> home-occupation sections (Sec. 3405, Sec. 4211) win — semantically correct for that framing.
> With use type **"Restaurant or cafe"**, Sec. 4555 surfaces at score **4.08** as the second
> citation (`blacksburg-va-sec-4555:chunk:4:acdc20192f6e`). The Layer 2 `food-service` /
> `food-business` tags on Sec. 4555 are confirmed live in Qdrant and produced correctly by the
> classifier. The section surfaces when the use type matches; it does not beat home-occupation
> sections on a home-based query, which is the intended ranking.

**Check 2 — Residential query ranking** ("Add a second-story bedroom addition to single-family
home" + Residential addition use type, same address)

| Rank | Section | Score |
|---|---|---|
| 1 | Sec. 4220 — Single-family, attached | 4.07 |
| 2 | Sec. 4201 — Accessory apartment | 4.05 |
| 3 | Sec. 3113 — Site Development Regulations | 4.02 |
| 4 | Sec. 3289 — Vehicular parking (historic overlay) | 4.02 |
| 5 | Sec. 1271 — General provisions | 4.02 |

Zero commercial sections in the top 5 — **residential ranks above commercial. ✓**

**Verdict:** Layer 2 source classification is live and behaving correctly. Retrieval precision
improved without sacrificing recall.

---

## Next Steps

### Now — production hardening (blocks real users)
1. **Run beta smoke Tests 3 & 4** against prod — supported full pipeline + unsupported
   jurisdiction (distinct "unsupported jurisdiction" message, not a generic crash). Check
   `/health` and `/ready` for warnings (re-confirm `vector_count` is non-zero now that Qdrant is
   populated, and that the old OpenAI 429 warning is gone under Groq).
2. **Move Supabase free Postgres → paid plan with backups** before real users land. Triggers:
   >25 testers, or any paid/contractual/municipal/SLA-bound user, or >1 GB / quota warning.
3. **Run pre-launch checklist scripts:** `validate_source_packs.py`,
   `check_public_support_candidates.py`, `check_source_freshness.py`,
   `check_production_config.py`, `smoke_public_api.py`. Enforce rate limits; remove beta keys
   before broad public launch.

### Next — jurisdiction expansion
- Living roadmap: `docs/handoff-nationwide-expansion.md` (WS0–WS9).
- Add jurisdictions via source packs (`docs/public-launch/source-pack-spec.md` +
  `document-acquisition-workflow.md`); promote only after a golden scenario passes
  (`docs/public-launch/golden-scenario-spec.md`). Do **not** hard-code city checks — extend
  `data/source_registry.json` and the district mappings.

### Done this session ✓
- ~~Reconcile stale `docs/production-readiness/runbook.md`~~ — fixed: env matrix now reflects
  Groq/Gemini/Qdrant + `STARTUP_REINDEX_ENABLED=false` + blueprint-sync/secrets warnings.
- ~~Docs cleanup~~ — removed 17 superseded/scratch markdown files; remaining docs are current,
  CLAUDE.md-referenced, or living specs.

---

## Key References
- `CLAUDE.md` — repo shape, commands, architecture, provider modes, working conventions.
- `AGENT.md` — commit exclusions, branch/PR conventions.
- `docs/single-orchestrator-architecture.md` — orchestrator/tool design.
- `docs/production-readiness/runbook.md` — deploy checklist, env matrix, rollback, incidents.
- `docs/handoff-nationwide-expansion.md` — expansion roadmap (WS0–WS9).
- `docs/handoff-layer2-prod-verification.md` — the verification runbook used above.

## Operational gotchas (from project memory)
- Render is **blueprint-synced** — change env in `render.yaml`, not the dashboard (drift is reset).
- Startup reindex must stay **OFF** (boot-time reindex blocks Render's port scan → failed deploy).
- `progress.md` / `testing-progress.md` are local-only — never commit (now gitignored).
- Never put "Co-Authored-By: Claude" in commits/PRs.
- `gh` auth can flip accounts: on `403 denied to abhihari10`, run
  `gh auth switch --user abhihari010 && gh auth setup-git`.
