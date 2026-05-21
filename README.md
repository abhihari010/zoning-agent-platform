# Zoning Agent Platform

Monorepo for a zoning feasibility assistant that helps a resident or business owner ask, in plain English, whether a project is likely allowed at a property and what permits or reviews come next.

The current build uses a React frontend and a FastAPI backend with a sequential three-agent orchestration flow:

1. `User Intent Agent`: interprets the project description and flags missing details.
2. `Zoning Research Agent`: retrieves district-relevant municipal source excerpts.
3. `Compliance & Checklist Agent`: synthesizes the result into a feasibility summary, permit path, warnings, and citations.

The frontend is designed to connect those stages together visibly for the user, including:

- intake form for project description and address
- progress tracker for each agent stage
- clarification modal when the intent stage needs more information
- feasibility dashboard with citations and warnings
- downloadable permit checklist
- prominent legal disclaimer

## Provider-Agnostic Operation and Roadmap

The current backend defaults to a provider-agnostic local mode: deterministic analysis with source-registry retrieval. That default does not require IBM watsonx credentials or any other external AI provider. WatsonX support remains available only as an optional legacy adapter selected with `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`.

The roadmap keeps the useful shape of the original system while expanding beyond a single provider. The goal is a zoning assistant that supports local source ingestion, pluggable LLM providers, richer retrieval, broader geography, and a more polished user workflow.

### Guiding Principles

- Keep zoning answers citation-first. Every recommendation should link back to source text, effective dates, jurisdiction, and section references.
- Treat AI output as assisted drafting, not legal authority. The app should always explain uncertainty and route low-confidence cases to human review.
- Separate the agent workflow from the model provider. The same three-agent flow should work with future hosted providers, local models, or deterministic fallback logic.
- Make geography configurable. Blacksburg should become the first supported jurisdiction, not a hard-coded boundary.
- Design for expansion through source data, not one-off conditionals. Adding a city should mostly mean adding jurisdiction metadata, parcel/district mapping, and ordinance documents.

### Target Architecture

1. `Intake Agent`
   - Understands the user's project description.
   - Extracts use type, construction scope, business operations, missing details, and risk factors.
   - Produces follow-up questions when the project is underspecified.

2. `Jurisdiction & Parcel Agent`
   - Normalizes the address.
   - Determines jurisdiction, parcel context, zoning district, overlays, and special areas when available.
   - Replaces the current Blacksburg-only address restriction with configurable jurisdiction support.

3. `Retrieval Agent`
   - Searches the local zoning knowledge base.
   - Filters by jurisdiction, district, use, overlay, source type, and effective date.
   - Returns cited excerpts with enough metadata for auditability.

4. `Compliance Agent`
   - Synthesizes feasibility, likely permit path, review triggers, warnings, and next steps.
   - Must only make claims that can be traced to retrieved source excerpts or clearly marked assumptions.

5. `Review & Feedback Layer`
   - Shows confidence, source coverage, unresolved questions, and user feedback.
   - Stores traces so bad answers can be debugged and improved.

### Phase 1: Provider Boundary Foundation

Phase 1 is implemented in the current codebase. The backend now routes analysis and retrieval through provider-neutral interfaces in `apps/api/app/ai/`, while `apps/api/app/services.py` preserves the existing `AnalyzeResult` response shape consumed by the frontend.

Implemented provider settings:

- `AI_PROVIDER=deterministic|watsonx`
- `RAG_PROVIDER=source_registry|watsonx`

Default behavior:

- `AI_PROVIDER=deterministic`
- `RAG_PROVIDER=source_registry`
- no WatsonX credentials required
- missing citations force an `unknown` or low-confidence result instead of a high-confidence zoning conclusion

WatsonX behavior:

- WatsonX is optional legacy support behind `apps/api/app/ai/watsonx_provider.py`.
- Missing WatsonX credentials only matter when `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`.
- If WatsonX analysis fails after retrieval, the backend falls back to deterministic analysis and adds a warning.

Phase 1 reference docs:

- `docs/agent-agnostic-zoning-platform/spec.md`
- `docs/agent-agnostic-zoning-platform/plan.md`

### Phase 2: Build a Real Local RAG Pipeline

The current source registry can store excerpts, and `services/ingestion/documents/` can import local `.md`, `.txt`, and `.json` documents. The next step is to turn that into a searchable knowledge base.

Recommended steps:

1. Add document records for jurisdiction, source URL, source type, effective date, and retrieval timestamp.
2. Add chunking with stable chunk IDs.
3. Add embeddings for each chunk.
4. Store vectors in a local database first:
   - ChromaDB for fast local prototyping, or
   - SQLite plus vector extension if you want fewer moving parts, or
   - Postgres/pgvector when preparing for production.
5. Implement hybrid retrieval:
   - keyword search for exact ordinance terms
   - vector search for semantic matches
   - metadata filters for jurisdiction, district, use, and document type
6. Return citations from chunks, not hand-written excerpts.

Success criteria:

- `POST /api/v1/ingestion/import-local-docs` can ingest real ordinance documents.
- `POST /api/v1/ingestion/reindex` actually rebuilds the retrieval index.
- Retrieval returns source-backed chunks with section references and URLs.

### Phase 3: Expand Beyond Blacksburg

The current address flow intentionally rejects non-Blacksburg addresses. To expand, jurisdiction handling should become data-driven.

Recommended steps:

1. Introduce a `jurisdictions.json` or database table with:
   - jurisdiction ID
   - display name
   - state/county/city matching rules
   - official zoning map/source URLs
   - supported document collections
   - planning department contact info
2. Replace hard-coded Blacksburg validation in `normalize_address`.
3. Store `jurisdiction_id` on each project and source.
4. Add district mapping rules per jurisdiction.
5. Add an "unsupported jurisdiction" state that still helps the user by explaining what is missing.
6. Start with 2-3 nearby jurisdictions before scaling broadly.

Good first expansion targets:

- Montgomery County, VA
- Christiansburg, VA
- Roanoke, VA

Success criteria:

- The app can distinguish "valid address, unsupported jurisdiction" from "invalid address."
- Sources and retrieval are scoped to the correct jurisdiction.
- The UI clearly shows which jurisdiction is being analyzed.

### Phase 4: Improve Agent Quality and Trust

Once retrieval is grounded in real documents, improve the reasoning workflow.

Recommended steps:

1. Require structured JSON from the compliance agent.
2. Validate every model response with Pydantic before returning it.
3. Add citation coverage checks:
   - no citations means `unknown`
   - contradictory citations means `low_confidence`
   - missing district/use match lowers confidence
4. Add an evidence grading step before final synthesis.
5. Save agent traces for debugging:
   - prompt inputs
   - retrieval filters
   - source IDs
   - model provider
   - response validation errors
6. Add golden test cases for common scenarios.

Success criteria:

- The app refuses to overstate uncertain answers.
- Every answer has visible evidence or a clear explanation of why evidence is missing.
- Regression tests catch prompt/schema drift.

### Phase 5: UI Expansion

The frontend already has an assistant workspace, admin source editor, progress tracker, clarification modal, citations, checklist download, and feedback. The next UI pass should make the product feel less like a demo and more like a planning workspace.

Recommended improvements:

1. Rename/rebrand the app away from IBM-specific language.
2. Add jurisdiction and source coverage indicators near the address field.
3. Show a structured project intake panel:
   - use type
   - construction scope
   - operating hours
   - employees
   - parking/loading
   - food/fire/health triggers
4. Add an evidence viewer with filters by source, section, district, and confidence.
5. Add a side-by-side "Answer" and "Evidence" layout for completed reviews.
6. Improve the admin area:
   - source upload status
   - index status
   - document version history
   - source health checks
7. Add saved projects and comparison views later.

Success criteria:

- Users understand why the answer was reached.
- Admins can see what source coverage exists before trusting the assistant.
- The experience works for incomplete or unsupported cases, not just happy paths.

### Suggested Next Sprint

The provider boundary foundation is in place. The next narrow sprint should improve deterministic local retrieval before adding embeddings or hosted model providers.

1. Make `/api/v1/ingestion/reindex` build stable local chunk records from registered sources.
2. Store chunk metadata such as source ID, section reference, district tags, use tags, URL, and effective date.
3. Keep retrieval deterministic and local while the chunk model settles.
4. Add tests for stable chunk IDs and source metadata.
5. Defer embeddings, vector search, and new LLM providers until the chunked source index exists.

### Open Technical Decisions

- Which LLM provider should be the first non-IBM provider?
- Should the production database stay SQLite for now, or move to Postgres/pgvector?
- Should document ingestion fetch official URLs automatically, or should admins upload curated documents first?
- How much parcel-level GIS data should the app attempt to handle in the first expansion?
- Should jurisdiction expansion start regionally around Virginia, or support arbitrary uploaded jurisdictions?

### Near-Term Implementation Checklist

- [x] Create `apps/api/app/ai/` provider interfaces.
- [x] Add `AI_PROVIDER` and `RAG_PROVIDER` settings.
- [x] Wrap the existing watsonx client as one optional legacy provider.
- [x] Add deterministic/local providers for tests and development.
- [x] Update tests so the backend works without external AI credentials.
- [x] Rework package and user-facing copy away from IBM-specific product naming.
- [ ] Implement real document chunking and indexing.
- [ ] Replace hard-coded Blacksburg-only validation with jurisdiction support states.
- [ ] Add jurisdiction metadata to source registry entries.
- [ ] Add UI indicators for jurisdiction, source coverage, and confidence.

## Structure

- `apps/web`: React + TypeScript + Vite frontend with Tailwind CSS
- `apps/api`: FastAPI backend
- `packages/shared-schema`: Shared TypeScript contracts
- `services/ingestion`: Placeholder for document ingestion pipeline

## Quick Start

### Web

1. `npm install`
2. `npm run dev:web`
3. `npm run build:web`

### API

1. `cd apps/api`
2. `python -m venv .venv`
3. `.venv\\Scripts\\activate`
4. `pip install -e .[dev]`
5. Optional: from the repo root, copy `.env.example` to `.env` if you want persistent local settings
6. `uvicorn app.main:app --reload --port 8000`

The default backend provider mode runs without WatsonX credentials:

- `AI_PROVIDER=deterministic`
- `RAG_PROVIDER=source_registry`

Google Maps is still required for live address intake and suggestions. Backend tests can run without a `.env` file because they mock external calls.

Set environment variables before starting the API when needed:

- `GOOGLE_MAPS_API_KEY`: required Google Maps API key with Geocoding and Places enabled
- `GOOGLE_MAPS_TIMEOUT_SECONDS`: optional timeout (default `8`)
- `ZONING_DB_PATH`: optional SQLite database path for persistent API storage (default `apps/api/app/data/app.sqlite3`)
- `AI_PROVIDER`: optional analysis provider (`deterministic` or `watsonx`, default `deterministic`)
- `RAG_PROVIDER`: optional retrieval provider (`source_registry` or `watsonx`, default `source_registry`)
- `GOOGLE_DISTRICT_KEYWORD_MAP`: optional JSON mapping used when district cannot be inferred from components, example:
  - `{"downtown":"mixed-use-core","industrial":"industrial-zone"}`
- `IBM_ZONING_DB_PATH`: legacy fallback for `ZONING_DB_PATH` during migration
- `WATSONX_ENABLED`: legacy compatibility flag that selects WatsonX providers when set to a truthy value; prefer `AI_PROVIDER` and `RAG_PROVIDER` for new setup
- `WATSONX_API_KEY`: required when `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`
- `WATSONX_URL`: required when `AI_PROVIDER=watsonx` (example `https://us-south.ml.cloud.ibm.com`)
- `WATSONX_PLATFORM_URL`: optional IBM Cloud IAM URL override for WatsonX retrieval
- `WATSONX_PROJECT_ID`: required when `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`
- `WATSONX_VECTOR_INDEX_ID`: required when `RAG_PROVIDER=watsonx`
- `WATSONX_MODEL_ID`: required when `AI_PROVIDER=watsonx`
- `WATSONX_TIMEOUT_SECONDS`: optional timeout for IAM + inference (default `20`)
- `WATSONX_MAX_ATTEMPTS`: optional retry attempts for WatsonX HTTP calls (default `3`)
- `WATSONX_RETRY_DELAY_SECONDS`: optional backoff base delay for WatsonX retries (default `0.6`)

`.env` loading:

- The API now loads environment values automatically from:
  - repo root `.env`
  - repo root `.env.local`
  - `apps/api/.env`
  - `apps/api/.env.local`
- Recommended setup: keep a single repo-root `.env` based on `.env.example`

District and retrieval data sources:

- `apps/api/app/data/district_rules.json`: district mapping rules from Google components
- `apps/api/app/data/source_registry.json`: source registry used by zoning retrieval/citations

Available API additions:

- `GET /api/v1/address/suggest?query=...`: Google Places autocomplete-backed address suggestions
- `GET /api/v1/ingestion/sources`: list persistent source registry entries
- `POST /api/v1/ingestion/sources`: create or update a source registry entry
- `POST /api/v1/ingestion/reindex`: request source reindex
- `POST /api/v1/ingestion/import-local-docs`: parse local `.md`, `.txt`, or `.json` documents into source entries

Analysis behavior:

- If no provider variables are set, analysis uses deterministic local logic and retrieval uses the source registry.
- If `AI_PROVIDER=watsonx`, analysis attempts watsonx model inference.
- If `RAG_PROVIDER=watsonx`, retrieval attempts the WatsonX vector index.
- If watsonx call fails, backend falls back to deterministic analysis and records a warning.
- If retrieval returns no citations, the backend returns an `unknown` or low-confidence result and recommends human planning review.
- `POST /api/v1/projects/{project_id}/analyze` also accepts `clarification_answers`, allowing the frontend to pause for follow-up questions and re-run the orchestration with added user detail.

Run backend tests:

- `cd apps/api`
- `pytest -q`

Frontend expects backend at `http://localhost:8000`.

## Deploy Web to Vercel

This repo includes a root `vercel.json` for the Vite frontend:

- Build command: `npm run build:web`
- Output directory: `apps/web/dist`
- Install command: `npm install`

Production builds should set the deployed API URL explicitly:

- `VITE_API_URL=https://your-api-host.example`

To avoid browser CORS failures, set this variable in the API host after Vercel gives you a deployment URL:

- `CORS_ALLOW_ORIGINS=https://your-vercel-project.vercel.app`

For a quick smoke test, the API can temporarily use `CORS_ALLOW_ORIGINS=*`, but the deployed app should use the exact Vercel origin.
