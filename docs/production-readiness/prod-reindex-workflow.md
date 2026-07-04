# Production Reindex Workflow — Setup & Runbook

`.github/workflows/prod-reindex.yml` automates what used to be a manual,
~45-minute, laptop-run step after every jurisdiction merge: syncing the
committed source packs into the production corpus (Postgres + Qdrant) and
applying district/use payload tags.

## What it runs

From a GitHub-hosted runner (never the 512 MB Render box), with cwd `apps/api`:

1. `scripts/reindex_prod.py` — imports source packs into prod Postgres, syncs
   jurisdiction records (so `/api/v1/jurisdictions/coverage` picks up new
   cities), and embeds **new** chunks into Qdrant via Gemini. Incremental:
   chunk_id encodes a content hash, so already-embedded chunks are skipped and
   re-runs are cheap and resumable.
2. `scripts/update_source_classification.py` — `--dry-run` first (logged for
   the record), then applies the payload-only district/use retag to
   already-indexed chunks. No re-embedding, no Gemini cost.

Running both in sequence is correct for every change shape: new text gets
imported + embedded (with district payloads written directly from committed
`classification_rules.json`); a rules-only change makes the reindex a near
no-op (0 pending chunks) and the retag applies the new tags.

A final informational step curls the public coverage endpoint and prints the
jurisdiction list (non-fatal).

## Triggers

- **Push to `main`** touching `apps/api/app/data/source_packs/**` or
  `apps/api/app/data/jurisdictions.json` (i.e. any merged jurisdiction PR).
- **Manual** (`Actions → Production Reindex → Run workflow`) with options:
  - `skip_import` — skip the slow import phase; only embed/retag what is
    already in Postgres. Leave **off** for new cities (their sources are not
    in Postgres yet).
  - `retag_only` — only run the payload retag (for a rules-only fix when you
    don't want to wait for the import phase).

Runs are serialized (`concurrency: prod-reindex`, queued not cancelled) so two
merges in quick succession cannot race on Qdrant.

## Required GitHub Actions secrets (USER SETUP — one time)

The workflow **no-ops with a warning** until these exist, so merging it is
safe. Add them at **repo → Settings → Secrets and variables → Actions →
New repository secret**. All values live in the Render dashboard
(`zoning-agent-api` service → Environment) — they are intentionally not in the
repo or blueprint.

| Secret name         | Value                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------------- |
| `PROD_DATABASE_URL` | Prod Postgres URL (the `DATABASE_URL` on Render; `postgres://` or `postgresql+psycopg://` both work — settings normalizes) |
| `QDRANT_URL`        | Prod Qdrant cluster URL                                                                    |
| `QDRANT_API_KEY`    | Prod Qdrant API key                                                                        |
| `GEMINI_API_KEY`    | Gemini key used for embeddings                                                             |

Notes:

- `GROQ_API_KEY` is **not** needed: district classification
  (`scripts/classify_districts.py`) is an offline, pre-commit step whose output
  (`classification_rules.json`) is committed with the pack. Neither
  `reindex_prod.py` nor `update_source_classification.py` calls Groq.
- Provider modes (`EMBEDDING_PROVIDER=gemini`, `VECTOR_PROVIDER=qdrant`,
  `RAG_PROVIDER=hybrid_local`) are set in the workflow itself, not secrets.
- The secrets guard means a missing/rotated secret produces a skipped run with
  a `::warning::`, never a half-configured run. In particular the "missing
  QDRANT_URL → silent localhost fallback → connection refused" failure mode
  from manual runs cannot reach prod here: the guard skips before anything runs.

## First-run checklist

1. Add the four secrets above.
2. Trigger manually: Actions → **Production Reindex** → Run workflow (defaults;
   leave both options off).
3. Watch the logs: the import phase is **known-slow, not hung** (~45 min,
   ~0.4 s/source upsert over the full corpus; logs progress per 100 sources),
   then embedding runs only for chunks not yet in Qdrant.
4. Confirm the final step prints the expected coverage count, or curl
   `GET https://zoning-agent-api.onrender.com/api/v1/jurisdictions/coverage`
   yourself.

## Cost & limits

- Embedding cost is incremental — only new/changed text is embedded. A typical
  new city is a few thousand chunks, well under the $1/mo Gemini spend cap.
  A `--full-rebuild` (NOT exposed as a workflow input on purpose) would re-embed
  the whole corpus (~$0.75) and eat most of the cap — keep full rebuilds manual.
- The Gemini cap is shared with live prod query embeddings; if an embed run
  429s, re-running later resumes where it left off.
- Job timeout is 180 min; the queue (`concurrency`) holds follow-up runs rather
  than cancelling in-flight ones.

## Failure modes

| Symptom                                        | Meaning / action                                                                 |
| ---------------------------------------------- | -------------------------------------------------------------------------------- |
| Run "succeeds" instantly with a warning        | Secrets not configured — add them (table above) and re-run.                      |
| Import phase looks stuck                       | It isn't — ~0.4 s/source over ~7,500+ sources; check the per-100 progress lines. |
| Gemini HTTP 429 during embedding               | Monthly spend cap hit; re-run later (incremental/resumable).                     |
| Retag reports skipped points                   | Expected when SQL is ahead of the vector index (chunks not yet embedded) — the next reindex run picks them up. |
| Coverage step fails but reindex succeeded      | Informational only (`continue-on-error`); check the Render service is up.        |

## Relationship to the manual runbook

The manual laptop procedure (env vars + `python scripts/reindex_prod.py` from
`apps/api`) still works and remains the fallback — see the script docstrings.
This workflow replaces it for the routine post-merge case.
