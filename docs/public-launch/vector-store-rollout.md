# Production Vector Store Rollout

## Current Choice

The public-beta production vector provider is `none`. SQL source chunks are the retrieval baseline while the app runs on free/low-cost infrastructure. Chroma remains available for local and staging experiments, using jurisdiction-scoped metadata, but should not be required for production readiness until persistence and rebuild operations are explicit.

## Persistence

- `VECTOR_PROVIDER=none` disables Chroma and uses SQL-backed retrieval. This is the public-beta default.
- `VECTOR_PROVIDER=chroma` enables Chroma for local or staging use.
- `CHROMA_PATH` controls local persistence.
- `CHROMA_COLLECTION` should use an environment-specific name, for example `zoning_sources_prod_v1`.
- If the host filesystem is ephemeral, vectors must be rebuilt after deploy or restart from source registry rows.

## Required Metadata

Every chunk must carry:

- `source_id`
- `chunk_id`
- `jurisdiction_id`
- `jurisdiction_scope`
- `state`
- `county`
- `municipality`
- `source_type`
- `source_version`
- `content_hash`
- `effective_date`
- `retrieved_at`
- `url`
- `districts`
- `uses`
- `coverage_status`

## Filtering Contract

Retrieval first filters by exact `jurisdiction_id`. It may also include:

- the approved parent jurisdiction when configured in `jurisdictions.json`
- `jurisdiction_id="*"` only when the source metadata declares the target state in `applies_to_states` or `state`

Municipal zoning ordinances must never use `jurisdiction_id="*"`.

## Rebuild Checklist

1. Validate source packs.
2. Import source packs or seed sources.
3. Reindex source chunks.
4. Sync Chroma.
5. Confirm `/api/v1/ingestion/status` reports a ready source index and vector index.
6. Run golden scenarios before promoting coverage.

## Commands

```powershell
python scripts/validate_source_packs.py
cd apps/api
pytest tests/test_rag_phase2.py -q
cd ../..
```
