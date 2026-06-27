"""Generic source-pack draft promoter.

Promotes reviewed draft manifests from ``.tmp/source_pack_drafts/{state}/{id}/``
into the live product by performing two writes:

  1. Curated source pack at
     ``apps/api/app/data/source_packs/{state}/{id}/manifest.json``
     (``coverage_status`` forced to ``source_indexed``; sources/district tags
     preserved verbatim from the draft).

  2. ``apps/api/app/data/jurisdictions.json`` entry added or updated so address
     resolution can reach the new corpus.

Re-runnable / idempotent: running twice over the same draft yields byte-identical
files and no duplicate jurisdictions.json entry.

Never writes ``coverage_status: public_supported`` — hard-forced to ``source_indexed``.

Usage::

    python scripts/promote_source_pack_drafts.py --id christiansburg-va
    python scripts/promote_source_pack_drafts.py --all
    python scripts/promote_source_pack_drafts.py --all --state va
    python scripts/promote_source_pack_drafts.py --id salem-va --state va \\
        --drafts-dir .tmp/source_pack_drafts \\
        --source-packs-dir apps/api/app/data/source_packs \\
        --jurisdictions-file apps/api/app/data/jurisdictions.json

Pure stdlib — no ``app``, ``settings``, or database imports.  Promotion and
reindex are separate human-gated steps.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRAFTS_DIR = REPO_ROOT / ".tmp" / "source_pack_drafts"
DEFAULT_SOURCE_PACKS_DIR = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_packs"
DEFAULT_JURISDICTIONS_FILE = REPO_ROOT / "apps" / "api" / "app" / "data" / "jurisdictions.json"

FORCED_COVERAGE_STATUS = "source_indexed"
FORBIDDEN_COVERAGE_STATUS = "public_supported"
SCHEMA_VERSION = "source-pack/v1"
DISTRICT_MAPPING_STRATEGY = (
    "source_indexed_until_city_zoning_code_and_gis_layers_qa_pass"
)

# Full state name lookup (extend as non-VA states are onboarded).
_STATE_FULL_NAMES: dict[str, str] = {
    "VA": "Virginia",
    "CA": "California",
    "TX": "Texas",
    "NY": "New York",
    "FL": "Florida",
    "MD": "Maryland",
    "NC": "North Carolina",
    "PA": "Pennsylvania",
    "GA": "Georgia",
    "OH": "Ohio",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _strip_state_suffix(name: str) -> str:
    """Strip the trailing ', STATE' suffix from a jurisdiction name.

    Examples:
        "Christiansburg, VA" -> "Christiansburg"
        "Montgomery County, VA" -> "Montgomery County"
        "Roanoke" -> "Roanoke"  (no suffix, unchanged)
    """
    if ", " in name:
        return name.rsplit(", ", 1)[0]
    return name


def _derive_locality_names(jur: dict) -> list[str]:
    """Derive locality_names list from the jurisdiction block.

    For all jurisdiction types: strip the state-suffix from ``name``.
    This gives the primary locality string used for address matching.
    """
    name: str = jur.get("name", "")
    locality = _strip_state_suffix(name)
    return [locality] if locality else []


def _derive_county_names(jur: dict) -> list[str]:
    """Derive county_names from the jurisdiction block.

    Judgment calls (documented):
    - ``municipality`` / ``town``: use the ``county_name`` or ``county`` field
      from the draft (the town sits inside a county).
    - ``county``: the county itself; use ``county_name``/``county`` from the
      draft, or fall back to the jurisdiction name (minus state suffix).
    - ``independent_city``: Virginia independent cities are not part of any
      county; derive "<City> City" and "City of <City>" so both common name
      variants match, mirroring the live roanoke-va entry.
    """
    jtype: str = jur.get("jurisdiction_type", "")
    # Draft may use either "county_name" or "county" for the parent county.
    county_raw: str = jur.get("county_name") or jur.get("county") or ""
    name: str = jur.get("name", "")

    if jtype == "independent_city":
        city_name = _strip_state_suffix(name)
        return [f"{city_name} City", f"City of {city_name}"]

    if jtype == "county":
        if county_raw:
            return [county_raw]
        # Fallback: the jurisdiction is itself the county.
        fallback = _strip_state_suffix(name)
        return [fallback] if fallback else []

    # municipality, town, special_district, etc.
    if county_raw:
        return [county_raw]
    return []


def _derive_match_strategy(jur: dict) -> str:
    """Derive match_strategy from jurisdiction_type.

    Judgment call: the task description cites "locality_and_county" as the
    target for the roanoke-va (independent_city) example.  Applying it
    universally would break county and municipality entries, so we derive by
    type — matching the pattern already live in jurisdictions.json:
        county           -> "county"
        independent_city -> "locality_and_county"
        municipality/... -> "locality"
    """
    jtype: str = jur.get("jurisdiction_type", "")
    if jtype == "county":
        return "county"
    if jtype == "independent_city":
        return "locality_and_county"
    return "locality"


def _derive_state_names(state: str) -> list[str]:
    """Return [abbrev, full_name] for known states, else just [abbrev]."""
    abbrev = (state or "").upper()
    full = _STATE_FULL_NAMES.get(abbrev)
    if full:
        return [abbrev, full]
    return [abbrev] if abbrev else []


def _build_jurisdiction_entry(jur: dict) -> dict:
    """Build a jurisdictions.json entry from a draft jurisdiction block.

    Raises ValueError with a descriptive message if required fields are
    missing from the draft (fail loud rather than writing a partial entry).
    """
    required = ["jurisdiction_id", "name", "state"]
    missing = [f for f in required if not jur.get(f)]
    if missing:
        raise ValueError(
            f"Draft jurisdiction block is missing required field(s): "
            f"{missing!r}.  Cannot build a valid jurisdictions.json entry.  "
            f"Fix the draft manifest and re-run."
        )

    return {
        "jurisdiction_id": jur["jurisdiction_id"],
        "name": jur["name"],
        "state": jur["state"],
        "state_fips": jur.get("state_fips"),
        "county_fips": jur.get("county_fips"),
        "place_fips": jur.get("place_fips"),
        "jurisdiction_type": jur.get("jurisdiction_type", "municipality"),
        "coverage_status": FORCED_COVERAGE_STATUS,
        "supported": False,
        "match_strategy": _derive_match_strategy(jur),
        "locality_names": _derive_locality_names(jur),
        "county_names": _derive_county_names(jur),
        "state_names": _derive_state_names(jur["state"]),
        "official_source_urls": list(jur.get("official_source_urls") or []),
        "zoning_map_url": jur.get("zoning_map_url") or "",
        "planning_contact": dict(jur.get("planning_contact") or {}),
        "last_verified_at": date.today().isoformat(),
        "district_mapping_strategy": DISTRICT_MAPPING_STRATEGY,
    }


# ---------------------------------------------------------------------------
# Core promotion logic
# ---------------------------------------------------------------------------


def promote_draft(
    jurisdiction_id: str,
    *,
    drafts_dir: Path,
    source_packs_dir: Path,
    jurisdictions_file: Path,
    state: str | None = None,
) -> dict:
    """Promote a single draft to a curated source pack + jurisdictions.json entry.

    Parameters
    ----------
    jurisdiction_id:
        The jurisdiction slug, e.g. ``"christiansburg-va"``.
    drafts_dir:
        Root of the draft manifests tree (contains ``{state}/{id}/``).
    source_packs_dir:
        Root of the curated source packs tree (output).
    jurisdictions_file:
        Path to ``jurisdictions.json`` (read-modify-write).
    state:
        Optional state sub-directory (e.g. ``"va"``).  When omitted the
        function globs under *drafts_dir* for the matching ``jurisdiction_id``.

    Returns
    -------
    dict with keys: ``id``, ``sources`` (count), ``pack_path``,
    ``jurisdiction_action`` (``"added"`` or ``"updated"``).

    Raises
    ------
    ValueError
        If the draft manifest is not found or the draft is structurally invalid.
    """
    # --- 1. Locate draft manifest ---
    if state:
        draft_path = drafts_dir / state.lower() / jurisdiction_id / "manifest.json"
        if not draft_path.exists():
            raise ValueError(
                f"Draft manifest not found: {draft_path}\n"
                f"Run the batch scraper first and review the draft before promoting."
            )
    else:
        candidates = sorted(drafts_dir.glob(f"*/{jurisdiction_id}/manifest.json"))
        if not candidates:
            raise ValueError(
                f"No draft manifest found for {jurisdiction_id!r} anywhere under "
                f"{drafts_dir}.\n"
                f"Run the batch scraper first and review the draft before promoting."
            )
        if len(candidates) > 1:
            paths = ", ".join(str(p) for p in candidates)
            raise ValueError(
                f"Ambiguous: multiple draft manifests found for {jurisdiction_id!r}:\n"
                f"  {paths}\n"
                f"Use --state to disambiguate."
            )
        draft_path = candidates[0]

    # --- 2. Load and validate draft ---
    try:
        draft = _load_json(draft_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read draft at {draft_path}: {exc}") from exc

    if not isinstance(draft, dict):
        raise ValueError(
            f"Draft manifest at {draft_path} must be a JSON object, got "
            f"{type(draft).__name__}."
        )

    # --- 3. Build curated source pack ---
    jur = dict(draft.get("jurisdiction") or {})
    jid = jur.get("jurisdiction_id") or jurisdiction_id

    # Force coverage_status — NEVER write public_supported.
    jur["coverage_status"] = FORCED_COVERAGE_STATUS

    # Ensure parent_jurisdiction_id is present (required by validate_source_packs.py).
    jur.setdefault("parent_jurisdiction_id", None)

    curated_pack = {
        "schema_version": SCHEMA_VERSION,
        "jurisdiction": jur,
        "verification_notes": draft.get("verification_notes") or "",
        "sources": list(draft.get("sources") or []),
        "scrape_provenance": dict(draft.get("scrape_provenance") or {}),
    }

    # Determine state slug for output path: prefer draft's jurisdiction.state,
    # fall back to the parent directory name from the draft path.
    state_slug = (jur.get("state") or "").lower() or draft_path.parent.parent.name

    pack_out_path = source_packs_dir / state_slug / jid / "manifest.json"
    _write_json(pack_out_path, curated_pack)
    n_sources = len(curated_pack["sources"])

    # --- 4. Build jurisdictions.json entry ---
    try:
        jur_entry = _build_jurisdiction_entry(jur)
    except ValueError:
        raise  # re-raise with original message

    # --- 5. Update jurisdictions.json (add or replace in-place) ---
    if jurisdictions_file.exists():
        try:
            jurisdictions_data = _load_json(jurisdictions_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Cannot read jurisdictions file {jurisdictions_file}: {exc}"
            ) from exc
    else:
        jurisdictions_data = []

    # Handle both {"jurisdictions": [...]} wrapper and bare list.
    if isinstance(jurisdictions_data, dict):
        jurisdictions_list: list = list(jurisdictions_data.get("jurisdictions") or [])
        _is_wrapped = True
    else:
        jurisdictions_list = list(jurisdictions_data)
        _is_wrapped = False

    # Find and replace existing entry (match on jurisdiction_id).
    existing_idx: int | None = None
    for i, entry in enumerate(jurisdictions_list):
        if isinstance(entry, dict) and entry.get("jurisdiction_id") == jid:
            existing_idx = i
            break

    if existing_idx is not None:
        jurisdictions_list[existing_idx] = jur_entry
        jurisdiction_action = "updated"
    else:
        jurisdictions_list.append(jur_entry)
        jurisdiction_action = "added"

    if _is_wrapped:
        jurisdictions_data["jurisdictions"] = jurisdictions_list  # type: ignore[index]
        out_data: object = jurisdictions_data
    else:
        out_data = jurisdictions_list

    _write_json(jurisdictions_file, out_data)

    return {
        "id": jid,
        "sources": n_sources,
        "pack_path": str(pack_out_path),
        "jurisdiction_action": jurisdiction_action,
    }


# ---------------------------------------------------------------------------
# Draft discovery
# ---------------------------------------------------------------------------


def find_all_drafts(
    drafts_dir: Path, state: str | None = None
) -> list[tuple[str, str]]:
    """Return sorted list of (state_slug, jurisdiction_id) for all drafts found.

    Parameters
    ----------
    drafts_dir:
        Root of the draft manifests tree.
    state:
        Optional state filter (e.g. ``"va"``).
    """
    if state:
        pattern = f"{state.lower()}/*/manifest.json"
    else:
        pattern = "*/*/manifest.json"

    results: list[tuple[str, str]] = []
    for path in sorted(drafts_dir.glob(pattern)):
        state_slug = path.parent.parent.name
        jid = path.parent.name
        results.append((state_slug, jid))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="promote_source_pack_drafts",
        description=(
            "Promote reviewed source-pack drafts into the live product.\n\n"
            "Writes for each jurisdiction:\n"
            "  1. apps/api/app/data/source_packs/{state}/{id}/manifest.json\n"
            "     (coverage_status forced to source_indexed; sources preserved verbatim)\n"
            "  2. apps/api/app/data/jurisdictions.json entry added or updated\n"
            "     (so address resolution can reach the new corpus)\n\n"
            "Idempotent: re-running over the same draft yields identical files.\n"
            "Never writes coverage_status=public_supported."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    exclusive = parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument(
        "--id",
        dest="jurisdiction_id",
        metavar="ID",
        help="Promote a single jurisdiction by id (e.g. christiansburg-va).",
    )
    exclusive.add_argument(
        "--all",
        action="store_true",
        help="Promote every draft found under --drafts-dir (optionally filtered by --state).",
    )
    parser.add_argument(
        "--state",
        metavar="STATE",
        help="State sub-directory filter, e.g. va.  Required when --id is ambiguous.",
    )
    parser.add_argument(
        "--drafts-dir",
        type=Path,
        default=DEFAULT_DRAFTS_DIR,
        metavar="DIR",
        help=(
            "Root directory of draft manifests "
            f"(default: .tmp/source_pack_drafts relative to repo root)."
        ),
    )
    parser.add_argument(
        "--source-packs-dir",
        type=Path,
        default=DEFAULT_SOURCE_PACKS_DIR,
        metavar="DIR",
        help=(
            "Root directory for curated source packs "
            "(default: apps/api/app/data/source_packs)."
        ),
    )
    parser.add_argument(
        "--jurisdictions-file",
        type=Path,
        default=DEFAULT_JURISDICTIONS_FILE,
        metavar="FILE",
        help="Path to jurisdictions.json (default: apps/api/app/data/jurisdictions.json).",
    )

    args = parser.parse_args(argv)

    ids_to_promote: list[tuple[str | None, str]]
    if args.all:
        found = find_all_drafts(args.drafts_dir, args.state)
        if not found:
            state_info = f" for state {args.state!r}" if args.state else ""
            print(f"[promote] No drafts found under {args.drafts_dir}{state_info}.")
            return 0
        ids_to_promote = list(found)
    else:
        ids_to_promote = [(args.state, args.jurisdiction_id)]

    promoted = 0
    failed = 0
    for state_slug, jid in ids_to_promote:
        try:
            result = promote_draft(
                jid,
                drafts_dir=args.drafts_dir,
                source_packs_dir=args.source_packs_dir,
                jurisdictions_file=args.jurisdictions_file,
                state=state_slug,
            )
            print(
                f"[promote] {result['id']}: {result['sources']} source(s) | "
                f"pack written -> {result['pack_path']} | "
                f"jurisdictions.json: {result['jurisdiction_action']}"
            )
            promoted += 1
        except ValueError as exc:
            print(f"[promote] ERROR {jid}: {exc}", file=sys.stderr)
            failed += 1

    print(f"\n[promote] Done: {promoted} promoted, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
