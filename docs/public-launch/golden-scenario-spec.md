# Golden Scenario Spec

Golden scenarios are the promotion gate between source indexing and public support. A jurisdiction can have official sources in the registry and still remain non-public until scenarios prove the product responds with the right confidence, warnings, and citations.

## File Location

Scenarios live in `apps/api/tests/golden/scenarios.json`.

## Required Fields

- `id`: Stable slug for the scenario.
- `project_description`: User-facing business or project description.
- `district`: Zoning district slug, or `unknown` when district mapping is not trusted.
- `jurisdiction_id`: Registry jurisdiction ID.
- `jurisdiction_name`: Display name for reports.
- `normalized_address`: Representative address string.
- `sources`: Test-local source registry entries used only for the scenario run.
- `expect`: Assertions for the scenario.

## Expected Result Fields

- `decisions`: Allowed feasibility decisions.
- `statuses`: Allowed analysis statuses.
- `min_citations`: Minimum accepted citation count.
- `max_citations`: Optional maximum citation count.
- `min_confidence`: Optional lower confidence bound.
- `max_confidence`: Optional upper confidence bound.
- `jurisdiction_supported`: Whether the jurisdiction should be treated as public-supported.
- `required_warning_substrings`: Warning text fragments that must appear.
- `forbidden_citation_jurisdiction_ids`: Jurisdictions that must never appear in citations.

## Coverage Rules

- Every candidate expansion jurisdiction must have at least one scenario.
- `source_indexed` jurisdictions should assert `unknown` or `low_confidence` until source completeness, district mapping, and citation QA are strong enough.
- `qa_ready` jurisdictions should add at least one happy-path scenario with a real local citation.
- `public_supported` jurisdictions must keep at least one happy-path scenario passing.
- No scenario may pass by citing another municipality's zoning ordinance unless the cited source is an explicit parent or statewide/global source with state applicability metadata.

## Example

```json
{
  "id": "sample-source-indexed-jurisdiction",
  "project_description": "Open a small cafe with two employees, posted operating hours, and interior renovations.",
  "district": "unknown",
  "jurisdiction_id": "sample-va",
  "jurisdiction_name": "Sample, VA",
  "normalized_address": "1 Main St, Sample, VA",
  "sources": [],
  "expect": {
    "decisions": ["unknown"],
    "statuses": ["low_confidence"],
    "min_citations": 0,
    "max_citations": 0,
    "jurisdiction_supported": false,
    "required_warning_substrings": ["not currently supported"]
  }
}
```
