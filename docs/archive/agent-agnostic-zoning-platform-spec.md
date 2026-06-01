# Agent-Agnostic Zoning Platform Spec

## What

Convert the inherited IBM zoning assistant into a standalone, provider-agnostic zoning platform that can run without IBM watsonx credentials, support future LLM/RAG providers, expand beyond Blacksburg, and provide a more trustworthy user interface around citations, confidence, and jurisdiction coverage. The first implementation phase should create the clean seams for provider selection and rebranding while preserving the existing frontend/backend API behavior.

## Context

This project now lives as a new side-project repository at `C:\Users\abhih\Zoning-Agent-App`, copied from the old IBM-oriented repo with a fresh Git history. The old repo should be treated as source history only; all new implementation work should happen in the new repo.

Today the app is a monorepo:

- `apps/web`: React + TypeScript + Vite frontend.
- `apps/api`: FastAPI backend.
- `packages/shared-schema`: frontend TypeScript contracts.
- `services/ingestion`: local document ingestion helper and sample zoning documents.

The current backend already has a visible three-stage flow:

- intent extraction in `apps/api/app/services.py`
- zoning retrieval in `retrieve_zoning_context(...)`
- compliance/checklist synthesis in `analyze_project(...)`

The main coupling problems are:

- `apps/api/app/services.py` directly imports `generate_watsonx_analysis`, `is_watsonx_enabled`, and `search_ordinances` from `apps/api/app/watsonx_client.py`.
- environment variables are IBM-specific: `WATSONX_ENABLED`, `WATSONX_API_KEY`, `WATSONX_URL`, `WATSONX_PROJECT_ID`, `WATSONX_MODEL_ID`, and `IBM_ZONING_DB_PATH`.
- product naming is still IBM-specific across `README.md`, package names, frontend copy, and Python package metadata.
- address validation is hard-coded to Blacksburg, VA in `normalize_address(...)`.
- local ingestion imports document excerpts into a source registry, but `/ingestion/reindex` does not rebuild a real searchable index.

Important existing contracts:

- `POST /api/v1/projects/intake` returns `IntakeResponse`.
- `POST /api/v1/projects/{project_id}/analyze` returns `AnalyzeResult`.
- the frontend maps backend snake_case fields into camelCase in `apps/web/src/api.ts`.
- the shared response shape includes `agents`, `feasibility`, `checklist`, `citations`, `disclaimers`, `follow_up_questions`, and `warnings`.

## Requirements

1. The new repo must run without IBM watsonx credentials.
2. The first implementation phase must preserve the existing public API response shapes consumed by `apps/web/src/api.ts`.
3. WatsonX support may remain as an optional legacy provider, but no core analysis path may depend on WatsonX-only imports.
4. Provider choice must be controlled by generic environment variables, not Watson-specific feature flags.
5. Tests must be able to run offline without network calls to IBM, Google, OpenAI, Anthropic, or any other external service.
6. Deterministic behavior must remain available as a fallback provider for local development and tests.
7. The app must continue returning `unknown` or `low_confidence` when evidence is missing rather than fabricating a zoning conclusion.
8. Product naming must move away from IBM-specific branding in user-visible UI, package names, documentation, and environment variable names.
9. Jurisdiction expansion must be data-driven, but the first phase may only introduce the model/config shape and preserve current Blacksburg behavior.
10. Future implementation phases must be decomposable so subagents can own non-overlapping areas: backend provider layer, ingestion/RAG, jurisdiction mapping, frontend UI, tests/docs.

## Design

### Phase 1: Repository Identity and Provider Boundary

Goal: make the side-project repo independent from IBM naming and WatsonX coupling without changing the user-facing analysis workflow.

Backend changes:

- Add `apps/api/app/settings.py` for environment parsing.
- Add `apps/api/app/ai/` with provider-neutral interfaces:
  - `AnalysisProvider`
  - `RetrievalProvider`
  - provider selection helpers
- Move WatsonX calls behind an optional adapter:
  - `apps/api/app/ai/watsonx_provider.py`
- Add deterministic/local adapters:
  - `apps/api/app/ai/deterministic_provider.py`
  - `apps/api/app/ai/source_registry_retriever.py`
- Update `apps/api/app/services.py` so it depends on generic providers rather than importing `app.watsonx_client` directly.
- Keep `apps/api/app/watsonx_client.py` temporarily as low-level legacy client code used only by the WatsonX adapter.

Environment variables:

- Add `ZONING_DB_PATH` as the preferred database path.
- Keep `IBM_ZONING_DB_PATH` as a backward-compatible fallback for one transition period.
- Add `AI_PROVIDER=deterministic|watsonx`.
- Add `RAG_PROVIDER=source_registry|watsonx`.
- Keep WatsonX credential variables only when `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`.

Frontend and package changes:

- Rename root package from `ibm-zoning-app` to a neutral name such as `zoning-agent-app`.
- Rename workspaces from `@ibm-zoning/*` to neutral package names.
- Update user-visible copy in `apps/web/src/App.tsx` from IBM-specific branding to neutral branding.
- Update `README.md` quick start and environment variable docs.
- Keep API route URLs unchanged for now.

Testing:

- Update tests so default configuration uses deterministic/local providers.
- Keep WatsonX tests isolated to WatsonX adapter behavior and mocked HTTP responses.
- Add tests proving `analyze_project(...)` works when no WatsonX environment variables are present.

### Phase 2: Local Retrieval and Ingestion

Goal: turn source registry excerpts into a real retrieval layer.

Backend changes:

- Introduce document/chunk models separate from `SourceRegistryEntry`.
- Add stable chunk IDs derived from source ID, section reference, and chunk index.
- Add metadata for jurisdiction, district, use, source type, URL, effective date, and retrieval timestamp.
- Implement reindex behavior for `/api/v1/ingestion/reindex`.
- Start with keyword and metadata retrieval over SQLite/source registry before adding a vector database.

Dependency decision:

- Do not add ChromaDB, pgvector, or embedding providers in Phase 1.
- In Phase 2, choose the smallest local retrieval implementation that provides testable improvement.
- Vector search should be added only after chunk metadata and deterministic retrieval are working.

### Phase 3: Jurisdiction Support

Goal: replace hard-coded Blacksburg support with jurisdiction metadata.

Backend changes:

- Add a jurisdiction config file or table, likely `apps/api/app/data/jurisdictions.json`.
- Add jurisdiction fields to project and source models:
  - `jurisdiction_id`
  - `jurisdiction_name`
  - optional planning department contact fields
- Add intake status support for:
  - valid supported address
  - valid unsupported jurisdiction
  - invalid address
- Preserve the existing Blacksburg behavior as the first supported jurisdiction.

Frontend changes:

- Show jurisdiction support status near the address field.
- Distinguish "unsupported area" from "invalid address."
- Show planning department fallback details when a jurisdiction is unsupported.

### Phase 4: Agent Quality and Trust

Goal: improve reliability of AI-assisted synthesis after provider and retrieval boundaries are stable.

Backend changes:

- Define strict structured output models for compliance synthesis.
- Validate model output through Pydantic before returning `AnalyzeResult`.
- Add citation coverage checks:
  - no citations means `decision=unknown`
  - weak metadata match lowers confidence
  - retrieval errors add warnings
- Save provider and retrieval trace details in audit events or a future trace table.

Frontend changes:

- Improve evidence display.
- Add confidence/source coverage indicators.
- Make warnings more visible and actionable.

### Phase 5: Product UI Pass

Goal: turn the app from a proof of concept into a planning workspace.

Frontend changes:

- Replace the current large introductory panel with a denser operational workflow.
- Add structured intake controls for common zoning facts:
  - use type
  - construction scope
  - operating hours
  - employee count
  - parking/loading
  - food/fire/health triggers
- Add side-by-side answer/evidence views after analysis.
- Improve admin ingestion:
  - source status
  - index status
  - document history
  - source health checks

## Decisions

### Decision: Start With Provider Interfaces, Not a New LLM Vendor

Choice: Phase 1 will add provider interfaces and deterministic/local providers before adding OpenAI, Anthropic, Ollama, ChromaDB, or pgvector.

Alternatives considered:

- Add OpenAI immediately.
- Add ChromaDB immediately.
- Rewrite the agent flow around a third-party agent framework.

Why this choice:

- The immediate blocker is WatsonX dependency, not lack of another model.
- Offline tests and predictable behavior are more important than model quality in the first refactor.
- Provider interfaces let future LLM integrations be added without changing the API contract again.

Reversible: yes. New providers can be added behind the same interface.

### Decision: Preserve API Shapes During Phase 1

Choice: Keep `IntakeResponse` and `AnalyzeResult` compatible with the current frontend.

Alternatives considered:

- Redesign backend responses at the same time as provider refactor.
- Split agent results into multiple new endpoints.

Why this choice:

- It keeps the first implementation phase narrow.
- The frontend can continue working while backend internals change.
- Later UI improvements can evolve the contract deliberately.

Reversible: partially. Contract changes are possible later, but they should be versioned or coordinated with frontend changes.

### Decision: Keep WatsonX as Optional Legacy Adapter

Choice: Do not delete `watsonx_client.py` in Phase 1. Hide it behind `WatsonXProvider`.

Alternatives considered:

- Delete all WatsonX code immediately.
- Leave current imports in `services.py`.

Why this choice:

- It avoids a large risky deletion during the boundary refactor.
- Existing WatsonX tests can be moved rather than thrown away.
- It documents how to add future providers.

Reversible: yes. The adapter can be removed once the project no longer needs legacy support.

### Decision: Use Source Registry Retrieval as the First Local RAG Provider

Choice: `RAG_PROVIDER=source_registry` should search existing `SourceRegistryEntry` records using current district/use metadata.

Alternatives considered:

- Add vector search immediately.
- Fetch live ordinance pages immediately.

Why this choice:

- The source registry already exists.
- It is deterministic and easy to test.
- It creates a working no-IBM path before adding more infrastructure.

Reversible: yes. The retrieval interface should support later vector and hybrid providers.

### Decision: Introduce Jurisdiction Models Before Broad Expansion

Choice: Phase 3 should define jurisdiction metadata before adding multiple cities.

Alternatives considered:

- Hard-code Christiansburg, Montgomery County, and Roanoke checks directly in `normalize_address(...)`.
- Keep using address keyword matching only.

Why this choice:

- Hard-coded geography will repeat the current Blacksburg limitation.
- Jurisdiction-specific source filtering is essential for trustworthy citations.

Reversible: no for the general direction. Exact storage format is reversible.

### Assumption: New Work Happens in the Side-Project Repo

All implementation work covered by this spec should happen under `C:\Users\abhih\Zoning-Agent-App`, not `C:\Users\abhih\IBM-Zoning-App`.

## Versions

Existing runtime and package constraints from the repo:

- API Python runtime: `>=3.11` from `apps/api/pyproject.toml`.
- Backend dependencies: FastAPI, Uvicorn, Pydantic 2, HTTPX, python-dotenv.
- Web app: React + TypeScript + Vite as currently configured in `apps/web`.
- Package manager: current repo uses `package-lock.json`, so npm is the baseline package manager unless deliberately changed.

Phase 1 should not introduce new external AI or vector database dependencies. Future specs should pin and verify versions when choosing OpenAI, Anthropic, Ollama, ChromaDB, pgvector, or other new runtime dependencies.

## Invariants

- `POST /api/v1/projects/{project_id}/analyze` must return the existing `AnalyzeResult` shape.
- `apps/web/src/api.ts` must not need a breaking response mapping change in Phase 1.
- Missing citations must never produce a high-confidence zoning decision.
- External model/provider failures must degrade to warnings plus deterministic fallback when possible.
- Tests must not require live API credentials by default.
- `.env` and runtime SQLite databases must remain untracked.
- The old IBM repo must not be mutated by implementation work for this side project.

## Error Behavior

Provider selection:

- Unknown `AI_PROVIDER` or `RAG_PROVIDER` should fail fast at startup or first use with a clear configuration error.
- Missing WatsonX credentials should only error when the WatsonX provider is selected.
- Deterministic/source-registry providers should not require network credentials.

Retrieval:

- Retrieval exceptions should produce a warning and no citations.
- No citations should force `decision=unknown` or low-confidence behavior.
- Source registry parse errors should report which source failed when possible.

Analysis:

- Invalid model JSON should not leak raw provider output to the frontend.
- Invalid model JSON should produce a warning and use deterministic fallback.
- Compliance output should be validated before becoming an `AnalyzeResult`.

Address/jurisdiction:

- Invalid address means the address could not be normalized.
- Unsupported jurisdiction means the address is valid but the app lacks source coverage.
- These states must be distinguishable in future API and UI changes.

## Testing Strategy

Phase 1 tests:

- Unit test provider selection for default deterministic/source-registry behavior.
- Unit test that WatsonX credentials are not required unless a WatsonX provider is selected.
- Unit test that source registry retrieval returns citations based on district/use filters.
- Unit test that no citations produces low-confidence or unknown analysis.
- Update existing WatsonX tests so they target the adapter/client layer with mocked HTTP responses.
- Run `pytest -q` from `apps/api`.
- Run `npm run typecheck:web` from repo root after package renaming.
- Run `npm run build:web` from repo root after frontend copy changes.

Phase 2 tests:

- Import local sample documents.
- Reindex them.
- Verify stable chunk IDs.
- Verify retrieval filters by jurisdiction/district/use.

Phase 3 tests:

- Valid supported jurisdiction returns created project.
- Valid unsupported jurisdiction returns a distinct unsupported state.
- Invalid address still returns invalid-address behavior.
- Existing Blacksburg tests keep passing.

Phase 4 tests:

- Invalid provider JSON falls back safely.
- Missing citations cannot produce high-confidence positive decisions.
- Prompt/schema drift is caught by Pydantic validation tests.

Frontend tests are not currently configured. For UI phases, add the smallest practical verification path first: TypeScript checks, production build, and manual browser verification.

## Delegation Plan

This work can be split among subagents after the spec is approved:

- Backend provider worker: owns `apps/api/app/ai/`, `apps/api/app/settings.py`, and updates to `services.py`.
- Backend tests worker: owns `apps/api/tests/*` changes for provider behavior and fallback guarantees.
- Branding/frontend worker: owns `package.json`, workspace package names, `apps/web/src/*`, and README copy.
- Ingestion/RAG worker: later owns `apps/api/app/ingestion.py`, retrieval indexing, and source/chunk models.
- Jurisdiction worker: later owns jurisdiction config, address normalization states, and source jurisdiction metadata.

Workers should not edit each other's owned files without coordination. Shared contract changes in `apps/api/app/models.py`, `packages/shared-schema/src/index.ts`, or `apps/web/src/api.ts` require explicit coordination.

## Out of Scope

- Adding a production LLM provider in Phase 1.
- Adding ChromaDB, pgvector, or embeddings in Phase 1.
- Fetching live zoning documents from municipal websites in Phase 1.
- Full multi-jurisdiction support in Phase 1.
- Authentication, user accounts, saved projects, or billing.
- Legal review of zoning outputs.
- Deploying the new side-project app to production.
