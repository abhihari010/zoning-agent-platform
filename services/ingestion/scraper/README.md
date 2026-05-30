# WS1 — Real Document Ingestion Scraper

Fetches **real municipal zoning ordinance text** and writes it into the existing
`source-pack/v1` manifest format so Stage 2 analysis is grounded in actual,
citable ordinance text instead of hand-written summary paragraphs.

This is the only missing link in the ingestion rail:

```
discover_jurisdiction_sources.py  → draft manifest skeleton
   [THIS PACKAGE: fills full_text + real url/section_ref/effective_date]
scripts/validate_source_packs.py  → validates source-pack/v1 schema
apps/api/app/ingestion.py         → manifest → SourceRegistryEntry → ≤900-char chunks → DB
POST /api/v1/ingestion/reindex    → chunks → vector store (out of WS1 scope)
```

## Quick start

From the repo root:

```bash
# Scrape Blacksburg, VA via Municode into the default draft root (.tmp/source_pack_drafts)
python services/ingestion/scraper/run_scrape.py --city "Blacksburg" --state VA --county "Montgomery"

# Validate the output against the authoritative schema
python scripts/validate_source_packs.py --source-packs-dir .tmp/source_pack_drafts

# Run the fixture-based unit tests (no network)
python -m pytest services/ingestion/scraper/tests -q
```

The default output root is `.tmp/source_pack_drafts`, so a scrape **never**
overwrites the curated packs in `apps/api/app/data/source_packs/`. Promotion of
a draft into the curated tree happens later, after district mapping + golden QA.

### CLI options

| Flag | Default | Purpose |
| --- | --- | --- |
| `--city` / `--state` | required | Jurisdiction name + 2-letter state code |
| `--fetcher` | `municode` | `municode` or `generic_html` |
| `--url` | – | Official URL(s); required for `generic_html`, optional override otherwise |
| `--county` | – | Parent county (sets `parent_jurisdiction_id`) |
| `--jurisdiction-id` | derived | Override the derived id (`{slug}-{state}`) |
| `--coverage-status` | `source_indexed` | Pack coverage status |
| `--delay` | `1.0` | Minimum seconds between HTTP requests |
| `--max-sections` | – | Cap section count (handy for smoke tests) |
| `--output-root` | `.tmp/source_pack_drafts` | Where to write the pack |

## Package layout

```
services/ingestion/scraper/
  http_client.py        # polite, cached httpx wrapper (rate-limit, retry/backoff, disk cache)
  html_cleaner.py       # HTML → clean plain text (stdlib html.parser; strips nav/script/style)
  manifest_builder.py   # SectionRecords + jurisdiction info → schema-valid manifest.json
  run_scrape.py         # CLI
  fetchers/
    base.py             # SectionRecord + Fetcher protocol + FetchResult
    municode.py         # PRIMARY: Municode JSON API (TOC walk + content chunk groups)
    generic_html.py     # FALLBACK: fetch an official page, clean HTML → coarse sections
  tests/
    fixtures/           # saved real Municode JSON + a generic HTML page (NO live network in tests)
    test_html_cleaner.py
    test_manifest_builder.py   # also runs the REAL validate_source_packs validator
    test_municode_parser.py    # parses saved fixtures → SectionRecords
    test_generic_html.py
```

## Municode API investigation (findings)

Municode (`library.municode.com`) is a single-page app backed by a **public,
unauthenticated JSON API** at `api.municode.com`. No API key, no anti-bot block
was encountered during development (a descriptive `User-Agent` and a polite
request delay were used). The endpoints used (discovered by inspecting the SPA's
network traffic — they evolve, so the parser is defensive):

1. **Resolve client id**
   `GET /Clients/name?clientName={city}&stateAbbr={ST}` → `{"ClientID": 8130, ...}`
2. **List code products**
   `GET /ClientContent/{clientId}` → `codes[]`; we pick the product whose
   `contentTypeId == "CODES"` (e.g. `productId` 10159, "Code of Ordinances").
3. **Latest published job + effective date**
   `GET /Jobs/latest/{productId}` → `{"Id": 485152, "BannerText": "...enacted December 9, 2025...", ...}`.
   The `BannerText` carries the codification/effective date, which we parse;
   we fall back to `PublishDate` if the banner has no "enacted" date.
4. **Table of contents (root)**
   `GET /CodesToc?jobId={jobId}&productId={productId}` → root node with
   `Children[]` (chapters/appendices). Each node has `Id`, `Heading`,
   `HasChildren`.
5. **TOC children**
   `GET /CodesToc/Children?jobId=&productId=&nodeId={id}` → child nodes, walked
   recursively (Article → Division → Section).
6. **Section content (chunk group)**
   `GET /CodesContent?jobId=&nodeId={id}&productId=` → a `Docs[]` *chunk group*.
   Each doc has `Id`, `Title` (e.g. `"Sec. 4211 - Home occupations."`) and
   `Content` (HTML). **One `CodesContent` call returns every section in the
   node's chunk group**, so we fetch once per division rather than once per
   section — far fewer requests.

**Deep-link URL** for a section on the public site:

```
https://library.municode.com/{state}/{city}/codes/code_of_ordinances?nodeId={nodeId}
```

The zoning ordinance node is found **data-drivenly** by matching the TOC heading
against `"zoning ordinance"` / `"zoning"` (excluding `"subdivision"`, comparative
tables, etc.). There is **no hard-coded per-city node id** — Blacksburg's zoning
lives under `APPENDIX A`, another city's may be a numbered chapter; the heading
match handles both.

### Live scrape results (validation target)

Both ran live against `api.municode.com` and produced schema-valid manifests
(0 errors; the per-source `districts: ["unknown"]` *warnings* are expected — see
below):

- **Blacksburg, VA** → 408 ordinance section sources.
- **Christiansburg, VA** → 211 ordinance section sources.

Feeding the Blacksburg manifest through the real
`apps/api/app/ingestion.build_source_chunks` produced 1,100 coherent chunks,
each carrying the correct deep-link `url` and `section_ref` (e.g. `Sec. 4211`).

## Design decisions

### One source per ordinance section

`apps/api/app/ingestion.build_source_chunks()` only does section-aware markdown
splitting when `metadata.imported_from` ends in `.md`; for source-pack sources it
runs plain `_chunk_text()` over the whole `full_text`, **losing internal section
structure**. So this scraper emits **one manifest source per ordinance section**,
each with:

- its own accurate `section_ref` (e.g. `Sec. 4211`),
- its own deep-link `url` (`?nodeId=...`),
- `full_text` = just that section's cleaned text.

This gives real, citable granularity (what legal citations require) and keeps the
downstream chunks coherent.

### Coverage status `source_indexed`, districts `unknown`

Scraped packs are written with `coverage_status: source_indexed` (not
`public_supported`) — promotion happens later after QA. District/use mapping is a
downstream QA step, so every source ships with `districts: ["unknown"]` and
`uses: ["general"]`. The validator emits a *warning* (not an error) for
`["unknown"]` districts; this is intentional and matches the existing curated
Christiansburg pack.

### Effective date

Captured from the Municode job banner (`...enacted <date>`) when available;
otherwise falls back to the retrieval date with
`metadata.effective_date_source = "retrieval_date"` so the provenance is explicit.

### Politeness & robustness (`http_client.py`)

- Descriptive `User-Agent` identifying the project.
- Configurable minimum delay between requests (`--delay`, default 1s).
- Retry of transient failures (timeouts, connection errors, `429`, `5xx`) with
  exponential backoff (capped).
- **On-disk cache** of every raw response under the pack's `raw/` dir, keyed by a
  hash of the URL — re-runs do not re-hit the network.
- On `401`/`403` the client raises `FetchBlockedError` and the CLI **fails
  gracefully** (exit code 2) rather than hammering the host.

## Known limitations / TODO

- **District & use mapping** is not inferred; all sources ship `districts:
  ["unknown"]`, `uses: ["general"]`. A follow-up (WS2 / QA) should map sections to
  the project's normalized district vocabulary before promotion to
  `public_supported`.
- **Municode-only primary path.** Cities not on Municode need the
  `generic_html` fallback (low fidelity: coarse heading splitting) or a new
  fetcher (e.g. American Legal Publishing, eCode360). The `Fetcher` protocol
  makes adding one straightforward.
- **No `robots.txt` parser yet.** We rely on a polite delay + descriptive UA and
  fail closed on `401`/`403`. A `robots.txt` check is a reasonable hardening
  follow-up if scraping is broadened.
- **Section ordering** in the manifest is by TOC walk; it is not re-sorted into
  strict numeric order. Downstream chunking keys on `source_id`, so order does
  not affect retrieval, but a human reviewer may prefer numeric sorting.
- **Tables/footnotes** in ordinance HTML are flattened to text lines; complex
  dimensional tables lose their grid layout (the text values survive).
```
