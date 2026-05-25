# Document Acquisition Workflow

Last updated: May 25, 2026

Use this workflow whenever adding or updating jurisdiction source packs. The goal is to capture official, reviewable sources without turning the repository into an unbounded national document dump.

## Folder Shape

Use one folder per jurisdiction:

```text
services/ingestion/source_packs/<state>/<jurisdiction_id>/
  manifest.json
  notes.md
  raw/
  extracted/
```

Folder rules:

- `manifest.json` is the source-pack contract and must follow `docs/public-launch/source-pack-spec.md`.
- `notes.md` captures research decisions, blockers, and source URLs that were considered but rejected.
- `raw/` is optional and should contain PDFs/HTML only when licensing and repository-size concerns are acceptable.
- `extracted/` is optional and should contain reviewed text extracts from official documents.
- Prefer official URLs plus concise reviewed excerpts in `manifest.json` over committing large raw files.

Drafts from `scripts/discover_jurisdiction_sources.py` are written to `.tmp/source_pack_drafts/` by default so they do not change production pack data. Move a draft into `services/ingestion/source_packs/` only after a reviewer is ready to own the pack.

## Source Quality Rules

Allowed sources:

- Official city, town, county, state, or regional authority domains.
- Official municipal code hosts such as Municode, CivicPlus, American Legal Publishing, or the jurisdiction's chosen code publisher.
- Official GIS/map portals linked from the jurisdiction.
- Official health, fire, building, permit, business license, or fee pages from the administering authority.

Do not use:

- SEO pages, scraped code mirrors, law-firm summaries, real-estate blogs, forums, or AI-generated summaries.
- News articles as zoning authority.
- Search-result snippets as source text.
- Unofficial PDF mirrors unless they are only a discovery lead and the official source is later verified.

## Required Review Steps

For each jurisdiction:

1. Identify the official planning/zoning department page.
2. Identify the zoning ordinance or code source.
3. Identify the official zoning map/GIS lookup.
4. Identify permit/building review pages.
5. Identify state, health, or fire sources only when they matter to expected use cases.
6. Capture planning contact information.
7. Record retrieval date separately from effective date.
8. Add blockers for missing, stale, or uncertain sources.
9. Run `python scripts/validate_source_packs.py` before import or reindex.

For each source record:

- `url` is the official source location or a documented curated local fallback.
- `retrieved_at` is when the URL or local source was reviewed.
- `effective_date` is the ordinance/form/page effective or last-updated date.
- `verification_status` starts as `candidate` and becomes `verified` only after manual review.
- `districts` should be precise when possible; `["unknown"]` is acceptable only as a temporary QA blocker.
- `uses` should reflect the source's scope, such as `home-based-food-business`, `food-service`, `retail`, or `general`.

## Raw and Extracted Documents

Before committing raw files:

- Confirm the document is public and appropriate to store in the repository.
- Avoid large PDFs when an official stable URL is sufficient.
- Prefer text extracts for the specific sections used by citations.
- Keep filenames stable and source-specific, for example `zoning-ordinance-2026-05-01.pdf`.
- Record the raw file's origin in `notes.md` and source `metadata`.

When extracting text:

- Preserve section headings and page/section references.
- Do not paraphrase legal text as if it were quoted.
- Keep excerpts short enough for review and citation.
- Add `metadata.original_official_url` when the extracted source came from a larger official document.

## Blockers

Record blockers in `verification_notes`, `notes.md`, or source `metadata.notes`. Common blockers:

- Official zoning map not found.
- Effective date unclear.
- Planning contact missing.
- Code host has multiple versions and the current version is uncertain.
- Ordinance references a map or table not yet extracted.
- District mapping unavailable for parcel-level analysis.
- Source is candidate-only and should not support public answers.

Blockers do not prevent draft creation, but they prevent promotion to `public_supported`.

## Promotion Checklist

Before moving beyond `source_discovery`:

- Manifest validates.
- Core sources are official and non-placeholder.
- Effective dates are present.
- Planning contact is present.
- Zoning ordinance/code and zoning map/GIS are identified or explicitly blocked.

Before `public_supported`:

- Source pack imports and chunks.
- Golden scenarios pass.
- Citations stay within the jurisdiction, approved parent, or explicit global scope.
- No core source remains `candidate`, `stale`, or `blocked`.
- A human reviewer accepts the jurisdiction scope and limitations.
