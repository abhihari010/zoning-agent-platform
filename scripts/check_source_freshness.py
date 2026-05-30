#!/usr/bin/env python3
"""Report stale or unreachable zoning sources without changing source data."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_registry.json"
SOURCE_PACK_ROOT = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_packs"
PUBLIC_SUPPORTED = "public_supported"


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    url: str
    retrieved_at: str | None
    coverage_status: str
    origin: str


def load_sources() -> list[SourceRef]:
    refs: list[SourceRef] = []
    if SOURCE_REGISTRY.exists():
        for item in json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8")):
            refs.append(
                SourceRef(
                    source_id=str(item.get("source_id") or "<missing>"),
                    url=str(item.get("url") or ""),
                    retrieved_at=_retrieved_at(item),
                    coverage_status=_coverage_status(item),
                    origin=str(SOURCE_REGISTRY.relative_to(REPO_ROOT)),
                )
            )

    for manifest_path in sorted(SOURCE_PACK_ROOT.glob("*/*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pack_status = str(manifest.get("jurisdiction", {}).get("coverage_status") or "")
        for item in manifest.get("sources", []):
            refs.append(
                SourceRef(
                    source_id=str(item.get("source_id") or "<missing>"),
                    url=str(item.get("url") or ""),
                    retrieved_at=_retrieved_at(item),
                    coverage_status=pack_status or _coverage_status(item),
                    origin=str(manifest_path.relative_to(REPO_ROOT)),
                )
            )
    return refs


def check_freshness(
    sources: list[SourceRef],
    *,
    max_age_days: int,
    check_urls: bool,
    timeout: float,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    today = date.today()
    seen: set[tuple[str, str]] = set()

    for source in sources:
        dedupe_key = (source.source_id, source.origin)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        is_public = source.coverage_status == PUBLIC_SUPPORTED
        if not source.url.startswith(("http://", "https://")):
            message = f"{source.origin}: {source.source_id} has non-HTTP URL {source.url!r}"
            (errors if is_public else warnings).append(message)
            continue

        retrieved = _parse_date(source.retrieved_at)
        if retrieved is None:
            message = f"{source.origin}: {source.source_id} missing retrieved_at"
            (errors if is_public else warnings).append(message)
        else:
            age_days = (today - retrieved).days
            if age_days > max_age_days:
                message = (
                    f"{source.origin}: {source.source_id} retrieved_at is {age_days} days old "
                    f"(max {max_age_days})"
                )
                (errors if is_public else warnings).append(message)

        if check_urls:
            reachable = _url_reachable(source.url, timeout)
            if not reachable:
                message = f"{source.origin}: {source.source_id} URL did not respond successfully"
                (errors if is_public else warnings).append(message)

    return errors, warnings


def _retrieved_at(item: dict[str, Any]) -> str | None:
    value = item.get("retrieved_at")
    if isinstance(value, str) and value.strip():
        return value.strip()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = metadata.get("retrieved_at")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _coverage_status(item: dict[str, Any]) -> str:
    value = item.get("coverage_status")
    if isinstance(value, str) and value:
        return value
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = metadata.get("coverage_status")
    return value if isinstance(value, str) else ""


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _url_reachable(url: str, timeout: float) -> bool:
    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(url, method=method, headers={"User-Agent": "zoning-agent-source-check/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return 200 <= response.status < 400
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405}:
                continue
            return 200 <= exc.code < 400
        except (urllib.error.URLError, TimeoutError):
            continue
    return False


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check source freshness and optional URL reachability.")
    parser.add_argument("--max-age-days", type=int, default=90)
    parser.add_argument("--check-urls", action="store_true")
    parser.add_argument("--timeout", type=float, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    errors, warnings = check_freshness(
        load_sources(),
        max_age_days=args.max_age_days,
        check_urls=args.check_urls,
        timeout=args.timeout,
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(
        json.dumps(
            {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
