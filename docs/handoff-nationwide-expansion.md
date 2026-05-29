# Handoff: Nationwide Expansion + RAG Activation

_Written: 2026-05-29. Pick up this document in a new session to continue._

---

## What the product is

A zoning feasibility platform. Users enter a US address and project description; the system runs a 5-stage pipeline and returns a plain-language feasibility decision, citations from the municipal zoning code, and a permit checklist. The backend is FastAPI (Python), the frontend is React + Vite, deployed on Render (API) and Vercel (frontend).

**Live URLs:**
- Frontend: https://zoning-agent-platform.vercel.app/
- API: https://zoning-agent-api.onrender.com
- Repo: https://github.com/abhihari010/zoning-agent-platform

---

## Current pipeline — how analysis works end-to-end

```
User submits (address + project description)
          │
          ▼
Stage 1 — Intake (apps/api/app/tools/intake_tool.py)
  • Parses project description → infers use type (e.g. "home-based-food-business")
  • Calls Google Maps → normalizes address → resolves jurisdiction_id (e.g. "blacksburg-va")
  • Looks up zoning district from district_rules.json (e.g. "mixed-use-core")
  • Detects missing details, generates clarification questions
          │
          ▼
Stage 2 — Retrieve Sources  ← THE KEY BOTTLENECK FOR EXPANSION
  Current: SourceRegistryRetrievalProvider (apps/api/app/ai/source_registry_retriever.py)
  • Loads ALL source chunks from SQLite into RAM
  • Filters in Python: jurisdiction_id + district + use tags
  • Returns top 5 matching chunks (pre-written excerpt strings)
  • NO vector search, NO semantic matching, NO Qdrant
          │
          ▼
Stage 3 — Analyze Compliance (apps/api/app/tools/compliance_tool.py)
  • Sends the 5 citation excerpts + project description to Groq
  • Model: llama-3.3-70b-versatile (via apps/api/app/ai/groq_provider.py)
  • Groq outputs: decision, summary, permits, follow-up questions, warnings
  • Falls back to deterministic keyword logic if Groq fails
          │
          ▼
Stage 4 — Citation Validation (apps/api/app/tools/citation_tool.py)
  • Verifies Groq didn't hallucinate citation IDs
  • Adjusts confidence if invalid IDs found
          │
          ▼
Stage 5 — Generate Checklist + Report (apps/api/app/tools/report_tool.py)
  • Builds structured permit steps from citations
  • Assembles final API response
```

---

## Current coverage

**6 jurisdictions, all in Virginia:**

| Jurisdiction | ID | Status | Sources |
|---|---|---|---|
| Blacksburg, VA | `blacksburg-va` | PUBLIC SUPPORTED ✓ | 6 |
| Christiansburg, VA | `christiansburg-va` | source-indexed | 4 |
| Montgomery County, VA | `montgomery-county-va` | source-indexed | 6 |
| Roanoke, VA | `roanoke-va` | source-indexed | 5 |
| Roanoke County, VA | `roanoke-county-va` | source-indexed | 5 |
| Global (state/federal) | `*` | n/a | 1 |

Sources live in: `apps/api/app/data/source_registry.json` (27 entries, manually written excerpt paragraphs — NOT scraped text)

> **⚠️ Editing `source_registry.json`? You MUST bump `SOURCE_REGISTRY_VERSION`.** Seeding (`ensure_seed_sources`, `apps/api/app/ai/source_registry_retriever.py`) only runs when the DB is empty **or** `SOURCE_REGISTRY_VERSION` is set to a value not yet seeded. On an already-seeded DB (e.g. production Postgres), edits/additions to the file are **silently ignored** until you change `SOURCE_REGISTRY_VERSION` to a new string and redeploy — then it upserts all entries (idempotent by `source_id`) and reindex picks them up. Symptom of forgetting: reindex reports fewer sources than the file has (we hit exactly this — DB stuck at 12 while the file had 27). Re-seeding does not require an empty DB; the version bump is the trigger.

---

## The critical RAG misconception to understand

**`VECTOR_PROVIDER=qdrant` is set on Render BUT Qdrant is not being used for retrieval.**

Here is why:
- `RAG_PROVIDER=source_registry` → uses `SourceRegistryRetrievalProvider` → SQL filter, no Qdrant
- `VECTOR_PROVIDER=qdrant` → only affects the trust indicator display in the UI and the `hybrid_local_retriever` — but that retriever is never called when `RAG_PROVIDER=source_registry`

To actually use Qdrant for retrieval, `RAG_PROVIDER` must be changed to `hybrid_local`. That activates `HybridLocalRetrievalProvider` (`apps/api/app/ai/hybrid_local_retriever.py`), which:
1. Embeds the query
2. Searches Qdrant with jurisdiction/district/use filters
3. Scores results by vector similarity + keyword overlap
4. Falls back to SQL keyword search if Qdrant returns nothing

**Current Render env vars (as of 2026-05-29):**
```
AI_PROVIDER=groq
GROQ_API_KEY=<set>
GROQ_MODEL=llama-3.3-70b-versatile
RAG_PROVIDER=source_registry       ← needs to change to hybrid_local
VECTOR_PROVIDER=qdrant
EMBEDDING_PROVIDER=none            ← needs to change to local (or openai)
QDRANT_URL=<set>
QDRANT_API_KEY=<set>
QDRANT_COLLECTION=zoning_source_chunks
```

---

## Next steps — priority order

### Step 1: Fix in-memory SQL filter (do this before anything else)

**Problem:** `list_source_chunks_filtered()` in `apps/api/app/storage.py` loads ALL chunks into RAM and filters in Python. Works fine at 27 sources. Will fail at 1,000+.

**Fix:** Replace with a SQL WHERE query.

File: `apps/api/app/storage.py` — method `list_source_chunks_filtered()`

The `payload_json` column stores `{districts: [], uses: []}`. The cleanest fix is to add indexed `districts_csv` and `uses_csv` VARCHAR columns to the `source_chunks` table so they can be filtered in SQL directly.

Steps:
1. New Alembic migration: add `districts_csv` + `uses_csv` columns + indexes to `source_chunks`
2. Update `repositories.py` `_upsert_source_chunks()` to populate them on write
3. Rewrite `list_source_chunks_filtered()` to use SQL WHERE with LIKE or IN checks
4. Add index: `CREATE INDEX idx_chunks_jurisdiction ON source_chunks(jurisdiction_id)`

---

### Step 2: Activate real RAG (flip env vars + reindex)

Once the SQL fix is in, switch Render env vars:

```
RAG_PROVIDER=hybrid_local
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=<free AI Studio key>
GEMINI_EMBEDDING_MODEL=gemini-embedding-001   # optional, this is the default
GEMINI_EMBEDDING_DIMENSIONS=768               # optional, default 768 (set 0 for full 3072)
```

`EMBEDDING_PROVIDER=gemini` uses `GeminiEmbeddingProvider` (`apps/api/app/ai/embedding_provider.py`) — Google's `gemini-embedding-001` via the **native** batch endpoint (`{base}/models/gemini-embedding-001:batchEmbedContents`, auth via `x-goog-api-key`). Free tier, semantically meaningful, 768 dims by default (Matryoshka-truncated). Needs a free `GEMINI_API_KEY` from Google AI Studio — separate from the Google Maps key. Unlike the old `local` SHA256 hash embeddings (64-dim, non-semantic), this produces real semantic similarity so queries like "run a food truck" will match "mobile food vendor ordinance".

> **Why native, not OpenAI-compat:** the OpenAI-compatible shim (`/v1beta/openai/embeddings`) is throttled separately from the documented per-model quota and returns `429` even when the native quota is completely idle (the AI Studio usage dashboard tracks only the native endpoint). The native `batchEmbedContents` endpoint gets the real documented limits (3,000 RPM / 1M TPM / unlimited RPD on free tier as of 2026-05). Do not switch back to the compat shim.

> **Note:** Groq has no embeddings API (only chat/speech models), so `AI_PROVIDER=groq` for compliance analysis and `EMBEDDING_PROVIDER=gemini` for retrieval are intentionally two different providers. The embeddings provider normalizes vectors to unit length, so the truncated 768-dim output is valid for both Qdrant cosine search and the hybrid retriever's dot-product scoring.

**Rate limits / resilience:** the native endpoint's free-tier limits (3,000 RPM / 1M TPM / unlimited RPD, per Google Cloud project) are generous enough for nationwide ingestion. The provider still batches inputs and retries `429` with exponential backoff (honoring `Retry-After` and Gemini's `retryDelay`) for safety. Tunables (env vars, all optional):
> - `GEMINI_EMBEDDING_BATCH_SIZE` (default 32) — inputs per `batchEmbedContents` request
> - `GEMINI_EMBEDDING_REQUEST_INTERVAL_SECONDS` (default 1.0) — pause between batches
>
> A `429` during reindex is non-fatal — it returns a `vector_warnings` entry (now including the quota message from the error body) and leaves the SQL chunks intact; just re-run reindex.

> **Troubleshooting — `429 "prepayment credits are depleted"`:** this is NOT a rate limit. It means your `GEMINI_API_KEY` belongs to a Google Cloud project with **billing enabled** (paid tier) whose prepaid balance is depleted, so every request is rejected. Fix: generate a new key in a **free-tier** project at AI Studio (or top up billing on the paid project). Confirmed working 2026-05-29 with a free-tier key → reindex reported 12 chunks / 12 vectors. The AI Studio usage dashboard showing generous limits + zero usage does not mean the key will work if its project is on depleted prepay.

After deploying, trigger reindex to populate Qdrant with the existing 27 VA sources:
```
POST https://zoning-agent-api.onrender.com/api/v1/ingestion/reindex
Header: X-Admin-Access-Key: <admin key>
```

**Verify:** Submit `400 Clay St SW, Blacksburg, VA 24060`. Pipeline field in UI should show `groq / hybrid_local`. Citation count should still be 5.

---

### Step 3: Populate US jurisdiction stubs

The system needs to recognize any US address as a known (but unsupported) jurisdiction — otherwise addresses outside Virginia return a generic fallback instead of a clean "not covered yet" message.

**How jurisdictions work:**
- `apps/api/app/data/jurisdictions.json` — flat JSON array, each entry is a `Jurisdiction`
- Key fields: `jurisdiction_id`, `coverage_status` (`"public_supported"` / `"source_indexed"` / `"unsupported"`), `locality_names[]`, `county_names[]`, `state_names[]`, `match_strategy`
- At runtime: Google Maps address components are matched against these arrays
- `supported=True` only when `coverage_status == "public_supported"`

**What to build:** `scripts/generate_jurisdiction_stubs.py`

Downloads the US Census national places file and generates `jurisdictions.json` stub entries for all ~19,000 incorporated places + ~3,000 counties. All set to `coverage_status = "unsupported"` initially. This makes any US address show the right city name in the "not covered" message and enables tracking which cities get the most requests.

Census data: `https://www2.census.gov/geo/docs/reference/codes2020/national_place2020.txt`

Generated `jurisdiction_id` format: `{city-slug}-{state-abbrev}` (e.g., `los-angeles-ca`, `chicago-il`)

**Scalability note:** At 22,000 entries, `jurisdictions.json` becomes slow to parse on every request. The loader (`apps/api/app/jurisdictions.py` `load_jurisdictions()`) uses `@lru_cache` — this helps. Longer term, split into per-state files: `data/jurisdictions/us-ca.json`, `data/jurisdictions/us-ny.json`, and lazy-load by state.

---

### Step 4: Build the document scraping pipeline

This is the core of nationwide expansion. The current "sources" are manually written excerpt paragraphs — not real ordinance text. For every new city you need actual scraped zoning code.

**Primary target: Municode** — most US municipalities publish their code here.

URL pattern: `https://library.municode.com/{state}/{city}/codes/code_of_ordinances`

Municode has a programmatic table-of-contents API:
```
GET https://library.municode.com/api/tocListNodes/{client-id}
```

**Files to create in `services/ingestion/scraper/`:**

```
services/ingestion/scraper/
  municode_scraper.py      # Fetch TOC, identify zoning chapters, extract section text
  html_chunker.py          # Clean HTML → plain text → 500–800 char chunks
  run_scrape.py            # CLI: python run_scrape.py --city "Los Angeles" --state CA
```

**Output format:** Write to `services/ingestion/source_packs/{STATE}/{jurisdiction-id}/manifest.json` using the existing source pack schema. This plugs directly into the existing workflow:
```
discover_jurisdiction_sources.py (scaffold) →
  run_scrape.py (fill content) →
    validate_source_packs.py (validate) →
      POST /api/v1/ingestion/reindex (load into DB + Qdrant)
```

**Chunking:** The existing `build_source_chunks()` in `apps/api/app/ingestion.py` handles chunking to 900-char max. Store scraped text in the `full_text` field of `SourceRegistryEntry` (supports up to 250KB per source). The `excerpt` field (auto-generated from first 500 chars of `full_text`) becomes the text Groq reads.

**Source types to scrape per city** (use existing enum from `validate_source_packs.py`):
- `zoning_ordinance` — zoning code chapters (primary, multiple per city)
- `planning_page` — planning dept homepage
- `permit_page` — permit application pages
- `building_code` — typically state-level, tag as `jurisdiction_id: "*"`
- `health_code` — state-level food establishment rules

**Priority city list (top 25 by population):**
New York City, Los Angeles, Chicago, Houston, Phoenix, Philadelphia, San Antonio, San Diego, Dallas, San Jose, Austin, Jacksonville, Fort Worth, Columbus, Charlotte, Indianapolis, San Francisco, Seattle, Denver, Nashville, Oklahoma City, El Paso, Washington DC, Las Vegas, Louisville

---

### Step 5: District resolution at scale

The current `district_rules.json` only has rules for Blacksburg (4 entries). For new cities, the district will be `"unknown"`.

**Good news:** This is handled gracefully. When `district = "unknown"`:
- Qdrant filter skips the district constraint → retrieves ALL sources for the jurisdiction
- Groq reads all retrieved excerpts and applies judgment across all districts
- Confidence is slightly lower but results are still meaningful

**Recommendation:** Do NOT try to pre-build district rules for every city. Instead:
1. Launch new cities with `district = "unknown"` fallback — this works
2. For the highest-traffic cities, add GIS-based district resolution as a Phase 2 improvement
3. GIS approach: each city's planning department publishes a zoning map as a GIS layer; query it with lat/lng to get the exact zoning district code

---

### Step 6: Embedding quality upgrade (later)

With `EMBEDDING_PROVIDER=groq` + `nomic-embed-text-v1_5` (768 dims), retrieval is already semantically meaningful. If you need higher quality at scale, upgrade to:

- `EMBEDDING_PROVIDER=openai` + `text-embedding-3-small` (1536 dims, ~$0.02/1M tokens) — requires a separate `OPENAI_API_KEY`
- Cohere Embed v3 (free tier available)
- Voyage AI (good quality, cheap)
- Jina Embeddings v3

After any embedding provider change: re-run reindex. The collection is auto-recreated for dimension changes (the reindex endpoint calls `store.reset_collection()` before upserting).

---

## Key files reference

| Area | File | What it does |
|------|------|---|
| Pipeline coordinator | `apps/api/app/orchestrator/zoning_orchestrator.py` | Runs all 5 stages |
| Current retrieval | `apps/api/app/ai/source_registry_retriever.py` | SQL tag filter (active) |
| Real RAG retrieval | `apps/api/app/ai/hybrid_local_retriever.py` | Qdrant + keyword (inactive) |
| Vector store | `apps/api/app/rag/vector_store.py` | Qdrant schema + upsert |
| Embeddings | `apps/api/app/ai/embedding_provider.py` | LocalHash (64-dim) + disabled |
| Groq AI | `apps/api/app/ai/groq_provider.py` | LLM compliance analysis |
| Source chunking | `apps/api/app/ingestion.py` | Splits full_text into ≤900-char chunks |
| SQL storage | `apps/api/app/storage.py` | `list_source_chunks_filtered()` — needs SQL fix |
| Source models | `apps/api/app/models.py:133` | `SourceRegistryEntry`, `SourceChunk` |
| Jurisdiction lookup | `apps/api/app/jurisdictions.py` | `detect_jurisdiction()`, `load_jurisdictions()` |
| District mapping | `apps/api/app/district_mapping.py` | `map_district_from_components()` |
| Jurisdiction data | `apps/api/app/data/jurisdictions.json` | All known jurisdictions |
| District rules | `apps/api/app/data/district_rules.json` | Address → zoning district (Blacksburg only) |
| Source registry | `apps/api/app/data/source_registry.json` | 27 VA sources |
| Scaffold script | `scripts/discover_jurisdiction_sources.py` | Generates source pack skeleton |
| Validate script | `scripts/validate_source_packs.py` | Validates manifest.json schema |
| Freshness script | `scripts/check_source_freshness.py` | Audits source staleness |
| Provider registry | `apps/api/app/ai/registry.py` | Routes AI_PROVIDER/RAG_PROVIDER to implementations |
| Settings | `apps/api/app/settings.py` | All env var definitions |

---

## Recommended session handoff sequence

```
Session A:  Step 1 (SQL fix) + Step 2 (flip env vars, reindex, verify Blacksburg still works)
Session B:  Step 3 (generate jurisdiction stubs script, update jurisdictions.json)
Session C:  Step 4 (build Municode scraper, scrape + load first 5 cities)
Session D:  Step 4 continued (next 20 cities, promote first batch to public_supported)
Session E+: Step 6 (embedding upgrade) when query quality needs improvement
```

---

## Tests to run before/after each change

```bash
# Backend unit tests (run from apps/api/)
pytest tests/test_ai_providers.py tests/test_orchestrator.py tests/test_settings.py -q

# Full backend suite
pytest -q  # ~23 passing; some Windows SQLite locking errors are pre-existing, not regressions

# TypeScript check (run from repo root)
npm run typecheck:web

# Live E2E verification (Playwright or manual browser):
# 1. Supported address:   400 Clay St SW, Blacksburg VA 24060
#    Expected: feasibility=conditional, confidence=97%, 5 citations, pipeline=groq/hybrid_local
# 2. Unsupported address: 123 Main St, Austin TX 78701
#    Expected: "Austin, TX was recognized, but source coverage is not ready yet"
```
