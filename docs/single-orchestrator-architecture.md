# Single Orchestrator Architecture

Last updated: May 23, 2026

## Current Decision

The zoning review backend uses one central `ZoningOrchestrator` instead of a chain of autonomous agents. The orchestrator runs deterministic or provider-backed tools in a staged workflow:

```text
User request
  -> ZoningOrchestrator
    -> IntakeTool
    -> location context from the current intake route
    -> retrieval provider
    -> ComplianceTool
    -> CitationTool
    -> ReportTool
```

The frontend presents these as pipeline stages:

1. Understand Project
2. Resolve Property
3. Retrieve Sources
4. Analyze Compliance
5. Generate Checklist

## Module Map

- `apps/api/app/orchestrator/zoning_orchestrator.py` coordinates the staged analysis flow.
- `apps/api/app/orchestrator/pipeline_context.py` carries state between stages.
- `apps/api/app/orchestrator/pipeline_events.py` records structured stage events into the existing audit-event store.
- `apps/api/app/tools/intake_tool.py` performs deterministic structured intake extraction.
- `apps/api/app/tools/compliance_tool.py` runs compliance synthesis and only invokes the selected model provider when source evidence exists.
- `apps/api/app/tools/citation_tool.py` validates citation IDs, effective dates, and source jurisdiction.
- `apps/api/app/tools/report_tool.py` builds pipeline stage reports and the user-facing checklist.
- `apps/api/app/ai/` remains the provider boundary for deterministic, OpenAI-compatible, local, and WatsonX-backed analysis/retrieval.

## Compatibility Contracts

The primary response field for stage progress is `pipeline_stages` in Python and `pipelineStages` in TypeScript.

The older `agents` field is still returned as a deprecated compatibility alias so existing clients do not break. New code should use `pipelineStages`.

`apps/api/app/services.py` remains as a compatibility facade. API routes and older tests can continue calling `analyze_project(...)`, but the implementation delegates immediately to `ZoningOrchestrator`.

## Location Boundary

For compatibility with the current frontend and tests, `/api/v1/projects/intake` still owns live address normalization, Google Maps validation, supported/unsupported jurisdiction detection, and project creation.

During analysis, the orchestrator records a `location` stage using the stored project location fields:

- `jurisdiction_id`
- `jurisdiction_name`
- `district`

Moving address normalization fully inside the orchestrator is intentionally deferred until the address/intake API can be redesigned without breaking unsupported-jurisdiction behavior.

## Free/Local Deployment Path

No ChromaDB, pgvector, or paid vector service is required for Phase 1.

The free/local path is:

- SQLite locally, or the configured Postgres database in staging.
- `AI_PROVIDER=deterministic` by default.
- `RAG_PROVIDER=source_registry` or `hybrid_local`.
- `EMBEDDING_PROVIDER=local` for deterministic local hash embeddings.

Dedicated vector storage should wait for Phase 2 RAG hardening, when the source corpus is large enough or retrieval quality requires persisted vector indexes.

## Phase Boundary

Phase 1 is complete when:

- one orchestrator owns analysis;
- progress is described as pipeline stages;
- `pipelineStages` is the primary frontend contract;
- trace events show each stage;
- docs explain the remaining location/intake compatibility boundary.

Phase 2 should focus on the real local RAG pipeline: source document records, full-document chunking, persisted chunk embeddings, stronger metadata filters, and citations returned from chunks rather than hand-written excerpts.
