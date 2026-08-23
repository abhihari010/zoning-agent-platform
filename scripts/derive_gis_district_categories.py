"""Derive `district_categories` for `app/data/parcel_gis_sources.json`.

A jurisdiction's GIS layer answers with its own zoning code (`R-4`, `DC`, `CBD`).
Retrieval scores against the coarse vocabulary the source packs are tagged with, so
each code needs a category -- and per CLAUDE.md that category must come from the
city's own ordinance, never from a guess about what the letters mean.

Three sources of evidence are used, in order, and each mapping records the sentence
it came from:

1. the layer's own published district name (`ZONE_DESC`, `DistrictName`, ...),
2. an ordinance heading that *defines* the district ("ARTICLE 8 - HIGHWAY COMMERCIAL
   DISTRICT-B-2"), where "defines" means the code leads the heading or sits directly
   against the word DISTRICT/ZONE -- a cross-reference like "Commercial structures in
   R-1, R-2 and R-3 Districts" is not a definition and is rejected,
3. the ordinance naming the district inline ("R-1 Low density residential district").

Free prose is deliberately NOT read: a purpose statement that mentions "mixed-use
buildings" is not the district's name, and reading those was the only thing that
produced wrong categories.

A code whose evidence is missing or contradictory is left out. An absent code yields
no district at request time, which is exactly where we were before the lookup existed.

    python scripts/derive_gis_district_categories.py            # report only
    python scripts/derive_gis_district_categories.py --write    # update the data files
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "apps" / "api" / "app" / "data"
SOURCES_PATH = DATA / "parcel_gis_sources.json"
EVIDENCE_PATH = DATA / "parcel_gis_district_evidence.json"
PACKS = DATA / "source_packs"

# The vocabulary the source packs are tagged with, and the ordinance words that name
# each family. Order matters: "DOWNTOWN"/"CENTRAL BUSINESS" also contain "BUSINESS",
# so the mixed-use phrases are matched first and win outright.
FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("mixed-use-core", ("MIXED USE", "MIXED-USE", "DOWNTOWN", "CENTRAL BUSINESS", "TOWN CENTER",
                        "CITY CENTER", "URBAN CENTER", "VILLAGE CENTER", "TRADITIONAL NEIGHBORHOOD")),
    # "CONSERVATION" is deliberately absent: it names historic-and-cultural overlays as
    # often as farmland, so it is not evidence of the agricultural family.
    ("agricultural", ("AGRICULTUR", "RURAL", "FARM")),
    ("industrial-zone", ("INDUSTRIAL", "MANUFACTURING", "INDUSTRY")),
    ("commercial-employment", ("COMMERCIAL", "BUSINESS", "OFFICE", "SHOPPING", "RETAIL", "PROFESSIONAL")),
    ("residential-low-density", ("RESIDENTIAL", "RESIDENCE", "DWELLING", "HOUSING", "MOBILE HOME",
                                 "MANUFACTURED HOME", "TOWNHOUSE", "APARTMENT", "MULTIFAMILY",
                                 "MULTI-FAMILY", "SINGLE-FAMILY", "SINGLE FAMILY", "ONE FAMILY",
                                 "ONE-FAMILY", "TWO-FAMILY", "TWO FAMILY")),
]

# The layer column that publishes the district's NAME. Naming the zoning field itself means
# the layer stores full names in place of codes ("Highway Commercial"). Layers whose name
# column only repeats the code, or holds rezoning history, are simply absent here.
NAME_FIELDS = {
    "albemarle-county-va": "Zoning",
    "clarksville-tn": None,
    "danville-va": "ZONE_DESC",
    "loudoun-county-va": "ZD_ZONE_NAME",
    "norfolk-va": "TYPE",
    "salem-va": "DistrictName",
    "virginia-beach-va": "DESCRIPTION",
    "winchester-va": "Name",
}

LEAD = re.compile(
    r"^[^A-Za-z0-9]*(?:(?:ARTICLE|SEC|SECTION|DIVISION|CHAPTER|APPENDIX)\.?\s*)?[0-9IVX][0-9IVX.\-]*\s*[:.\-—]\s*",
    re.I,
)
SPLIT = re.compile(r"[\s,;:()�—–]+")


def normalize(code: str) -> str:
    """Fold separators so a layer's `R1` matches an ordinance's `R-1`, but not `RM1`."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def family(text: str) -> str | None:
    """The one land-use family this text names, or None if it names none or several."""
    upper = text.upper()
    hits = [name for name, words in FAMILIES if any(word in upper for word in words)]
    if not hits:
        return None
    if hits[0] == "mixed-use-core":
        return "mixed-use-core"
    return hits[0] if len(hits) == 1 else None


def _strip_numbering(heading: str) -> str:
    previous = None
    while previous != heading:
        previous = heading
        heading = LEAD.sub("", heading, count=1).lstrip(" -—:.")
    return heading.lstrip("�§ ")


def _leads_heading(heading: str, code: str) -> bool:
    tokens = [t for t in SPLIT.split(_strip_numbering(heading).strip()) if t]
    return bool(tokens) and normalize(tokens[0].strip(".-/")) == normalize(code)


def defines(heading: str, code: str) -> bool:
    if _leads_heading(heading, code):
        return True
    wanted = normalize(code)
    patterns = (
        r"(?:DISTRICT|ZONE)S?\W{0,3}([A-Za-z0-9][A-Za-z0-9\-\./]*)",
        r"[-—]\s*([A-Za-z0-9][A-Za-z0-9\-\./]*)\s*\((?:LEGACY\s+)?DISTRICT\)",
        r"\(([A-Za-z0-9][A-Za-z0-9\-\./]*)\)\s*$",
    )
    return any(
        normalize(match.group(1)) == wanted
        for pattern in patterns
        for match in re.finditer(pattern, heading, re.I)
    )


def inline_names(blob: str, code: str) -> dict[str, str]:
    """Families named by "<CODE> <name> District/Zone" in the ordinance body.

    The code is matched case-sensitively and must be a whole token, or prose words
    ("granted", "illuminate") and longer codes (`RMF` for `RM`) match it.
    """
    escaped = re.escape(code)
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])\s*[,:/–—-]{0,2}\s*"
        r"([A-Za-z][A-Za-z /&-]{2,55}?)\s+[Dd]istrict\b"
        r"|(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])\s*[,:/–—-]{0,2}\s*"
        r"([A-Za-z][A-Za-z /&-]{2,55}?)\s+[Zz]one\b"
    )
    found: dict[str, str] = {}
    for match in pattern.finditer(blob):
        hit = family(match.group(1) or match.group(2) or "")
        if hit:
            found.setdefault(hit, match.group(0)[:90])
    return found


def arcgis(url: str, params: dict[str, str], timeout: float = 90) -> dict:
    response = httpx.get(url.rstrip("/") + "/query", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(f"ArcGIS error: {payload['error']}")
    return payload


def distinct(url: str, *fields: str) -> list[dict]:
    """Distinct rows for `fields`. groupBy statistics works on layers too old for
    returnDistinctValues, and pulling the column outright covers the rest."""
    stats = json.dumps([{"statisticType": "count", "onStatisticField": fields[0],
                         "outStatisticFieldName": "n"}])
    attempts = (
        {"where": "1=1", "f": "json", "returnGeometry": "false",
         "groupByFieldsForStatistics": ",".join(fields), "outStatistics": stats},
        {"where": "1=1", "f": "json", "returnGeometry": "false", "outFields": ",".join(fields)},
    )
    for params in attempts:
        try:
            rows = [row["attributes"] for row in arcgis(url, params).get("features", [])]
        except Exception:  # noqa: BLE001 - try the next shape before giving up
            continue
        if rows:
            return rows
    return []


def pack_headings_and_body(jurisdiction_id: str) -> tuple[set[str], str]:
    manifest = next(PACKS.glob(f"*/{jurisdiction_id}/manifest.json"), None)
    if manifest is None:
        return set(), ""
    sources = json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    headings: set[str] = set()
    for source in sources:
        breadcrumb = (source.get("metadata") or {}).get("breadcrumb") or []
        headings.update(str(part) for part in breadcrumb[1:])
        headings.add(str(source.get("title") or ""))
    body = " ".join(source.get("full_text") or "" for source in sources)
    return {h for h in headings if h}, body


def derive(jurisdiction_id: str, config: dict) -> tuple[dict[str, str], dict[str, str], list[str]]:
    zoning_field = config["zoning_field"]
    name_field = NAME_FIELDS.get(jurisdiction_id, "")
    fields = [zoning_field] + ([name_field] if name_field and name_field != zoning_field else [])
    rows = distinct(config["url"], *fields)
    codes: dict[str, str] = {}
    for row in rows:
        code = str(row.get(zoning_field) or "").strip()
        if code:
            codes.setdefault(code, str(row.get(name_field) or "").strip() if name_field else "")

    headings, body = pack_headings_and_body(jurisdiction_id)
    categories: dict[str, str] = {}
    evidence: dict[str, str] = {}

    for code, published_name in codes.items():                        # 1. the layer's own name
        hit = family(published_name) if published_name else None
        if hit:
            categories[code] = hit
            evidence[code] = f"layer district name: {published_name}"

    for code in codes:                                                # 2. a defining heading
        if code in categories:
            continue
        matched = {(family(h), h) for h in headings if defines(h, code)}
        matched = {(f, h) for f, h in matched if f}
        if len({f for f, _ in matched}) == 1:
            categories[code] = next(iter(matched))[0]
            evidence[code] = "ordinance heading: " + sorted(h for _, h in matched)[0]

    for code in codes:                                                # 3. named inline
        if code in categories:
            continue
        found = inline_names(body, code)
        if len(found) == 1:
            categories[code], quote = next(iter(found.items()))
            evidence[code] = f"ordinance text: {quote}"

    by_normalized = {normalize(c): c for c in categories}             # 4. conditional variants
    for code in codes:
        # Virginia proffers conditions onto a base district and suffixes its code with C.
        # It is the same district, so it takes the same category.
        if code in categories:
            continue
        stem = normalize(code)[:-1]
        if normalize(code).endswith("C") and stem in by_normalized:
            base = by_normalized[stem]
            categories[code] = categories[base]
            evidence[code] = f"conditional variant of {base} ({evidence[base]})"

    unmapped = sorted(c for c in codes if c not in categories)
    return dict(sorted(categories.items())), dict(sorted(evidence.items())), unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="update the committed data files")
    parser.add_argument("--jurisdiction", action="append", help="limit to these jurisdiction ids")
    args = parser.parse_args()

    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    evidence_all = (json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
                    if EVIDENCE_PATH.exists() else {})
    wanted = set(args.jurisdiction or sources["jurisdictions"])

    changed = 0
    for jurisdiction_id, config in sources["jurisdictions"].items():
        if jurisdiction_id not in wanted:
            continue
        if config.get("curated"):
            # Hand-curated against a shared county parcel layer, which this script cannot
            # split by jurisdiction. Leave it alone.
            print(f"{jurisdiction_id:26} curated by hand, skipped")
            continue
        try:
            categories, evidence, unmapped = derive(jurisdiction_id, config)
        except Exception as error:  # noqa: BLE001 - one dead service must not stop the rest
            print(f"{jurisdiction_id:26} SKIPPED ({type(error).__name__}: {error})")
            continue
        if not categories:
            print(f"{jurisdiction_id:26} no derivable categories")
            continue
        was = config.get("district_categories") or {}
        delta = {c for c in set(was) | set(categories) if was.get(c) != categories.get(c)}
        counts = defaultdict(int)
        for value in categories.values():
            counts[value] += 1
        print(f"{jurisdiction_id:26} {len(categories):3}/{len(categories) + len(unmapped):3}"
              f"  changed={len(delta):3}  " + " ".join(f"{k.split('-')[0]}={v}" for k, v in sorted(counts.items())))
        if delta:
            changed += len(delta)
        if args.write:
            config["district_categories"] = categories
            evidence_all[jurisdiction_id] = evidence

    if args.write:
        SOURCES_PATH.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
        EVIDENCE_PATH.write_text(json.dumps(dict(sorted(evidence_all.items())), indent=1) + "\n",
                                 encoding="utf-8")
        print(f"\nwrote {SOURCES_PATH.name} and {EVIDENCE_PATH.name}")
    elif changed:
        print(f"\n{changed} mapping(s) differ from the committed data; re-run with --write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
