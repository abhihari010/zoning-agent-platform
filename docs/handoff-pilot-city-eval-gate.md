# Execution Plan: First Pilot City + Reusable Eval Gate

_Audience: an executing agent (Sonnet) picking this up cold. Written 2026-06-01._

Goal: onboard **one** new (non-VA) jurisdiction end-to-end through the existing ingestion
rail, AND build the **reusable** offline accuracy harness (WS6) that gates promotion. After
this pilot, every future city is **scrape + a small data file + run the harness** — no new
eval code per city.

---

## The key economics (read this first)

An eval gate has two parts. Only one is per-city:

| Part | Built how often | Type |
|---|---|---|
| Eval **harness** — runner over the real `ZoningOrchestrator`, accuracy metrics, gate thresholds, scorecard | **Once** (this pilot) | Code |
| Labeled **scenarios** — ~8–10 `(address, project) → expected decision/permit path` rows per city | Per city | **Data** (JSON) |

So the coding is front-loaded here. City #2…N cost = one scrape + one hand-authored JSON +
one harness run. Do **not** write per-city eval code — if you find yourself doing that, stop.

A golden harness already exists (`apps/api/tests/golden/runner.py` + `scenarios.json`) but it
is a **deterministic CI regression guard** (in-memory sources, no real retrieval). Keep it.
This plan adds a **separate** real-pipeline accuracy runner alongside it.

---

## Critical constraints (do not violate)

- **No hard-coded city checks.** Extend `data/jurisdictions.json` + source packs only
  (CLAUDE.md rule). District stays `"unknown"` for the new city — graceful fallback handles it
  (WS5); do not author per-city district rules.
- **Do not touch production Qdrant/Postgres.** Run the scrape + eval against a **local/throwaway
  Qdrant collection** (`QDRANT_COLLECTION=zoning_eval_<city>`). Prod stays clean until the gate
  passes and a human approves promotion.
- **Ground-truth labels are NOT self-certified by the agent.** The agent drafts candidate
  expected-answers from the scraped ordinance; a **human signs off** before they become the gate
  (Phase 3 checkpoint). An eval gate built on guessed labels is worse than no gate.
- **If you edit `apps/api/app/data/source_registry.json`, bump `SOURCE_REGISTRY_VERSION`** or
  seeding is silently ignored. (Source *packs* imported via `/ingestion/reindex` do not need this.)
- Branch + PR per the repo convention; tie to a GitHub issue. Never commit `progress.md` or
  `Co-Authored-By` lines.

---

## Phase 0 — Setup + pick a Municode pilot city  ⟵ GATE 0

0.1 Create branch `feat/pilot-city-eval-gate` off `main` (now at `db71380`).

0.2 **Pilot city — SELECTED: Franklin, Tennessee** (confirmed 2026-06-01).
    - `--city "Franklin" --state TN`, `jurisdiction_id = franklin-tn`,
      `jurisdiction_type = municipality`.
    - Municode URL: `https://library.municode.com/tn/franklin` — verified live, Code of
      Ordinances updated 2026-05-27, contains **TITLE 14 — ZONING AND LAND USE CONTROL**.
    - Why: Nashville-metro city with very high small-business formation; single municipality;
      clean English Municode code → isolates "does the pipeline generalize beyond VA?" as the
      single variable (reuses the proven Municode fetcher, no new fetcher needed).
    - **⚠ TN-code caveat to check in Phase 2:** Tennessee MTAS-style codes sometimes keep the
      detailed zoning ordinance in a *separate* document and leave Title 14 as a thin reference
      stub. If the scraped Title 14 `full_text` is sparse (chunk count ≈ source count), find
      Franklin's standalone zoning ordinance (linked from `www.franklintn.gov` planning/zoning)
      and scrape that with `--fetcher generic_html --url <…>` instead. This is the most likely
      Phase 2 surprise — budget for it.
    - **Do NOT swap to Austin TX / Miami FL / Dallas TX** — those are on American Legal /
      eCode360 and need fetchers that don't exist yet. Save them for after the pipeline is proven.

0.3 Confirm local env can run the real stack (needed for Phase 1 + 4). **As of 2026-06-01 the
    local env is NOT ready:** repo root has only `.env.example` + a `.env.local` containing just
    `VERCEL_OIDC_TOKEN`; there is no `.env` and `apps/api/` has no env files. Before Phase 1/4,
    create a repo-root `.env` (copy `.env.example`) with `GROQ_API_KEY`, `GEMINI_API_KEY`,
    `QDRANT_URL`, `QDRANT_API_KEY`, `GOOGLE_MAPS_API_KEY` (values live in Render/dashboards).
    Set `QDRANT_COLLECTION=zoning_eval_franklin` for all eval/scrape runs in this plan.

**GATE 0:** ✅ city chosen + Municode hosting confirmed (this step done). Remaining before
Phase 1/4: populate the local `.env` (0.3). Then proceed.

---

## Phase 1 — Build the reusable eval harness (WS6, build-once)

Location: `apps/api/tests/eval/` (new package; keep separate from `tests/golden/`).

1.1 `apps/api/tests/eval/dataset_schema.py` — a Pydantic model for one labeled scenario:
```
id, address, project_description, jurisdiction_id,
expect: { decision_in: [...], permit_path_includes: [...](optional),
          must_cite_section_refs: [...](optional, by section_ref not chunk id),
          min_confidence: float, should_abstain: bool }
```
The `expect` block is intentionally tolerant (decision ∈ set, citation by human-readable
`section_ref`) so labels survive chunk-id churn.

1.2 `apps/api/tests/eval/runner.py` — runs the **real** pipeline:
    - Calls `ZoningOrchestrator` (not deterministic `services.analyze_project`) with
      `AI_PROVIDER=groq`, `RAG_PROVIDER=hybrid_local`, `EMBEDDING_PROVIDER=gemini`,
      `VECTOR_PROVIDER=qdrant` against the `zoning_eval_<city>` collection.
    - For each scenario, computes per-row pass/fail and aggregates these **metrics**:
      | Metric | Definition | Default gate |
      |---|---|---|
      | Decision accuracy | predicted `decision` ∈ `expect.decision_in` | ≥ 0.80 |
      | Citation validity | every returned citation id resolves to a real chunk (reuse `CitationTool` logic) | = 1.0 |
      | Hallucinated-section rate | citations whose `section_ref` doesn't exist in the city's corpus | = 0.0 |
      | Required-citation recall | `must_cite_section_refs` actually surfaced when specified | ≥ 0.80 |
      | Abstention correctness | rows with `should_abstain` return `unknown`/low-conf, not a fabricated conclusion | = 1.0 |
    - Emits a **scorecard**: `apps/api/tests/eval/reports/<city>-<date>.json` + a printed table.
      Exit non-zero if any gate fails (so it works in CI).

1.3 `apps/api/tests/eval/datasets/<jurisdiction_id>.json` — the per-city data file (filled in
    Phase 3). Runner auto-discovers datasets here.

1.4 Unit-test the harness itself with a tiny synthetic fixture city (2 scenarios, mocked
    provider) so the metric math is covered without burning API quota. Add to `pytest -q`.

**Acceptance:** `python -m pytest apps/api/tests/eval -q` passes on the synthetic fixture; the
runner produces a scorecard and exits non-zero when a gate is intentionally failed.

---

## Phase 2 — Scrape the pilot city

2.1 Draft skeleton:
```
python scripts/discover_jurisdiction_sources.py \
  --jurisdiction-name "<City>" --state <ST> --jurisdiction-type municipality
```

2.2 Scrape real ordinance text (Municode fetcher, the proven path):
```
python services/ingestion/scraper/run_scrape.py \
  --city "<City>" --state <ST> --fetcher municode \
  --coverage-status source_indexed
# add --max-sections 20 for a first smoke run, then full
```
Output lands in `.tmp/source_pack_drafts/<st>/<jurisdiction_id>/manifest.json` (never overwrites
curated packs).

2.3 **First non-VA Municode scrape WILL surface parser issues** — budget for it. Inspect the
    draft manifest: section refs populated, `full_text` non-empty and clean (no nav chrome),
    chunk count ≫ source count, URLs resolve. Likely fix sites if broken: Municode TOC client-id
    discovery + section parsing in `services/ingestion/scraper/fetchers/municode.py` and cleanup
    in `html_cleaner.py`. Fix in the fetcher (reusable), not by hand-editing the manifest.

2.4 Validate:
```
python scripts/validate_source_packs.py --source-packs-dir .tmp/source_pack_drafts
```
Must be 0 errors. (Warnings about `districts: unknown` are expected — Layer 2 tags are applied
later/offline; new cities legitimately start unknown.)

2.5 Promote the validated draft into the curated tree:
    `apps/api/app/data/source_packs/<st>/<jurisdiction_id>/manifest.json`.

**Acceptance:** validated manifest with real `full_text` in the curated tree; spot-check 3
sections against the live Municode page for fidelity.

---

## Phase 3 — Author labeled scenarios (per-city data)  ⟵ GATE 1 (human)

3.1 Agent drafts **8–10 candidate scenarios** in
    `apps/api/tests/eval/datasets/<jurisdiction_id>.json`, derived from the scraped ordinance.
    Cover a spread: clearly-permitted, clearly-prohibited, conditional/permit-required, and at
    least one **should_abstain** (ambiguous / out-of-corpus) case. Cite expected `section_ref`s
    pulled from the actual scraped text.

3.2 For each, the agent records its *reasoning + the ordinance section it relied on* so a human
    can verify quickly.

3.3 **GATE 1 (human sign-off):** the user reviews and corrects the expected answers. These
    labels become the gate — the agent must not self-certify them. This review is the only
    real per-city human cost, and it is light (read ~10 short ordinance excerpts).
    Capture the sign-off date in the dataset file.

This dataset file is the **template** every future city copies. Document its shape in Phase 6.

---

## Phase 4 — Import, reindex, run the gate  ⟵ GATE 2 (automated)

4.1 Import + chunk + index the pilot pack into the **eval** collection (local API instance,
    `QDRANT_COLLECTION=zoning_eval_<city>`):
```
POST /api/v1/ingestion/reindex   (header X-Admin-Access-Key)
  body: { "directory": "apps/api/app/data/source_packs/<st>/<jurisdiction_id>" }
```
Confirm `vector_count` rose and `vector_provider: qdrant`.

4.2 Run the harness:
```
python -m apps.api.tests.eval.runner --jurisdiction <jurisdiction_id>
```
Read the scorecard.

**GATE 2:** all default thresholds in 1.2 pass. If not, the city does **not** get promoted —
iterate on retrieval (district/use tags via `scripts/update_source_classification.py`, chunking,
or scrape quality) and re-run. This is the whole point of the gate: catch a bad city *before*
users see it.

---

## Phase 5 — Promote (only if GATE 2 passed)

5.1 Add the jurisdiction to `apps/api/app/data/jurisdictions.json` following the existing entry
    schema (`jurisdiction_id`, `name`, `state`, FIPS, `match_strategy`, `locality_names`,
    `official_source_urls`, `planning_contact`, `last_verified_at`, …). Start
    `coverage_status: "source_indexed"`.

5.2 Add a golden CI scenario for the city in `apps/api/tests/golden/scenarios.json` (regression
    guard — deterministic, cheap) so future refactors can't silently break it.

5.3 Flip `coverage_status` → `"public_supported"` **only now**. Run
    `scripts/check_public_support_candidates.py` against the new `jurisdiction_id` — must report
    `eligible`.

5.4 Production rollout: reindex the pilot pack into the **prod** collection
    (`zoning_source_chunks`), bump `SOURCE_REGISTRY_VERSION` only if `source_registry.json` was
    edited, deploy. Verify live: submit a pilot-city address → pipeline reads `groq/hybrid_local`,
    citations returned, correct decision.

**Acceptance:** the new city answers correctly live; an unsupported nearby address still returns
the graceful "recognized, not covered yet" response.

---

## Phase 6 — Document the repeatable loop (makes #2…N cheap)

Write `docs/public-launch/add-a-city-runbook.md`: the exact command sequence (discover → scrape →
validate → promote pack → author dataset → human sign-off → reindex eval → run harness → promote),
the dataset JSON template, and the gate thresholds. State plainly: **no new code per city** —
only a scrape and a hand-authored dataset, unless the city is on a non-Municode platform (then,
and only then, add a fetcher under `services/ingestion/scraper/fetchers/`).

---

## Verification commands (run before opening the PR)

```
python -m pytest apps/api/tests/eval -q            # harness self-tests
cd apps/api && pytest tests/golden -q              # golden regression incl. new city
cd apps/api && pytest -q                           # full backend suite (no regressions)
npm run typecheck:web                              # if any shared-schema/types touched
python scripts/validate_source_packs.py --source-packs-dir apps/api/app/data/source_packs
```

## Open questions for the human before starting
- Which pilot city/state? (must be Municode — see GATE 0)
- Confirm local `.env` has Groq + Gemini + Qdrant keys for the real-pipeline eval run.
- Default gate thresholds in 1.2 acceptable, or stricter for launch?
```

## Why this sequence
Build the gate (Phase 1) before scraping so you're never tempted to eyeball-approve a city.
Scrape (2) proves geographic generalization on the proven fetcher. Human-vetted labels (3) keep
the gate honest. Phases 4–5 are pure execution against objective thresholds. Phase 6 converts the
one-time investment into a cheap, repeatable loop — answering the "won't this take forever per
city?" concern: no, the code is built once here.
