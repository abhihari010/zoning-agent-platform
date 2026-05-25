# Source Pack Specification

Last updated: May 25, 2026

Source packs are the contract for adding jurisdiction-scoped official sources to the zoning RAG pipeline. A pack is not a dump of documents. It is a reviewed manifest that identifies the jurisdiction, the official source records, and the metadata needed to retrieve answers only from the correct legal authority.

The v1 manifest lives at:

```text
services/ingestion/source_packs/<state>/<jurisdiction_id>/manifest.json
```

## Contract Version

Every v1 manifest must include:

```json
{
  "schema_version": "source-pack/v1"
}
```

Agents must not silently upgrade older manifests. If `schema_version` is missing or different, update the pack deliberately and run `python scripts/validate_source_packs.py`.

## Manifest Shape

Required top-level fields:

- `schema_version`: must be `source-pack/v1`.
- `jurisdiction`: object describing the legal authority that owns the pack.
- `verification_notes`: plain-language notes describing what was verified and what remains uncertain.
- `sources`: non-empty array of official source records.

Required `jurisdiction` fields:

- `jurisdiction_id`: stable slug, for example `blacksburg-va`.
- `name`: display name, for example `Blacksburg, VA`.
- `coverage_status`: one of `source_discovery`, `source_indexed`, `qa_ready`, or `public_supported`.
- `state`: two-letter USPS abbreviation.
- `state_fips`: two-digit state FIPS code.
- `county_fips`: three-digit county FIPS code when applicable, otherwise `null`.
- `place_fips`: five-digit place FIPS code when applicable, otherwise `null`.
- `jurisdiction_type`: one of `municipality`, `county`, `independent_city`, `state`, `regional_authority`, or `special_district`.
- `parent_jurisdiction_id`: parent county/state jurisdiction ID when a parent source can legally apply, otherwise `null`.
- `official_source_urls`: non-empty array of official planning, code, GIS, or department URLs.
- `zoning_map_url`: official zoning map or GIS URL when available, otherwise `null` with a blocker in `verification_notes`.
- `planning_contact`: object with at least one of `url`, `email`, or `phone`.

Recommended `jurisdiction` fields:

- `county_name`
- `municipality_name`
- `homepage_url`
- `retrieved_at`

## Source Records

Required source fields:

- `source_id`: globally unique stable ID.
- `title`: human-readable official source title.
- `excerpt` or `full_text`: enough text to support chunking and citation review.
- `section_ref`: section, page, heading, or form label used for citations.
- `jurisdiction_id`: the owning jurisdiction ID, an approved parent jurisdiction ID, or `*` for explicit global/statewide scope.
- `url`: official source URL.
- `effective_date`: effective or last-updated date of the source content, not the retrieval date.
- `source_type`: one of the allowed source types below.
- `districts`: non-empty array. Use `["unknown"]` only when district mapping is not reviewed yet.
- `uses`: non-empty array. Use `["general"]` for broadly applicable sources.

Recommended source fields:

- `retrieved_at`: date the source URL or local fallback was reviewed.
- `source_version`: official amendment/version label or content hash.
- `metadata.verification_status`: `verified`, `candidate`, `stale`, or `blocked`.
- `metadata.reviewed_by`: agent or person that reviewed the source.
- `metadata.notes`: short source-specific caveat.

Allowed `source_type` values:

- `zoning_ordinance`
- `zoning_map`
- `planning_page`
- `permit_page`
- `building_code`
- `health_code`
- `fire_code`
- `gis_layer`
- `fee_schedule`
- `application_form`
- `state_law`

## URLs and Local Fallbacks

Source URLs must be `http` or `https` official-source URLs. Placeholder hosts such as `example.gov` are invalid.

A curated local fallback is allowed only when an official document is intentionally stored locally because a stable public URL is unavailable or unsuitable for repository-size/licensing reasons. In that case:

- `metadata.curated_local_fallback` must be `true`.
- `url` may use `local://...` or `file://...`.
- `metadata.original_official_url` should be provided when one existed.
- `metadata.fallback_reason` must explain why the local copy is used.
- The source still needs `effective_date`, `retrieved_at`, and verification notes.

The validator never downloads external pages. URL freshness is a separate manual or smoke-test concern.

## Parent and Global Scope

The default rule is strict: a source in a jurisdiction pack must have `source.jurisdiction_id` equal to `jurisdiction.jurisdiction_id`.

Parent scope is allowed when:

- `jurisdiction.parent_jurisdiction_id` is set.
- `source.jurisdiction_id` equals that parent ID.
- The source is legally administered by the parent authority, such as county permits for unincorporated areas.
- The source metadata explains the relationship.

Global scope is allowed only when:

- `source.jurisdiction_id` is `*`.
- `source.source_type` is `building_code`, `health_code`, `fire_code`, or `state_law`.
- `metadata.applies_to_states` includes the pack state.
- The source is not a municipal zoning ordinance, zoning map, local planning page, local permit page, local fee schedule, or local application form.

Global scope exists for statewide or cross-jurisdiction rules such as state building code, health department requirements, fire code, or state business licensing law. It must not be used to make a local zoning rule look broadly applicable.

## Coverage Promotion

Coverage is a QA status, not a promise implied by having documents.

- `source_discovery`: official links are identified, but the pack is not imported or indexed.
- `source_indexed`: the pack validates, imports, chunks, and can be reindexed locally.
- `qa_ready`: source metadata is complete and golden scenarios pass.
- `public_supported`: the jurisdiction is visible to users as answerable for defined common use cases after human review.

Promotion blockers:

- Missing or placeholder official URLs.
- Missing `effective_date`.
- Missing planning contact.
- Missing zoning ordinance or code source.
- Missing zoning map/GIS source when the jurisdiction uses map-based districts.
- `districts` only `unknown` for all zoning-critical sources.
- No golden scenario for the jurisdiction.
- Golden scenario citations from the wrong jurisdiction.
- Candidate, stale, or blocked verification notes on core sources.
- No indexed chunks for the jurisdiction.

Demotion triggers:

- Official links break or move.
- The jurisdiction publishes a code/map update that changes a cited rule.
- District mapping becomes unreliable.
- Golden scenarios fail or produce wrong-jurisdiction citations.

## Minimal Example

```json
{
  "schema_version": "source-pack/v1",
  "jurisdiction": {
    "jurisdiction_id": "sample-va",
    "name": "Sample, VA",
    "coverage_status": "source_indexed",
    "state": "VA",
    "state_fips": "51",
    "county_fips": "001",
    "place_fips": "12345",
    "jurisdiction_type": "municipality",
    "parent_jurisdiction_id": "sample-county-va",
    "official_source_urls": ["https://sampleva.gov/planning"],
    "zoning_map_url": "https://sampleva.gov/gis/zoning",
    "planning_contact": {
      "url": "https://sampleva.gov/planning/contact",
      "email": "planning@sampleva.gov"
    }
  },
  "verification_notes": "Official planning, code, and zoning map URLs reviewed on 2026-05-25.",
  "sources": [
    {
      "source_id": "sample-va-zoning-ordinance",
      "title": "Sample Zoning Ordinance",
      "excerpt": "The zoning ordinance establishes districts, permitted uses, and review procedures.",
      "section_ref": "Chapter 18, Zoning",
      "jurisdiction_id": "sample-va",
      "url": "https://sampleva.gov/code/chapter-18",
      "effective_date": "2026-05-01",
      "source_type": "zoning_ordinance",
      "districts": ["unknown"],
      "uses": ["general"],
      "retrieved_at": "2026-05-25",
      "metadata": {
        "verification_status": "verified"
      }
    }
  ]
}
```
