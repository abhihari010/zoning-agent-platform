# Eval Datasets

Each file is named `<jurisdiction_id>.json` and contains an array of labeled scenarios
for that city. The runner auto-discovers files here by jurisdiction ID.

## Dataset JSON Shape

```json
[
  {
    "id": "franklin-tn-bakery-conditional",
    "address": "230 Franklin Rd, Franklin, TN 37064",
    "project_description": "Convert a garage into a small commercial bakery with two employees and a walk-up window.",
    "jurisdiction_id": "franklin-tn",
    "expect": {
      "decision_in": ["conditional", "restricted"],
      "permit_path_includes": ["building permit", "business license"],
      "must_cite_section_refs": ["Sec. 14-123", "Sec. 14-456"],
      "min_confidence": 0.5,
      "should_abstain": false
    }
  }
]
```

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique scenario ID used in scorecard output |
| `address` | string | yes | Full address passed to the pipeline |
| `project_description` | string | yes | Project description passed to the orchestrator |
| `jurisdiction_id` | string | yes | Must match the indexed corpus jurisdiction |
| `expect.decision_in` | list[string] | yes | Acceptable decisions (the pipeline must return one of these) |
| `expect.permit_path_includes` | list[string] | no | Strings that should appear in permit_path or checklist permits |
| `expect.must_cite_section_refs` | list[string] | no | Section refs (human-readable) that must appear among citations |
| `expect.min_confidence` | float | no | Minimum required feasibility confidence |
| `expect.should_abstain` | bool | no | True = pipeline must return unknown or low-confidence (not a fabricated conclusion) |

### Authoring guidelines

- Derive expected answers directly from the scraped ordinance text — do not guess.
- A human must sign off on each dataset before it becomes a gate (Phase 3 checkpoint).
  Record the sign-off date in a top-level `"signed_off_at"` field on the array wrapper,
  or in a companion `<jurisdiction_id>.meta.json` file.
- Cover a spread of cases: clearly permitted, clearly prohibited, conditional, and at
  least one `should_abstain` (ambiguous / out-of-corpus) scenario.
- `must_cite_section_refs` should reference section headings exactly as they appear in
  the scraped ordinance — they are matched verbatim against `citation.section_ref`.

## Running the real-pipeline eval

The harness runs the **real** `ZoningOrchestrator` against an indexed corpus.
Always run it against throwaway infrastructure — never production data:

- Index + run against a **throwaway Qdrant collection**
  (`QDRANT_COLLECTION=zoning_eval_<city>`) and an **isolated SQLite** DB (leave
  `DATABASE_URL` empty so the SQLite fallback is used).
- Set `CACHE_ENABLED=false` so cached responses can't mask a regression.
- Use the **prod analysis model (Groq)** — **never OpenRouter**.
- **Delete the throwaway collection afterward**; prod stays clean until a human
  approves promotion. See `docs/handoff-pilot-city-eval-gate.md` for the full plan.

### Montgomery County VA — dimensional run

`montgomery-county-va.json` holds 12 positive dimensional scenarios covering
ordinance sections 10-21, 10-24, 10-25, 10-26, 10-27, 10-28, 10-29, 10-30
(district → section: A-1→10-21, R-1→10-24, R-2→10-25, R-3→10-26, RM-1→10-27,
GB→10-28, CB→10-29, M-1→10-30).

**Pass bar: 12/12 fully-correct** — every scenario must return the expected
decision AND surface its required dimensional citation.

CI-safe integrity guard (no providers, runs in CI):

```
cd apps/api
pytest tests/eval/test_montgomery_dataset.py -q
```

Real-pipeline run (manual, throwaway infra only):

```
cd apps/api
# repo-root .env: AI_PROVIDER=groq, RAG_PROVIDER=hybrid_local,
# EMBEDDING_PROVIDER=gemini, VECTOR_PROVIDER=qdrant
export QDRANT_COLLECTION=zoning_eval_montgomery   # throwaway collection
export CACHE_ENABLED=false
unset DATABASE_URL                                # isolated SQLite fallback

# 1. Index the Montgomery County VA source pack into the throwaway collection
#    (local API: POST /api/v1/ingestion/reindex with X-Admin-Access-Key).
# 2. Run the harness:
python -m tests.eval.runner --jurisdiction montgomery-county-va
# 3. Delete the throwaway Qdrant collection afterward.
```

## No files here yet

Franklin, TN (the first pilot city) scenarios are authored in Phase 3, after the
ordinance is scraped (Phase 2) and a human reviews the expected answers (Gate 1).
See `docs/handoff-pilot-city-eval-gate.md` for the full plan.
