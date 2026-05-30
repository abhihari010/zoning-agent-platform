"""WS2: merge real scraped ordinance text into the Blacksburg + Christiansburg packs.

Two effects (see docs/handoff-nationwide-expansion.md, WS2):

1. ENRICH — inject the matching real ordinance section's ``full_text`` into the
   existing, precisely-tagged curated entries in
   ``apps/api/app/data/source_registry.json``.  Tags / section_ref / url / uses
   are preserved; only ``full_text`` is added, so ``build_source_chunks`` now
   grounds those entries in real text instead of a hand-written excerpt while the
   demo's district/use precision is kept.

2. BREADTH — write the full scraped corpus to
   ``apps/api/app/data/source_packs/va/{city}/manifest.json`` (coverage
   ``source_indexed``, ``districts: ["unknown"]``).  The curated jurisdiction
   block (real FIPS + planning contact) is kept; only the ``sources`` array is
   replaced with the scraped sections.  Sections already used for enrichment are
   excluded so the index does not carry duplicate chunks.

Inputs are the non-destructive scraper drafts under
``.tmp/source_pack_drafts/va/{city}/manifest.json`` (produced by
``services/ingestion/scraper/run_scrape.py``).  Re-runnable / idempotent.

Run from the repo root::

    python scripts/ws2_merge_scraped_sources.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DRAFT_ROOT = REPO_ROOT / ".tmp" / "source_pack_drafts" / "va"
SOURCE_PACKS = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_packs" / "va"
REGISTRY_PATH = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_registry.json"

# curated registry source_id -> scraped section_ref whose real text grounds it.
ENRICHMENT: dict[str, str] = {
    "blacksburg-home-occupation-standards": "Sec. 4211",
    "blacksburg-off-street-parking-home-occupation": "Sec. 5210",
}


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _scraped_sections(city_slug: str) -> list[dict]:
    manifest = _load(DRAFT_ROOT / city_slug / "manifest.json")
    return list(manifest["sources"])  # type: ignore[index]


def _by_section_ref(sections: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for src in sections:
        out.setdefault(src["section_ref"], src)
    return out


def enrich_registry() -> tuple[int, set[str]]:
    """Inject real full_text into curated entries. Returns (count, used_refs)."""
    registry = _load(REGISTRY_PATH)
    blacksburg = _by_section_ref(_scraped_sections("blacksburg-va"))
    used_refs: set[str] = set()
    enriched = 0
    for entry in registry:  # type: ignore[union-attr]
        ref = ENRICHMENT.get(entry["source_id"])
        if not ref:
            continue
        section = blacksburg.get(ref)
        if not section:
            raise SystemExit(f"Scraped section {ref!r} not found for {entry['source_id']}.")
        entry["full_text"] = section["full_text"]
        entry.setdefault("metadata", {})
        entry["metadata"]["full_text_source"] = section["url"]
        entry["metadata"]["full_text_section_ref"] = section["section_ref"]
        entry["metadata"]["verification_status"] = "scraped_full_text"
        used_refs.add(ref)
        enriched += 1
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return enriched, used_refs


def write_breadth_pack(city_slug: str, *, exclude_refs: set[str]) -> int:
    """Replace a curated pack's sources with the scraped corpus (minus excludes)."""
    curated = _load(SOURCE_PACKS / city_slug / "manifest.json")
    draft = _load(DRAFT_ROOT / city_slug / "manifest.json")

    jurisdiction = dict(curated["jurisdiction"])  # type: ignore[index]
    jurisdiction["coverage_status"] = "source_indexed"

    sources = [s for s in draft["sources"] if s["section_ref"] not in exclude_refs]  # type: ignore[index]

    merged = {
        "schema_version": "source-pack/v1",
        "jurisdiction": jurisdiction,
        "verification_notes": draft.get("verification_notes", ""),  # type: ignore[union-attr]
        "sources": sources,
        "scrape_provenance": draft.get("scrape_provenance", {}),  # type: ignore[union-attr]
    }
    out_path = SOURCE_PACKS / city_slug / "manifest.json"
    out_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return len(sources)


def main() -> int:
    enriched, used_refs = enrich_registry()
    print(f"[ws2] enriched {enriched} curated registry entries with real full_text "
          f"({', '.join(sorted(used_refs))}).")

    # Blacksburg excludes the enriched sections; Christiansburg has none.
    bburg = write_breadth_pack("blacksburg-va", exclude_refs=used_refs)
    cburg = write_breadth_pack("christiansburg-va", exclude_refs=set())
    print(f"[ws2] breadth pack blacksburg-va:    {bburg} sources (excluded {len(used_refs)} enriched).")
    print(f"[ws2] breadth pack christiansburg-va: {cburg} sources.")
    print("[ws2] validate: python scripts/validate_source_packs.py "
          "--source-packs-dir apps/api/app/data/source_packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
