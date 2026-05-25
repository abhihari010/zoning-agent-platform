# Nationwide Jurisdiction Expansion Strategy

Last updated: May 25, 2026

## Definition of Supported

`public_supported` means the app can answer common zoning review scenarios for a jurisdiction because official source links, indexed source records, district handling, and at least one golden QA scenario are in place.

Coverage tiers:

- Tier 0, recognized only: jurisdiction can be named from an address, but the app refuses to answer.
- Tier 1, source discovery: official planning/code/map/contact links are identified.
- Tier 2, source indexed: a source pack imports into the registry and chunks successfully.
- Tier 3, QA ready: golden scenarios pass, source metadata is complete, and failure modes are reviewed.
- Tier 4, public supported: visible to users as answerable for defined common use cases.

Promotion rule: no jurisdiction becomes `public_supported` while it has placeholder sources, missing effective dates, no official source URL, no planning contact, or no passing golden scenario.

Demotion rule: move a jurisdiction down to `qa_ready` or `source_indexed` if official links break, citations become stale, district mapping fails, or a planning/code update changes a core source.

## Demand-Led Backlog

Backlog fields:

- state
- jurisdiction ID and display name
- demand count from `jurisdiction_requests`
- population or strategic user relevance
- official sources found
- source pack status
- QA status
- public support status
- owner and next action

Priority score:

`demand_count * 3 + source_availability * 2 + population_relevance + strategic_fit`

Source availability is 0-3:

- 0: no official source found
- 1: planning/contact page only
- 2: code plus map found
- 3: code, map, permits, and department contacts found

## First Targets

Initial expansion stays regional and QA-able:

- Christiansburg, VA
- Roanoke, VA
- Roanoke County, VA
- Salem, VA
- Radford, VA
- Pulaski County, VA
- Botetourt County, VA
- Lynchburg, VA
- Charlottesville, VA
- Albemarle County, VA

After Virginia proves repeatable, expand by user request clusters rather than attempting a bulk national promise.

## Operating Cadence

Weekly:

- Review top jurisdiction requests.
- Choose one source pack to advance.
- Verify official source URLs and planning contact.
- Add or update golden scenario coverage.
- Reindex and run browser/API smoke tests.

Before promotion:

- Confirm source pack imports without validation errors.
- Confirm source readiness reports complete metadata.
- Confirm at least one supported happy path and one unsupported/low-confidence path.
- Confirm frontend coverage copy does not over-promise.

## Current Sprint 2 Status

The app now models national coverage as statuses instead of a boolean. Unknown US jurisdictions receive honest unsupported handling and can be requested by signed-in users. The first Virginia expansion batch is source-indexed for QA, while Blacksburg and Montgomery County remain the only public-supported jurisdictions.
