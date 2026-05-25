from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.ai.source_registry_retriever import ensure_seed_sources, ensure_source_index_ready  # noqa: E402
from app.jurisdictions import validate_public_support_candidate  # noqa: E402
from app.storage import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report whether jurisdictions satisfy machine-checkable public-support gates."
    )
    parser.add_argument("jurisdiction_ids", nargs="+", help="Jurisdiction IDs to check.")
    args = parser.parse_args()

    ensure_seed_sources()
    ensure_source_index_ready()
    exit_code = 0
    for jurisdiction_id in args.jurisdiction_ids:
        result = validate_public_support_candidate(jurisdiction_id, source_store=store)
        status = "eligible" if result.eligible else "blocked"
        print(f"{jurisdiction_id}: {status}")
        for error in result.errors:
            print(f"  ERROR: {error}")
        for warning in result.warnings:
            print(f"  WARN: {warning}")
        if not result.eligible:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
