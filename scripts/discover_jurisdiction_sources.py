from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


SOURCE_CATEGORIES = [
    ("planning-zoning-page", "Official planning/zoning page", "planning_page", ["general"]),
    ("municipal-code", "Official zoning ordinance or municipal code", "zoning_ordinance", ["general"]),
    ("zoning-map-gis", "Official zoning map or GIS layer", "zoning_map", ["general"]),
    ("building-permits", "Official building permit page", "permit_page", ["general"]),
    ("business-license", "Official business license page", "permit_page", ["general"]),
    ("fire-marshal", "Official fire marshal or fire code page", "fire_code", ["food-service", "general"]),
    ("health-department", "Official health department page", "health_code", ["food-business", "food-service"]),
]

STATE_FIPS = {
    "AL": "01",
    "AK": "02",
    "AZ": "04",
    "AR": "05",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DE": "10",
    "DC": "11",
    "FL": "12",
    "GA": "13",
    "HI": "15",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "IA": "19",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "ME": "23",
    "MD": "24",
    "MA": "25",
    "MI": "26",
    "MN": "27",
    "MS": "28",
    "MO": "29",
    "MT": "30",
    "NE": "31",
    "NV": "32",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "NC": "37",
    "ND": "38",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "UT": "49",
    "VT": "50",
    "VA": "51",
    "WA": "53",
    "WV": "54",
    "WI": "55",
    "WY": "56",
}


def default_output_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".tmp" / "source_pack_drafts"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_draft_manifest(
    *,
    jurisdiction_name: str,
    state: str,
    jurisdiction_type: str,
    county: str | None = None,
    jurisdiction_id: str | None = None,
) -> dict:
    state = state.upper()
    slug = jurisdiction_id or f"{slugify(jurisdiction_name)}-{state.lower()}"
    parent_jurisdiction_id = f"{slugify(county)}-county-{state.lower()}" if county else None
    display_name = f"{jurisdiction_name}, {state}"

    return {
        "schema_version": "source-pack/v1",
        "jurisdiction": {
            "jurisdiction_id": slug,
            "name": display_name,
            "coverage_status": "source_discovery",
            "state": state,
            "state_fips": STATE_FIPS.get(state, "TODO_STATE_FIPS"),
            "county_fips": "TODO_COUNTY_FIPS",
            "place_fips": "TODO_PLACE_FIPS",
            "jurisdiction_type": jurisdiction_type,
            "parent_jurisdiction_id": parent_jurisdiction_id,
            "county_name": county,
            "official_source_urls": [],
            "zoning_map_url": None,
            "planning_contact": {
                "url": None,
                "email": None,
                "phone": None,
            },
        },
        "verification_notes": (
            f"Draft generated on {date.today().isoformat()}. Replace TODO URLs, verify official "
            "sources, capture effective dates, and mark source metadata.verification_status as verified."
        ),
        "sources": [
            _draft_source(slug, category_slug, title, source_type, uses)
            for category_slug, title, source_type, uses in SOURCE_CATEGORIES
        ],
    }


def write_draft_manifest(
    manifest: dict,
    *,
    output_root: str | Path | None = None,
    force: bool = False,
) -> Path:
    root = Path(output_root) if output_root else default_output_root()
    jurisdiction = manifest["jurisdiction"]
    state = str(jurisdiction["state"]).lower()
    jurisdiction_id = str(jurisdiction["jurisdiction_id"])
    pack_dir = root / state / jurisdiction_id
    manifest_path = pack_dir / "manifest.json"

    if manifest_path.exists() and not force:
        raise FileExistsError(f"Draft manifest already exists: {manifest_path}. Use --force to overwrite.")

    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "raw").mkdir(exist_ok=True)
    (pack_dir / "extracted").mkdir(exist_ok=True)
    notes_path = pack_dir / "notes.md"
    if force or not notes_path.exists():
        notes_path.write_text(
            "# Source Acquisition Notes\n\n"
            "- Verify official planning/zoning page.\n"
            "- Verify zoning ordinance/code host.\n"
            "- Verify zoning map/GIS source.\n"
            "- Capture planning contact.\n"
            "- Record blockers before promotion.\n",
            encoding="utf-8",
        )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _draft_source(
    jurisdiction_id: str,
    category_slug: str,
    title: str,
    source_type: str,
    uses: list[str],
) -> dict:
    return {
        "source_id": f"{jurisdiction_id}-{category_slug}",
        "title": f"TODO: {title}",
        "excerpt": f"TODO: Verify and extract the official {title.lower()}.",
        "section_ref": "TODO",
        "jurisdiction_id": jurisdiction_id,
        "url": "TODO_OFFICIAL_URL",
        "effective_date": "TODO_EFFECTIVE_DATE",
        "source_type": source_type,
        "districts": ["unknown"],
        "uses": uses,
        "metadata": {
            "verification_status": "candidate",
            "candidate_category": category_slug,
            "required_before_promotion": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a draft jurisdiction source-pack manifest skeleton.")
    parser.add_argument("--jurisdiction-name", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--jurisdiction-type", required=True)
    parser.add_argument("--county")
    parser.add_argument("--jurisdiction-id")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root(),
        help="Root for draft packs. Defaults to .tmp/source_pack_drafts to avoid production data changes.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing draft manifest.")
    args = parser.parse_args(argv)

    manifest = build_draft_manifest(
        jurisdiction_name=args.jurisdiction_name,
        state=args.state,
        jurisdiction_type=args.jurisdiction_type,
        county=args.county,
        jurisdiction_id=args.jurisdiction_id,
    )
    manifest_path = write_draft_manifest(manifest, output_root=args.output_root, force=args.force)
    print(f"Draft source pack created: {manifest_path}")
    print("Review TODO values and run python scripts/validate_source_packs.py --source-packs-dir <draft-root>.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
