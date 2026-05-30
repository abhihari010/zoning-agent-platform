"""CLI entry point for the WS1 ingestion scraper.

Example::

    python services/ingestion/scraper/run_scrape.py --city "Blacksburg" --state VA

This:
1. Selects a fetcher (Municode by default; ``--fetcher generic_html`` with
   ``--url`` for the fallback).
2. Fetches real ordinance sections, caching raw responses under the pack's
   ``raw/`` directory.
3. Builds a schema-valid ``source-pack/v1`` manifest (one source per section).
4. Writes it to ``<output-root>/{state}/{jurisdiction-id}/manifest.json``.

The default output root is ``.tmp/source_pack_drafts`` so a real scrape never
overwrites the curated ``services/ingestion/source_packs`` manifests.  Validate
the result with::

    python scripts/validate_source_packs.py --source-packs-dir <output-root>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script (``python services/ingestion/scraper/run_scrape.py``)
# as well as a module (``python -m services.ingestion.scraper.run_scrape``).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from services.ingestion.scraper.fetchers import GenericHtmlFetcher, MunicodeFetcher
    from services.ingestion.scraper.fetchers.base import Fetcher
    from services.ingestion.scraper.http_client import FetchBlockedError
    from services.ingestion.scraper.manifest_builder import build_manifest, slugify
else:  # pragma: no cover - exercised via module execution
    from .fetchers import GenericHtmlFetcher, MunicodeFetcher
    from .fetchers.base import Fetcher
    from .http_client import FetchBlockedError
    from .manifest_builder import build_manifest, slugify


def default_output_root() -> Path:
    return Path(__file__).resolve().parents[3] / ".tmp" / "source_pack_drafts"


def _pack_dir(output_root: Path, state: str, jurisdiction_id: str) -> Path:
    return output_root / state.lower() / jurisdiction_id


def _build_fetcher(args: argparse.Namespace, *, raw_dir: Path) -> Fetcher:
    if args.fetcher == "municode":
        return MunicodeFetcher(
            cache_dir=raw_dir,
            request_delay=args.delay,
            max_sections=args.max_sections,
        )
    if args.fetcher == "generic_html":
        if not args.url:
            raise SystemExit("--fetcher generic_html requires at least one --url.")
        return GenericHtmlFetcher(
            args.url,
            cache_dir=raw_dir,
            request_delay=args.delay,
        )
    raise SystemExit(f"Unknown fetcher: {args.fetcher}")


def run(args: argparse.Namespace) -> int:
    state = args.state.upper()
    jurisdiction_id = args.jurisdiction_id or f"{slugify(args.city)}-{state.lower()}"
    output_root = args.output_root or default_output_root()
    pack_dir = _pack_dir(output_root, state, jurisdiction_id)
    raw_dir = pack_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    fetcher = _build_fetcher(args, raw_dir=raw_dir)

    print(f"[ws1] fetching {args.city}, {state} via {fetcher.name} ...", file=sys.stderr)
    try:
        result = fetcher.fetch(city=args.city, state=state)
    except FetchBlockedError as exc:
        print(f"[ws1] BLOCKED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surface a clear message, don't hammer
        print(f"[ws1] fetch failed: {exc}", file=sys.stderr)
        return 1

    if not result.sections:
        print("[ws1] no sections extracted; nothing to write.", file=sys.stderr)
        return 1

    provenance = {**result.provenance, "source_home_url": result.source_home_url}
    manifest = build_manifest(
        city=args.city,
        state=state,
        records=result.sections,
        jurisdiction_type=args.jurisdiction_type,
        county=args.county,
        jurisdiction_id=args.jurisdiction_id,
        official_source_urls=args.url or None,
        coverage_status=args.coverage_status,
        effective_date=result.effective_date,
        provenance=provenance,
    )

    manifest_path = pack_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"[ws1] wrote {len(result.sections)} section source(s) -> {manifest_path}",
        file=sys.stderr,
    )
    print(
        f"[ws1] validate with: python scripts/validate_source_packs.py "
        f"--source-packs-dir {output_root}",
        file=sys.stderr,
    )
    print(str(manifest_path))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape real zoning ordinance text into a source pack.")
    parser.add_argument("--city", required=True, help='Jurisdiction name, e.g. "Blacksburg".')
    parser.add_argument("--state", required=True, help="Two-letter state code, e.g. VA.")
    parser.add_argument(
        "--fetcher",
        choices=["municode", "generic_html"],
        default="municode",
        help="Which fetcher to use (default: municode).",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Official URL(s); required for generic_html, optional override otherwise.",
    )
    parser.add_argument("--county", help="Parent county name (sets parent_jurisdiction_id).")
    parser.add_argument("--jurisdiction-id", help="Override the derived jurisdiction id.")
    parser.add_argument("--jurisdiction-type", default="municipality")
    parser.add_argument(
        "--coverage-status",
        default="source_indexed",
        help="Coverage status for the pack (default: source_indexed).",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Min seconds between requests.")
    parser.add_argument(
        "--max-sections",
        type=int,
        default=None,
        help="Cap the number of sections (useful for smoke tests).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Root for draft packs (default: .tmp/source_pack_drafts).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
