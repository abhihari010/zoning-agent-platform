# Ingestion Helpers

This folder holds seeding helpers and local documents for the zoning ingestion pipeline.
It is not a standalone deployable service; the API owns parsing, chunking, and indexing.

Pipeline stages:

1. Source registration
2. Document fetch and versioning
3. Parsing and OCR fallback
4. Chunking and metadata tagging
5. Optional embedding and vector indexing after deterministic chunks exist

Current helpers:

- `python services/ingestion/seed_sources.py`
  Seeds the API's persistent source catalog from `apps/api/app/data/source_registry.json`
  or from a custom JSON file path you pass in.
- `services/ingestion/documents/`
  Local document folder for automatic ingestion. The API can now parse `.md`,
  `.txt`, and `.json` source files from this directory or from another directory
  you provide.

The bundled `source_registry.json` holds the original Blacksburg coverage, which uses
official Town/Municode/State source URLs for home occupation standards, business zoning
guidance, off-street parking, building safety review, and food-establishment permitting.
Keep `jurisdiction_id` set to `blacksburg-va` and preserve district/use tags when
refreshing these curated excerpts.

Every other supported jurisdiction ships as its own pack under
`apps/api/app/data/source_packs/<state>/<jurisdiction-id>/`. See
`docs/public-launch/source-pack-spec.md` for the pack format and
`docs/public-launch/document-acquisition-workflow.md` for how packs are built.

Document parsing format:

- `title: ...`
- `section_ref: ...`
- `url: ...`
- `effective_date: ...`
- `districts: district-a, district-b`
- `uses: use-a, use-b`

After the metadata header, the remaining body text is condensed into the source excerpt.

Provider notes:

- The API default retrieval provider is `source_registry`, which is local and deterministic.
- Embeddings and vector databases are not required for the default path.
- Production uses `RAG_PROVIDER=hybrid_local` with Gemini embeddings and a Qdrant index, which
  combines vector search with keyword scoring and metadata filters.
