"""Batch scrape driver for jurisdiction expansion (Stage 2).

Turns "one city at a time" into one unattended run over a city list,
writing draft source packs to ``.tmp/source_pack_drafts`` for human
review **before** any promotion step.

SAFETY BOUNDARY
---------------
This script stops at *validated drafts*.  It does NOT:
  - promote drafts into ``apps/api/app/data/source_packs``
  - call any app/settings/database layer
  - trigger a vector reindex

Promotion into the curated tree and reindexing remain deliberate,
human-gated steps.  Run ``scripts/ws2_merge_scraped_sources.py`` (or
the equivalent hand-review step) after inspecting the batch report.

City-list JSON schema
---------------------
The input is a JSON array of objects.  Required fields per entry:

  ``city``   (str)  — jurisdiction name passed to the scraper.
  ``state``  (str)  — two-letter state code, e.g. ``"VA"``.

Optional fields (all map 1-to-1 to the scraper's CLI flags):

  ``county``            (str)  — parent county name.
  ``jurisdiction_id``   (str)  — override derived id.
  ``jurisdiction_type`` (str)  — e.g. ``"municipality"`` (default).
  ``fetcher``           (str)  — ``"municode"`` | ``"generic_html"`` |
                                 ``"flippingbook"`` | ``"municipalcodeonline"``
                                 (default: ``"municode"``).
  ``url``               (list[str]) — official URL(s); required by generic_html.
  ``host_slug``         (str)  — municipalcodeonline subdomain slug.
  ``chapters``          (list[str]) — municipalcodeonline chapter node ids.
  ``max_sections``      (int)  — cap section count (for smoke tests / cost control).
  ``coverage_status``   (str)  — default ``"source_indexed"``.
  ``county_fips``       (str)  — 3-digit county FIPS.
  ``place_fips``        (str)  — 5-digit Census place FIPS.
  ``county_name``       (str)  — sets county_name without deriving parent id.
  ``delay``             (float)— min seconds between requests (default 1.0).

Example (see ``scripts/va_sample_cities.json`` for a ready-to-run file):

    [
      {
        "city": "Blacksburg",
        "state": "VA",
        "county": "Montgomery",
        "fetcher": "municode",
        "max_sections": 5
      },
      {
        "city": "Radford",
        "state": "VA",
        "county": "Radford City",
        "fetcher": "municode"
      }
    ]

Exit codes
----------
0  — every city scraped successfully (no failures, no blocks).
1  — one or more cities failed or were blocked, or the city list was invalid.

Usage
-----
    python scripts/batch_scrape.py --city-list scripts/va_sample_cities.json
    python scripts/batch_scrape.py --city-list scripts/va_sample_cities.json --skip-existing
    python scripts/batch_scrape.py --city-list scripts/va_sample_cities.json \\
        --output-root .tmp/my_drafts --delay 2.0
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo-root bootstrap: allow ``python scripts/batch_scrape.py`` AND
# ``python -m scripts.batch_scrape`` (the latter sets __package__).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import the scraper's run() via the public module path so tests can monkeypatch it.
from services.ingestion.scraper.run_scrape import build_parser as _scraper_build_parser  # noqa: E402
from services.ingestion.scraper.run_scrape import run as _scraper_run  # noqa: E402


def _default_output_root() -> Path:
    return _REPO_ROOT / ".tmp" / "source_pack_drafts"


def _load_validate_module():
    """Dynamically load ``scripts/validate_source_packs.py`` as a module.

    We use importlib so the validator stays importable even when this script
    is invoked as a top-level ``python scripts/batch_scrape.py`` (i.e. when
    ``scripts/`` is not a package).  Tests can monkeypatch ``_validate_draft``
    directly; they never need to touch this loader.
    """
    module_name = "_batch_scrape_validator"
    # Return a cached instance if already loaded.
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    validate_path = _REPO_ROOT / "scripts" / "validate_source_packs.py"
    spec = importlib.util.spec_from_file_location(module_name, validate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load validate_source_packs from {validate_path}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so that @dataclass (which resolves
    # ``sys.modules.get(cls.__module__)``) sees a real module, not None.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[arg-type]
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

SCRAPE_OK = "scraped"
SCRAPE_BLOCKED = "blocked"
SCRAPE_FAILED = "failed"
SCRAPE_SKIPPED = "skipped"


@dataclass
class CityResult:
    """Per-city outcome recorded in the batch report."""

    city: str
    state: str
    jurisdiction_id: str
    status: str = ""           # SCRAPE_OK | SCRAPE_BLOCKED | SCRAPE_FAILED | SCRAPE_SKIPPED
    section_count: int = 0
    validation_ok: bool = False
    validation_errors: int = 0
    validation_warnings: int = 0
    output_path: str = ""
    error_detail: str = ""


@dataclass
class BatchReport:
    """Aggregated result written to ``_batch_report.json``."""

    run_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    city_list_path: str = ""
    output_root: str = ""
    cities: list[CityResult] = field(default_factory=list)

    # summary counters
    total: int = 0
    scraped: int = 0
    blocked: int = 0
    failed: int = 0
    skipped: int = 0
    validated_ok: int = 0

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "city_list_path": self.city_list_path,
            "output_root": self.output_root,
            "summary": {
                "total": self.total,
                "scraped": self.scraped,
                "blocked": self.blocked,
                "failed": self.failed,
                "skipped": self.skipped,
                "validated_ok": self.validated_ok,
            },
            "note": (
                "DRAFTS ONLY — do not promote or reindex. "
                "Inspect each manifest.json, then run scripts/ws2_merge_scraped_sources.py "
                "(or equivalent) to merge into the curated source pack tree."
            ),
            "cities": [
                {
                    "city": c.city,
                    "state": c.state,
                    "jurisdiction_id": c.jurisdiction_id,
                    "status": c.status,
                    "section_count": c.section_count,
                    "validation_ok": c.validation_ok,
                    "validation_errors": c.validation_errors,
                    "validation_warnings": c.validation_warnings,
                    "output_path": c.output_path,
                    "error_detail": c.error_detail,
                }
                for c in self.cities
            ],
        }


# ---------------------------------------------------------------------------
# City-list parsing
# ---------------------------------------------------------------------------


def parse_city_list(path: Path) -> list[dict[str, Any]]:
    """Read and validate the JSON city list.

    Returns a list of city entry dicts.  Raises ``ValueError`` on bad input.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read city list {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"City list must be a JSON array, got {type(raw).__name__}")

    entries: list[dict] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"City list entry {i} must be a JSON object, got {type(entry).__name__}")
        if "city" not in entry or "state" not in entry:
            raise ValueError(f"City list entry {i} missing required field 'city' or 'state': {entry!r}")
        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Argument namespace builder (city entry → argparse.Namespace)
# ---------------------------------------------------------------------------
from services.ingestion.scraper.manifest_builder import slugify as _slugify  # noqa: E402


def _entry_to_namespace(entry: dict, *, output_root: Path, global_delay: float | None) -> argparse.Namespace:
    """Convert a city-list entry dict into an ``argparse.Namespace`` for :func:`run`.

    Field defaults mirror ``build_parser()`` from ``run_scrape.py``.
    """
    # Use the scraper's build_parser to get the canonical defaults, then
    # override with entry-specific values.
    parser = _scraper_build_parser()
    # Parse an empty argv to get all defaults populated.
    defaults = parser.parse_args(
        ["--city", entry["city"], "--state", entry["state"]]
    )

    ns = argparse.Namespace(**vars(defaults))

    # Apply entry overrides.
    ns.city = entry["city"]
    ns.state = entry["state"]
    ns.fetcher = entry.get("fetcher", "municode")
    ns.county = entry.get("county", None)
    ns.jurisdiction_id = entry.get("jurisdiction_id", None)
    ns.jurisdiction_type = entry.get("jurisdiction_type", "municipality")
    ns.coverage_status = entry.get("coverage_status", "source_indexed")
    ns.url = entry.get("url", []) or []
    ns.host_slug = entry.get("host_slug", None)
    ns.chapters = entry.get("chapters", []) or []
    ns.county_fips = entry.get("county_fips", None)
    ns.place_fips = entry.get("place_fips", None)
    ns.county_name = entry.get("county_name", None)
    ns.max_sections = entry.get("max_sections", None)

    # Platform-specific identifiers (thread through when present so batch mode
    # can drive eCode360 / American Legal / enCodePlus without name resolution).
    if "code_id" in entry:
        ns.code_id = entry["code_id"]
    if "client_slug" in entry:
        ns.client_slug = entry["client_slug"]
    if "code_slug" in entry:
        ns.code_slug = entry["code_slug"]
    if "regs_slug" in entry:
        ns.regs_slug = entry["regs_slug"]
    if "impersonate" in entry:
        ns.impersonate = entry["impersonate"]

    # delay: city-entry takes precedence, then global CLI override, then default 1.0
    ns.delay = float(entry.get("delay", global_delay if global_delay is not None else 1.0))

    # output_root is always driven by the batch-level flag (not per-city)
    ns.output_root = output_root

    return ns


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def _validate_draft(draft_root: Path, jurisdiction_id: str) -> tuple[bool, int, int]:
    """Validate the draft root and return the per-city result.

    ``validate_source_packs`` walks the entire root, but we scope the recorded
    counts to *this* city by finding the ``summary`` whose ``jurisdiction_id``
    matches.  This keeps one bad city from retroactively stamping errors onto a
    previously-clean city's row, and mirrors the per-city scoping in
    :func:`_draft_validates`.

    Returns ``(ok, error_count, warning_count)`` for this city.  If no matching
    summary is found (e.g. the manifest could not be parsed at all), returns a
    graceful failure ``(False, 1, 0)``.
    """
    validator = _load_validate_module()
    result = validator.validate_source_packs(draft_root)
    for summary in result.summaries:
        if summary.jurisdiction_id == jurisdiction_id:
            return summary.error_count == 0, summary.error_count, summary.warning_count
    # No summary for this city — the validator never recognized it as a pack.
    return False, 1, 0


def _section_count_from_manifest(manifest_path: Path) -> int:
    """Return the number of sources in a manifest, 0 on error."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return len(data.get("sources", []))
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Draft-exists check (for --skip-existing)
# ---------------------------------------------------------------------------


def _draft_validates(output_root: Path, state: str, jurisdiction_id: str) -> bool:
    """Return True if a draft for this city already exists and validates."""
    manifest = output_root / state.lower() / jurisdiction_id / "manifest.json"
    if not manifest.exists():
        return False
    # Run a scoped validate on just this city's subdirectory.
    validator = _load_validate_module()
    city_root = output_root / state.lower() / jurisdiction_id
    # validate_source_packs expects the *root* that contains state/id subdirs,
    # so pass the parent (the state dir) and check that this id validates.
    # Simpler: validate the whole draft root (cheap) — if the manifest exists
    # and the full root validates (or this city has no errors), treat as done.
    try:
        result = validator.validate_source_packs(output_root)
        for summary in result.summaries:
            if summary.jurisdiction_id == jurisdiction_id and summary.error_count == 0:
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Core batch loop
# ---------------------------------------------------------------------------


def run_batch(
    entries: list[dict],
    *,
    output_root: Path,
    skip_existing: bool = False,
    global_delay: float | None = None,
) -> BatchReport:
    """Run scrape + validate for each city entry.

    Continue-on-error: a blocked (exit 2) or failed (exit 1) city is
    recorded and the loop proceeds to the next city.  One bad city never
    aborts the batch.

    Resumability is provided by two mechanisms:
    1. ``--skip-existing``: cities whose draft already validates are skipped
       entirely (no re-scrape, no re-validate).
    2. The scraper's on-disk ``raw/`` cache: even when not skipped, the
       fetcher reuses cached HTTP responses so re-runs don't re-hit the network.
    """
    report = BatchReport(output_root=str(output_root))

    for entry in entries:
        city = entry["city"]
        state = entry["state"].upper()
        raw_jid = entry.get("jurisdiction_id")
        jurisdiction_id = raw_jid if raw_jid else f"{_slugify(city)}-{state.lower()}"

        cr = CityResult(city=city, state=state, jurisdiction_id=jurisdiction_id)

        # --skip-existing: if a validated draft already exists, skip.
        if skip_existing and _draft_validates(output_root, state, jurisdiction_id):
            cr.status = SCRAPE_SKIPPED
            manifest = output_root / state.lower() / jurisdiction_id / "manifest.json"
            cr.output_path = str(manifest)
            cr.section_count = _section_count_from_manifest(manifest)
            cr.validation_ok = True
            print(
                f"[batch] SKIP {city}, {state} ({jurisdiction_id}) — validated draft exists",
                file=sys.stderr,
            )
            report.cities.append(cr)
            report.skipped += 1
            continue

        # Build the Namespace the scraper expects.
        ns = _entry_to_namespace(entry, output_root=output_root, global_delay=global_delay)

        print(f"[batch] START {city}, {state} ({jurisdiction_id})", file=sys.stderr)

        # --- Scrape ---
        try:
            exit_code = _scraper_run(ns)
        except SystemExit as exc:
            # _build_fetcher raises SystemExit on bad args (string or int code).
            # Treat any SystemExit as a configuration failure (exit 1).
            raw_code = exc.code
            if isinstance(raw_code, int):
                exit_code = raw_code if raw_code != 0 else 1
            else:
                exit_code = 1
            cr.error_detail = f"SystemExit({raw_code!r})"
        except Exception as exc:  # noqa: BLE001
            exit_code = 1
            cr.error_detail = traceback.format_exc()
            print(f"[batch] EXCEPTION for {city}, {state}: {exc}", file=sys.stderr)

        manifest_path = output_root / state.lower() / jurisdiction_id / "manifest.json"

        if exit_code == 0:
            cr.status = SCRAPE_OK
            cr.output_path = str(manifest_path)
            cr.section_count = _section_count_from_manifest(manifest_path)
        elif exit_code == 2:
            cr.status = SCRAPE_BLOCKED
            cr.error_detail = cr.error_detail or "Fetcher returned exit 2 (blocked/rate-limited)."
            print(f"[batch] BLOCKED {city}, {state}", file=sys.stderr)
        else:
            cr.status = SCRAPE_FAILED
            cr.error_detail = cr.error_detail or f"Scraper exited {exit_code}."
            print(f"[batch] FAILED  {city}, {state} (exit {exit_code})", file=sys.stderr)

        # --- Validate draft (only if scrape produced a manifest) ---
        # Scoped to THIS city's jurisdiction_id so another city's error never
        # retroactively stamps this row.
        if cr.status == SCRAPE_OK and manifest_path.exists():
            try:
                ok, nerrors, nwarnings = _validate_draft(output_root, jurisdiction_id)
                cr.validation_ok = ok
                cr.validation_errors = nerrors
                cr.validation_warnings = nwarnings
            except Exception as exc:  # noqa: BLE001
                cr.validation_ok = False
                cr.error_detail += f" | validate error: {exc}"

        report.cities.append(cr)

    # Tally summary counters.
    report.total = len(report.cities)
    report.scraped = sum(1 for c in report.cities if c.status == SCRAPE_OK)
    report.blocked = sum(1 for c in report.cities if c.status == SCRAPE_BLOCKED)
    report.failed = sum(1 for c in report.cities if c.status == SCRAPE_FAILED)
    report.skipped = sum(1 for c in report.cities if c.status == SCRAPE_SKIPPED)
    report.validated_ok = sum(1 for c in report.cities if c.validation_ok)

    return report


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------


def write_batch_report(report: BatchReport, output_root: Path) -> Path:
    """Write machine-readable JSON report to ``output_root/_batch_report.json``."""
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "_batch_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return report_path


def print_human_summary(report: BatchReport, report_path: Path) -> None:
    """Print a concise human-readable summary to stderr."""
    lines = [
        "",
        "=" * 68,
        "BATCH SCRAPE REPORT",
        f"  Run at    : {report.run_at}",
        f"  Cities    : {report.total}  (scraped={report.scraped}  blocked={report.blocked}"
        f"  failed={report.failed}  skipped={report.skipped})",
        f"  Validated : {report.validated_ok}/{report.scraped} scraped packs passed validation",
        f"  Report    : {report_path}",
        "-" * 68,
    ]
    for c in report.cities:
        tag = f"[{c.status.upper():<8}]"
        val = "val=OK" if c.validation_ok else f"val=ERR({c.validation_errors}err/{c.validation_warnings}warn)"
        sec = f"sections={c.section_count}" if c.section_count else ""
        parts = [tag, f"{c.city}, {c.state}", sec, val]
        if c.error_detail:
            parts.append(f"| {c.error_detail[:80]}")
        lines.append("  " + "  ".join(p for p in parts if p))
    lines.append("=" * 68)
    lines.append(
        "NOTE: DRAFTS ONLY — do not promote or reindex until manually reviewed."
    )
    lines.append("")
    print("\n".join(lines), file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch scrape driver (Stage 2 — jurisdiction expansion). "
            "Reads a JSON city list, runs the WS1 scraper + validator for each city, "
            "writes drafts to .tmp/source_pack_drafts, and emits a batch report. "
            "SAFETY: stops at validated drafts; never promotes or reindexes."
        )
    )
    parser.add_argument(
        "--city-list",
        type=Path,
        required=True,
        help="Path to a JSON file containing a list of city entries (see module docstring for schema).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Root directory for draft packs (default: .tmp/source_pack_drafts).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip cities whose draft already validates (resumability).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help=(
            "Global min seconds between requests, applied to all cities unless "
            "overridden per-city in the JSON list (default: 1.0)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_root = args.output_root or _default_output_root()

    # Parse city list.
    try:
        entries = parse_city_list(args.city_list)
    except ValueError as exc:
        print(f"[batch] ERROR: {exc}", file=sys.stderr)
        return 1

    if not entries:
        print("[batch] city list is empty — nothing to do.", file=sys.stderr)
        return 0

    print(
        f"[batch] Starting batch scrape: {len(entries)} cit(y/ies), "
        f"output_root={output_root}, skip_existing={args.skip_existing}",
        file=sys.stderr,
    )

    report = run_batch(
        entries,
        output_root=output_root,
        skip_existing=args.skip_existing,
        global_delay=args.delay,
    )
    report.city_list_path = str(args.city_list)

    report_path = write_batch_report(report, output_root)
    print_human_summary(report, report_path)

    # Exit non-zero if any city failed (CI/cron-friendly).
    if report.failed > 0 or report.blocked > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
