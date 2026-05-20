# Agent-Agnostic Zoning Platform Ticket Plan

Source spec: `docs/agent-agnostic-zoning-platform/spec.md`

This plan breaks the spec into tickets sized for focused implementation, review, and rollback. The order is intentional: start by protecting the new side-project identity, then remove WatsonX coupling, then deepen retrieval, jurisdiction support, trust, and UI.

## Shared Decisions

- New implementation work belongs in `C:\Users\abhih\Zoning-Agent-App`, not the old IBM repo.
- Phase 1 must preserve the existing API response shape consumed by `apps/web/src/api.ts`.
- The default backend path must run without IBM watsonx credentials.
- WatsonX can remain as an optional legacy adapter, but `apps/api/app/services.py` must stop importing WatsonX client functions directly.
- New external AI/vector dependencies are out of scope until the provider and retrieval seams exist.

## Ticket 1: Rebrand Repository and Package Identity

### Goal

Rename user-visible and package-level IBM branding so the side project stands on its own before deeper architecture work begins.

### Context

The project was copied into a fresh repo, but names still reference IBM in `README.md`, root `package.json`, workspace package names, frontend copy, and Python package metadata.

### Relevant Files or References

- `README.md`
- `package.json`
- `apps/web/package.json`
- `packages/shared-schema/package.json`
- `apps/api/pyproject.toml`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `docs/agent-agnostic-zoning-platform/spec.md`

### Proposed Approach

Rename the app to a neutral working name such as `zoning-agent-app`. Update npm workspace names, Python package name/description, visible frontend copy, README headings, and API client imports. Keep route paths and response contracts unchanged.

### Acceptance Criteria

- No user-facing UI copy says `IBMinds`, `IBM Zoning`, or similar IBM-branded product names.
- Root npm package and workspace package names are neutral.
- Python project metadata is neutral.
- The frontend still imports the shared schema successfully after package renaming.
- README quick start reflects the new project name.

### Source Reference

Spec sections: `Requirements`, `Design / Phase 1`, `Decisions / Preserve API Shapes During Phase 1`.

### Verify

- `npm install`
- `npm run typecheck:web`
- `npm run build:web`
- From `apps/api`: `pytest -q`

### Out of Scope

- UI redesign.
- Changing API route paths.

## Ticket 2: Add Backend Settings Module and Generic Environment Variables

### Goal

Centralize backend configuration and introduce provider-neutral environment variables.

### Context

Configuration is currently read ad hoc through `os.getenv(...)`, including `WATSONX_ENABLED` and `IBM_ZONING_DB_PATH`.

### Relevant Files or References

- `apps/api/app/services.py`
- `apps/api/app/storage.py`
- `apps/api/app/watsonx_client.py`
- `apps/api/pyproject.toml`
- `.env.example`
- `README.md`

### Proposed Approach

Add `apps/api/app/settings.py` with typed settings helpers for `AI_PROVIDER`, `RAG_PROVIDER`, `ZONING_DB_PATH`, Google Maps settings, and legacy WatsonX settings. Update storage to prefer `ZONING_DB_PATH` while temporarily accepting `IBM_ZONING_DB_PATH`. Document the new variables.

### Acceptance Criteria

- Default settings select deterministic analysis and source registry retrieval.
- `ZONING_DB_PATH` works as the preferred database path.
- `IBM_ZONING_DB_PATH` still works as a backward-compatible fallback.
- Unknown `AI_PROVIDER` or `RAG_PROVIDER` produces a clear configuration error.
- Missing WatsonX credentials do not error unless a WatsonX provider is selected.

### Source Reference

Spec sections: `Requirements`, `Design / Phase 1`, `Error Behavior / Provider selection`.

### Verify

- From `apps/api`: `pytest -q`
- Manual check with no WatsonX environment variables: backend imports and tests run.

### Out of Scope

- Adding OpenAI, Anthropic, Ollama, ChromaDB, or pgvector.

## Ticket 3: Introduce Provider-Neutral AI Interfaces

### Goal

Create explicit interfaces for analysis and retrieval so orchestration code no longer depends on WatsonX-specific functions.

### Context

`apps/api/app/services.py` currently imports `generate_watsonx_analysis`, `is_watsonx_enabled`, and `search_ordinances` directly.

### Relevant Files or References

- `apps/api/app/services.py`
- `apps/api/app/watsonx_client.py`
- `apps/api/app/models.py`
- `docs/agent-agnostic-zoning-platform/spec.md`

### Proposed Approach

Create `apps/api/app/ai/` with interface/protocol definitions for analysis and retrieval providers. Include request/response dataclasses or Pydantic models for provider inputs and outputs. Add provider selection helpers that read from `settings.py`.

### Acceptance Criteria

- `apps/api/app/ai/` exists with provider-neutral contracts.
- Provider outputs can represent decision, summary, required permits, follow-up questions, warnings, and citations.
- The contracts are independent of WatsonX response shapes.
- The interfaces are documented enough for future provider implementations.

### Source Reference

Spec sections: `Design / Phase 1`, `Decisions / Start With Provider Interfaces, Not a New LLM Vendor`.

### Verify

- From `apps/api`: `pytest -q`
- Static import check by starting Python and importing `app.ai`.

### Out of Scope

- Rewriting all analysis logic in this ticket.

## Ticket 4: Implement Deterministic Analysis and Source Registry Providers

### Goal

Make the default no-IBM path explicit through deterministic analysis and source registry retrieval providers.

### Context

The current fallback logic is embedded directly inside `services.py`. Source registry retrieval already exists but is not packaged as a provider.

### Relevant Files or References

- `apps/api/app/services.py`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`
- `apps/api/app/data/source_registry.json`
- `services/ingestion/documents/*`

### Proposed Approach

Add `deterministic_provider.py` and `source_registry_retriever.py` under `apps/api/app/ai/`. Move or wrap existing deterministic feasibility and source filtering logic into these providers while preserving current behavior.

### Acceptance Criteria

- `AI_PROVIDER=deterministic` works without any WatsonX settings.
- `RAG_PROVIDER=source_registry` retrieves matching citations from stored sources.
- Missing citations produce `unknown` or `low_confidence` behavior.
- Existing sample source behavior remains intact.

### Source Reference

Spec sections: `Requirements`, `Design / Phase 1`, `Decisions / Use Source Registry Retrieval as the First Local RAG Provider`.

### Verify

- From `apps/api`: `pytest -q`
- Add or update tests that call `analyze_project(...)` with no WatsonX env vars.

### Out of Scope

- Real vector search.
- New document chunking.

## Ticket 5: Wrap WatsonX as an Optional Legacy Provider

### Goal

Keep WatsonX support available while removing WatsonX imports from core orchestration.

### Context

WatsonX calls currently live in `apps/api/app/watsonx_client.py`, and the orchestration layer imports them directly.

### Relevant Files or References

- `apps/api/app/watsonx_client.py`
- `apps/api/app/services.py`
- `apps/api/tests/test_watsonx_client.py`
- `apps/api/app/ai/`

### Proposed Approach

Create `apps/api/app/ai/watsonx_provider.py` that adapts the low-level WatsonX client to the generic analysis and retrieval provider interfaces. Update WatsonX tests so they target the adapter and low-level client with mocked HTTP.

### Acceptance Criteria

- `services.py` no longer imports from `app.watsonx_client`.
- WatsonX code is only used when `AI_PROVIDER=watsonx` or `RAG_PROVIDER=watsonx`.
- Missing WatsonX credentials do not affect deterministic/source-registry tests.
- Existing WatsonX client tests still validate retry/error behavior through mocks.

### Source Reference

Spec sections: `Design / Phase 1`, `Decisions / Keep WatsonX as Optional Legacy Adapter`.

### Verify

- From `apps/api`: `pytest -q`
- Search check: `rg "watsonx_client" apps/api/app/services.py` returns no matches.

### Out of Scope

- Deleting WatsonX support entirely.

## Ticket 6: Refactor Analysis Orchestration to Use Providers

### Goal

Update `analyze_project(...)` and retrieval flow to use selected providers while preserving the existing frontend contract.

### Context

The orchestration function owns intent extraction, retrieval, confidence scoring, fallback behavior, agent reports, checklist creation, and final `AnalyzeResult`.

### Relevant Files or References

- `apps/api/app/services.py`
- `apps/api/app/models.py`
- `apps/api/app/routers/api.py`
- `apps/web/src/api.ts`
- `packages/shared-schema/src/index.ts`

### Proposed Approach

Change retrieval and model analysis calls to go through provider selection. Keep existing `AnalyzeResult` assembly and agent report structure. Ensure provider exceptions become warnings and deterministic fallback behavior remains intact.

### Acceptance Criteria

- Existing API response shape remains compatible with `apps/web/src/api.ts`.
- Provider retrieval failures add warnings and produce no citations.
- Provider analysis failures add warnings and fall back safely.
- No citations cannot produce a high-confidence positive decision.
- Agent reports still include intent, research, and compliance stages.

### Source Reference

Spec sections: `Requirements`, `Invariants`, `Error Behavior`.

### Verify

- From `apps/api`: `pytest -q`
- Run targeted API tests for `/projects/{project_id}/analyze`.

### Out of Scope

- Changing frontend UI layout.
- Adding new API route versions.

## Ticket 7: Update Backend Tests for Offline Provider Behavior

### Goal

Ensure the backend test suite proves the app works without IBM or other external credentials.

### Context

The spec requires offline tests. Existing tests include WatsonX client tests and service/API tests.

### Relevant Files or References

- `apps/api/tests/test_api.py`
- `apps/api/tests/test_services.py`
- `apps/api/tests/test_watsonx_client.py`
- `apps/api/app/ai/`
- `apps/api/app/settings.py`

### Proposed Approach

Add tests for default provider settings, deterministic analysis, source registry retrieval, missing citation handling, unknown provider errors, and WatsonX credential isolation. Mock Google Maps and WatsonX calls where necessary.

### Acceptance Criteria

- `pytest -q` passes with no `.env` file.
- Tests prove WatsonX credentials are not required by default.
- Tests prove missing citations produce low-confidence or unknown behavior.
- Tests prove unknown providers fail with clear errors.

### Source Reference

Spec sections: `Requirements`, `Testing Strategy`.

### Verify

- From `apps/api`: `pytest -q`

### Out of Scope

- Browser or frontend testing.

## Ticket 8: Update Documentation for Phase 1 Operation

### Goal

Make the README and environment examples match the new provider-agnostic behavior.

### Context

The README currently documents WatsonX environment variables as part of the main setup and still contains IBM-specific references.

### Relevant Files or References

- `README.md`
- `.env.example`
- `services/ingestion/README.md`
- `docs/agent-agnostic-zoning-platform/spec.md`
- `docs/agent-agnostic-zoning-platform/plan.md`

### Proposed Approach

Document the new app name, provider settings, no-IBM default mode, optional WatsonX legacy mode, and testing commands. Keep the roadmap but align it with the implemented Phase 1 changes.

### Acceptance Criteria

- A new developer can run the default app without WatsonX credentials.
- Optional WatsonX setup is clearly labeled legacy/optional.
- Environment variable names match code.
- README points to the spec and plan.

### Source Reference

Spec sections: `Design / Phase 1`, `Testing Strategy`.

### Verify

- Follow the README quick start from a clean shell as far as dependency availability allows.
- Confirm no required setup step mentions WatsonX for the default path.

### Out of Scope

- Deployment documentation overhaul.

## Ticket 9: Add Local Retrieval Indexing Foundation

### Goal

Make `/api/v1/ingestion/reindex` perform useful deterministic indexing work over local sources.

### Context

Currently `/ingestion/reindex` only returns `queued` and the source count. Local source import exists, but retrieval is over whole source excerpts rather than chunks.

### Relevant Files or References

- `apps/api/app/ingestion.py`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`
- `apps/api/app/routers/api.py`
- `services/ingestion/documents/*`

### Proposed Approach

Introduce document/chunk models and storage for chunks. Reindex source entries into stable chunks with metadata. Keep retrieval deterministic and local; do not add vector dependencies yet.

### Acceptance Criteria

- Reindex creates stable chunk records from imported sources.
- Chunk IDs are deterministic across repeated reindex runs.
- Chunk metadata includes source ID, section reference, district/use tags, URL, and effective date where available.
- Retrieval can be adapted to use chunks in a later ticket.

### Source Reference

Spec sections: `Design / Phase 2`, `Testing Strategy / Phase 2`.

### Verify

- From `apps/api`: `pytest -q`
- API test imports sample docs, calls reindex, and verifies chunk count/IDs.

### Out of Scope

- Embeddings or vector search.

## Ticket 10: Add Jurisdiction Metadata Foundation

### Goal

Introduce data-driven jurisdiction support while preserving Blacksburg as the first supported jurisdiction.

### Context

Address normalization currently rejects non-Blacksburg addresses with a generic invalid-address state.

### Relevant Files or References

- `apps/api/app/services.py`
- `apps/api/app/district_mapping.py`
- `apps/api/app/models.py`
- `apps/api/app/data/district_rules.json`
- new `apps/api/app/data/jurisdictions.json`

### Proposed Approach

Add jurisdiction config with Blacksburg metadata. Extend internal address normalization result with jurisdiction support state. Keep public API changes minimal until the frontend can consume unsupported-jurisdiction states.

### Acceptance Criteria

- Blacksburg remains supported.
- Jurisdiction metadata is loaded from data, not hard-coded only in `normalize_address(...)`.
- Internal logic can distinguish invalid address from unsupported jurisdiction.
- Tests cover supported, unsupported, and invalid address cases through mocked Google responses.

### Source Reference

Spec sections: `Design / Phase 3`, `Decisions / Introduce Jurisdiction Models Before Broad Expansion`.

### Verify

- From `apps/api`: `pytest -q`

### Out of Scope

- Adding Christiansburg, Montgomery County, or Roanoke source coverage.
- Full frontend unsupported-jurisdiction UI.

## Ticket 11: Improve Evidence and Confidence UI

### Goal

Make completed analysis results easier to trust by surfacing evidence coverage, confidence, and warnings more clearly.

### Context

The frontend already shows results, citations, warnings, trace, and feedback, but the layout still feels demo-like and the evidence relationship is not prominent enough.

### Relevant Files or References

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `packages/shared-schema/src/index.ts`
- `docs/agent-agnostic-zoning-platform/spec.md`

### Proposed Approach

Refine the completed review experience with clearer answer/evidence sections, source coverage indicators, and more visible warnings. Keep existing API data and avoid adding new backend fields in this ticket unless already available.

### Acceptance Criteria

- Users can see the decision, confidence, warnings, and citations without hunting through tabs.
- No-citation or low-confidence results are visually distinct.
- Existing checklist download and feedback still work.
- UI copy uses the new neutral app name.

### Source Reference

Spec sections: `Design / Phase 4`, `Design / Phase 5`.

### Verify

- `npm run typecheck:web`
- `npm run build:web`
- Manual browser verification after starting the dev server.

### Out of Scope

- New structured intake fields.
- New backend response fields.

## Ticket 12: Add Structured Intake Fields for Common Zoning Facts

### Goal

Improve project intake by collecting common zoning facts explicitly instead of relying only on free-text parsing.

### Context

The current UI uses project description and address, then asks follow-up questions when missing operating hours, employee count, or construction scope.

### Relevant Files or References

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `packages/shared-schema/src/index.ts`
- `apps/api/app/models.py`
- `apps/api/app/services.py`

### Proposed Approach

Add optional structured fields for use type, construction scope, operating hours, employee count, parking/loading, and food/fire/health triggers. Merge structured fields into the project context sent to the backend while preserving compatibility with the existing intake endpoint.

### Acceptance Criteria

- Users can provide common zoning facts through structured controls.
- Free-text project description still works.
- Existing clarification modal still works.
- Backend analysis receives the structured facts in a deterministic format.

### Source Reference

Spec sections: `Design / Phase 5`.

### Verify

- `npm run typecheck:web`
- `npm run build:web`
- From `apps/api`: `pytest -q` if backend contracts are touched.
- Manual browser verification of intake and analysis flow.

### Out of Scope

- Saved project profiles.
- User accounts.

## Ticket 13: Add Admin Source Health and Index Status

### Goal

Make the admin workspace more useful for managing source coverage and reindexing.

### Context

The frontend admin area can edit sources, import local documents, and request reindex, but it does not show meaningful index status or source health.

### Relevant Files or References

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/api/app/routers/api.py`
- `apps/api/app/storage.py`
- `apps/api/app/models.py`

### Proposed Approach

Expose source counts, index/chunk counts when available, last import/reindex timestamps if stored, and simple source completeness signals. Display these in the admin workspace.

### Acceptance Criteria

- Admin users can see how many sources are registered.
- Admin users can see whether an index exists after reindexing.
- Source cards indicate missing metadata such as URL, effective date, districts, or uses.
- Reindex/import feedback remains visible and actionable.

### Source Reference

Spec sections: `Design / Phase 5`.

### Verify

- From `apps/api`: `pytest -q`
- `npm run typecheck:web`
- `npm run build:web`
- Manual admin workspace verification.

### Out of Scope

- Full document version history.
- Remote source crawling.
