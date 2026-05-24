# Claude Code Continuation Handoff

Last updated: May 23, 2026

## Section 0 Completion (Antigravity – May 23 2026)

**Branch**: `main`
**Checkpoint commits**:
- `341323f` – feat: add single orchestrator and chroma local rag _(Codex)_
- `4dc6313` – fix: break circular import between app.rag and app.ai; protect tmp dirs in gitignore _(Antigravity stabilization)_

**Verification results after stabilization**:

```text
pytest -q   →  70 passed, 1 skipped
pytest -q tests/test_rag_phase2.py  →  3 passed
npm run typecheck:web  →  clean
npm run build:web      →  clean (203 kB bundle)
secret scan  →  no secrets found
```

**Bugs fixed during stabilization**:

1. **Circular import** (`app.rag ↔ app.ai`): `hybrid_local_retriever.py` imported
   `ChromaVectorStore` at module level, which cycled through `app.ai.__init__` →
   `app.ai.registry` → back into `app.rag.vector_store` before it finished loading.
   Fixed by moving the import to a lazy `from app.rag.vector_store import ChromaVectorStore`
   inside `_retrieve_with_chroma()`. This also required updating the monkeypatch target in
   `test_ai_providers.py` from `app.ai.hybrid_local_retriever.ChromaVectorStore.query` to
   `app.rag.vector_store.ChromaVectorStore.query`.

2. **Missing gitignore entries**: `.tmp/` and `.tmp-*/` added to protect pytest basetemp
   dirs (`.tmp-pytest-api-*`, etc.) from being committed. Chroma path and `*.sqlite3` were
   already protected.

**Status**: Section 0 complete. Ready to begin Section 1 (Phase 2 Hardening).

## Purpose

Continue the zoning platform conversion from an IBM-oriented/multi-agent prototype into a provider-agnostic, locally runnable, single-orchestrator zoning assistant.

The user wants to keep using free/local infrastructure while the app is early-stage. Do not introduce paid-only requirements. ChromaDB embedded `PersistentClient` is the chosen Phase 2 vector store for now; Postgres/pgvector can wait.

Use at most 2 subagents if delegating work.

## Repo State To Preserve

- Local repo: `C:\Users\abhih\Zoning-Agent-App`
- Current branch at handoff time: `main`
- There are substantial uncommitted changes from Codex. Do not revert them.
- Treat the current working tree as the baseline continuation state.
- Before making new changes, run:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
git status --short
```

Recommended first action:

1. Review the current diff.
2. Run the verification commands below.
3. Create a checkpoint branch/commit if the user wants a recoverable handoff point.

Do not run destructive git commands such as `git reset --hard`, `git checkout -- .`, or broad file cleanup.

## What Is Already Implemented

### Phase 1: Single Orchestrator Architecture

The old visible three-agent framing has been replaced by a single orchestrator mental model.

Important files:

- `apps/api/app/orchestrator/zoning_orchestrator.py`
- `apps/api/app/orchestrator/pipeline_context.py`
- `apps/api/app/orchestrator/pipeline_events.py`
- `apps/api/app/tools/intake_tool.py`
- `apps/api/app/tools/compliance_tool.py`
- `apps/api/app/tools/citation_tool.py`
- `apps/api/app/tools/report_tool.py`
- `apps/api/app/services.py`
- `apps/api/app/routers/api.py`
- `apps/web/src/App.tsx`

Current behavior:

- `apps/api/app/services.py` is now mostly a compatibility facade.
- `ZoningOrchestrator` coordinates intake, retrieval, compliance, validation, and report output.
- API response keeps compatibility fields while adding `pipeline`, `pipeline_stages`, and `citation_validation`.
- Frontend no longer presents the workflow as three autonomous agents.
- Audit/trace events include structured `details`.
- `/api/v1/projects/{project_id}/trace` is admin-protected when `ADMIN_ACCESS_KEY` is configured.

Provider support:

- `AI_PROVIDER=deterministic|openai|watsonx|local`
- `RAG_PROVIDER=source_registry|hybrid_local|watsonx`
- `EMBEDDING_PROVIDER=none|local|openai`
- `AI_PROVIDER=local` uses an OpenAI-compatible local chat completions endpoint.
- WatsonX remains optional legacy support only.

### Phase 2: Local RAG With ChromaDB

Phase 2 foundation has been implemented.

Important files:

- `apps/api/app/rag/vector_store.py`
- `apps/api/app/rag/__init__.py`
- `apps/api/app/ingestion.py`
- `apps/api/app/ai/hybrid_local_retriever.py`
- `apps/api/app/ai/source_registry_retriever.py`
- `apps/api/app/models.py`
- `apps/api/app/repositories.py`
- `apps/api/app/database.py`
- `apps/api/app/routers/api.py`
- `apps/api/alembic/versions/202605230001_phase2_source_vector_metadata.py`
- `apps/api/tests/test_rag_phase2.py`

Current behavior:

- SQL remains the source of truth for source records and chunk records.
- ChromaDB is a rebuildable vector index selected with `VECTOR_PROVIDER=chroma`.
- `.md`, `.txt`, and `.json` imports preserve `full_text`.
- `excerpt` remains the preview field for compatibility.
- Reindex builds deterministic chunk IDs based on source, section, chunk index, and content hash.
- Reindex computes embeddings and upserts vectors into Chroma when enabled.
- Reindex removes stale Chroma vector IDs.
- Ingestion status reports:
  - `vector_provider`
  - `vector_index_ready`
  - `vector_count`
  - `vector_collection`
  - `vector_readiness_warnings`
- `hybrid_local` attempts Chroma retrieval first when configured, combines vector score with keyword scoring, and falls back safely if Chroma is unavailable.
- Source Admin shows vector readiness.

Environment additions:

```dotenv
VECTOR_PROVIDER=chroma
CHROMA_PATH=apps/api/app/data/chroma
CHROMA_COLLECTION=zoning_source_chunks
CHROMA_RESET_ON_REINDEX=false
```

Dependency added:

```toml
chromadb>=1.5.0,<1.6.0
```

## Last Known Verification

These passed after the Phase 2 implementation:

```powershell
cd C:\Users\abhih\Zoning-Agent-App\apps\api
pytest -q --basetemp ..\..\.tmp-pytest-api-phase2-final
```

Result:

```text
70 passed, 1 skipped
```

```powershell
cd C:\Users\abhih\Zoning-Agent-App
npm run typecheck:web
npm run build:web
```

Both passed.

## Important Constraints

- Keep deterministic local mode working.
- Keep provider-agnostic interfaces.
- Keep WatsonX optional; do not make IBM required.
- Do not require OpenAI credentials for tests.
- Do not fine-tune models yet.
- Do not make the model the source of zoning truth.
- Every final zoning claim should be citation-grounded, an assumption, or an unknown.
- Unsupported jurisdictions should not look like invalid addresses.
- Do not commit secrets.
- Do not broadly rewrite the frontend unless the task specifically requires it.
- Do not remove compatibility fields from API responses without updating `packages/shared-schema`, `apps/web`, and tests together.

## Recommended Next Work

### 0. Stabilize The Handoff State

Goal: make the current Codex changes easy to review later.

Tasks:

1. Run `git status --short`.
2. Review the new files and major diffs.
3. Run the verification commands above.
4. If everything passes, create a checkpoint branch and commit only the current intended changes.

Suggested branch name:

```text
codex/single-orchestrator-chroma-rag
```

Suggested commit message:

```text
feat: add single orchestrator and chroma local rag
```

Acceptance criteria:

- Backend tests pass.
- Web typecheck and build pass.
- No generated Chroma database files are committed.
- No secrets are committed.

### 1. Finish Phase 2 Hardening

Goal: make the Chroma-backed local RAG pipeline robust enough for real local/admin usage.

Tasks:

1. Add `.gitignore` protection for local vector/index artifacts if missing:
   - `apps/api/app/data/chroma/`
   - local SQLite files
   - temporary pytest folders
2. Verify Chroma works with a real installed dependency, not only fake tests:
   - import docs
   - reindex
   - confirm vector count
   - analyze supported project
   - confirm chunk-backed citations
3. Add or strengthen tests for:
   - real Chroma integration when `chromadb` is installed, skipped otherwise
   - `VECTOR_PROVIDER=chroma` with Chroma unavailable returns readiness warnings
   - stale source text refreshes SQL chunks and Chroma vector records
4. Improve chunking:
   - split markdown by headings/sections before falling back to character limits
   - preserve section references in chunk metadata where possible
   - avoid chunks that are too short to be useful
5. Improve vector metadata filters:
   - jurisdiction
   - source type
   - district
   - use
   - effective date
6. Make retrieval diagnostics visible in trace details:
   - query text
   - filters
   - SQL chunk count
   - Chroma vector count/hit count
   - fallback reason when Chroma is unavailable

Acceptance criteria:

- `RAG_PROVIDER=hybrid_local`, `EMBEDDING_PROVIDER=local`, `VECTOR_PROVIDER=chroma` returns chunk-backed citations after reindex.
- Zero vector hits produce unknown/low-confidence output, not invented claims.
- Chroma can be deleted and rebuilt from SQL source/chunk records.
- Tests still pass without paid credentials.

### 2. Move Location Resolution Fully Into Tools

Goal: finish the architectural cleanup so the orchestrator owns the whole pipeline internally.

Current limitation:

- `/api/v1/projects/intake` still performs live address normalization and jurisdiction detection before analysis.
- The orchestrator receives already-normalized location context.

Tasks:

1. Add or complete:
   - `apps/api/app/tools/address_tool.py`
   - `apps/api/app/tools/jurisdiction_tool.py`
   - optionally `apps/api/app/tools/parcel_tool.py`
2. Preserve the existing intake endpoint behavior while routing logic through these tools.
3. Keep unsupported jurisdiction distinct from invalid address.
4. Ensure the orchestrator trace records:
   - address normalization
   - jurisdiction resolution
   - district resolution
   - unsupported jurisdiction early exit

Acceptance criteria:

- Existing frontend still works.
- Existing endpoint shapes still work.
- Address suggestions continue working.
- Supported and unsupported jurisdiction tests still pass.

### 3. Real Parcel And Zoning District Lookup

Goal: reduce dependence on keyword district guesses.

Tasks:

1. Define a parcel/zoning lookup interface:
   - input: normalized address, lat/lng, jurisdiction
   - output: parcel ID, zoning district, overlays, confidence, warnings
2. Implement deterministic/local adapters first:
   - JSON fixtures for tests
   - manual mapping table for known beta addresses
3. Add optional live adapters later:
   - municipal GIS
   - county parcel APIs
   - uploaded GIS exports
4. Update frontend trust indicators to show whether district came from:
   - official parcel lookup
   - configured local mapping
   - keyword fallback
   - unknown

Acceptance criteria:

- Missing zoning district produces `unknown`/low confidence.
- Retrieval uses district filters only when district confidence is adequate.
- Trace shows lookup method and confidence.

### 4. Upgrade Compliance Reasoning

Goal: make compliance synthesis stronger while keeping citations as the source of truth.

Tasks:

1. Add prompt templates:
   - `apps/api/app/prompts/intake_extraction.md`
   - `apps/api/app/prompts/compliance_synthesis.md`
   - `apps/api/app/prompts/evidence_grading.md`
2. Add a structured compliance schema if current `AnalysisProviderResult` is too small:
   - feasibility status
   - confidence
   - findings
   - permit path
   - warnings
   - unresolved questions
   - citation chunk IDs
3. Add provider method for strict JSON model output.
4. Ensure model outputs are validated before report generation.
5. Preserve deterministic compliance fallback.

Compliance prompt rules:

- Only use provided chunks.
- Do not invent citation IDs.
- Return unknown if evidence is missing.
- Return conditional/unknown if evidence conflicts.
- Return JSON only.

Acceptance criteria:

- Invalid citation IDs are rejected or removed.
- No high-confidence result with zero citations.
- Unsupported claims are flagged.
- Deterministic tests still require no OpenAI/local model server.

### 5. Add Caching And Version Invalidation

Goal: reduce cost/latency as usage grows.

Suggested cache keys:

- `address_normalization:{normalized_raw_address}`
- `jurisdiction:{lat}:{lng}`
- `retrieval:{jurisdiction_id}:{district}:{use_type}:{scope}:{source_version}`
- `analysis:{request_hash}:{source_index_version}:{provider}:{prompt_version}`

Tasks:

1. Add a small cache abstraction with SQLite/local backend first.
2. Store source index version and prompt/schema version.
3. Invalidate retrieval/analysis cache when:
   - source document changes
   - reindex runs
   - jurisdiction metadata changes
   - district mapping changes
   - model provider changes
   - prompt/schema version changes

Acceptance criteria:

- Default local mode works with no external cache service.
- Cache does not hide source updates after reindex.
- Trace shows cache hits/misses.

### 6. Frontend Trust UX

Goal: make evidence and uncertainty easier to inspect.

Tasks:

1. Keep current flow, but improve result layout:
   - Answer/checklist on left
   - Evidence/citations on right for desktop
   - tabs or stacked layout on mobile
2. Add trust indicators:
   - jurisdiction analyzed
   - zoning district
   - district lookup confidence/source
   - source count
   - citation count
   - vector readiness
   - last source update
3. Improve unsupported jurisdiction state:
   - valid address but not supported
   - planning contact if configured
   - what source coverage is missing
4. Keep legal disclaimer prominent.

Acceptance criteria:

- Users can see which evidence was used.
- Unsupported jurisdictions do not look like system errors.
- No UI copy suggests multiple autonomous agents.
- `npm run typecheck:web` and `npm run build:web` pass.

### 7. Evaluation And Golden Tests

Goal: make future agent/model changes reviewable.

Tasks:

1. Create `apps/api/tests/golden/`.
2. Add scenario JSON files:
   - supported jurisdiction with enough evidence
   - supported jurisdiction with no citations
   - unsupported jurisdiction
   - invalid address
   - clarification required
   - fake citation ID from model output
   - conflicting evidence
   - missing zoning district
3. Add a pytest runner that validates:
   - allowed statuses
   - required warnings
   - citation requirements
   - confidence ceilings
4. Store anonymized evaluation traces for future fine-tuning/evaluation.

Acceptance criteria:

- Golden tests pass locally without paid AI providers.
- New retrieval/compliance changes can be judged against stable scenarios.

### 8. Deployment Notes For Free Plans

Goal: keep the app usable without paid infrastructure.

Current recommended free/staging setup:

- Render API
- Vercel frontend
- Supabase free Postgres for SQL source of truth
- Chroma embedded path for local/dev

Open question:

- Render free disk may not be durable enough for Chroma index state.

Recommended approach for now:

1. Treat Chroma as rebuildable.
2. Keep SQL source/chunks as durable truth.
3. Reindex after deploy or add a controlled startup/admin rebuild flow.
4. Surface readiness warnings if vectors are missing.
5. Do not introduce pgvector until production usage justifies it.

## Suggested Verification Commands

Backend:

```powershell
cd C:\Users\abhih\Zoning-Agent-App\apps\api
pytest -q
alembic upgrade head
```

Frontend:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
npm run typecheck:web
npm run build:web
```

Secret/placeholder checks:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
rg "postgresql://[^\s]+:[^\[<\s][^@\s]+@|BETA_ACCESS_KEY=[A-Za-z0-9_*@!-]{8,}|ADMIN_ACCESS_KEY=[A-Za-z0-9_*@!-]{8,}" README.md .env.example render.yaml docs apps services -g "!apps/api/tests/**"
rg "example\.gov" apps\api\app\data services\ingestion apps\web packages
```

Local Chroma smoke:

```powershell
cd C:\Users\abhih\Zoning-Agent-App\apps\api
$env:RAG_PROVIDER="hybrid_local"
$env:EMBEDDING_PROVIDER="local"
$env:VECTOR_PROVIDER="chroma"
pytest -q tests\test_rag_phase2.py
```

## What To Leave For Codex Review Later

When handing back to Codex, include:

1. Branch name and commit hash.
2. Summary of changed files.
3. Which recommended next-work section(s) were completed.
4. Verification command outputs.
5. Any skipped tests and why.
6. Any product or architecture decisions made.
7. Any new env vars or deployment requirements.
