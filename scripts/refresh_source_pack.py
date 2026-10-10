#!/usr/bin/env python3
"""Refresh a curated source pack's text from a rescrape draft, keeping its curation.

The freshness gate (``check_source_freshness.py``) fails CI once a live city's
sources pass 90 days, so every live pack is periodically rescraped with
``run_scrape.py`` / ``batch_scrape.py`` into a draft tree. This merges a draft
back into the curated pack **field by field**:

- matching section (by URL, else by ``source_id`` + title): refresh ``title``, ``section_ref``, ``full_text``, ``excerpt``, ``retrieved_at``,
  ``effective_date`` and merge ``metadata``; keep ``districts``, ``uses`` and
  every other hand-set field.
- in the draft only: appended as scraped (a section added upstream).
- in the curated pack only: kept untouched (reference links, curated-only
  entries) and listed, so a section removed upstream gets a human look.

The ``jurisdiction`` block is never touched -- unlike
``promote_source_pack_drafts.py``, which forces ``source_indexed``.

    python scripts/refresh_source_pack.py --drafts .tmp/source_pack_drafts va/richmond-va [...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK_ROOT = REPO_ROOT / "apps" / "api" / "app" / "data" / "source_packs"
REFRESHED = ("title", "section_ref", "full_text", "excerpt", "retrieved_at", "effective_date")
# Dates the scraper falls back to when the page states none; never let one
# overwrite a real date the curated pack already carries.
WEAK_DATE_SOURCES = {None, "unknown", "retrieval_date"}


def _ref(value: str | None) -> str:
    # Older packs carry trailing-period refs ("Sec. 30-682.1."), the scraper no longer does.
    return (value or "").strip().rstrip(".")


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def _unique_by(sources: list[dict], key: str) -> dict[str, dict]:
    counts: dict[str, int] = {}
    for source in sources:
        counts[source.get(key) or ""] = counts.get(source.get(key) or "", 0) + 1
    return {s[key]: s for s in sources if s.get(key) and counts[s[key]] == 1}


def _pair(curated: list[dict], draft: list[dict]) -> list[tuple[dict, dict]]:
    # The scraper suffixes colliding section numbers (-2, -12, ...) in crawl order, so a
    # source_id can name a different section on the next scrape -- winchester's zoning
    # and subdivision ordinances both have a "Sec. 5-1". A section's URL is stable, so
    # every URL match is settled first. Municode node ids embed the title's initials,
    # though, so a retitled section gets a new URL; for what is left, an id is trusted
    # only alongside the same title or section number.
    by_url = _unique_by(draft, "url")
    curated_urls = _unique_by(curated, "url")
    pairs: dict[int, dict] = {}
    claimed: set[int] = set()
    for source in curated:
        new = by_url.get(source.get("url")) if source.get("url") in curated_urls else None
        if new is not None:
            pairs[id(source)] = new
            claimed.add(id(new))
    by_id = {s["source_id"]: s for s in draft if id(s) not in claimed}
    for source in curated:
        new = by_id.get(source["source_id"])
        if id(source) in pairs or new is None or id(new) in claimed:
            continue
        if any(_ref(new.get(k)) and _ref(new.get(k)) == _ref(source.get(k)) for k in ("title", "section_ref")):
            pairs[id(source)] = new
            claimed.add(id(new))
    return [(s, pairs[id(s)]) for s in curated if id(s) in pairs]


def refresh(curated: dict, draft: dict) -> dict:
    """Merge ``draft`` into ``curated`` in place; return a change report."""
    pairs = _pair(curated["sources"], draft["sources"])
    matched = {id(new) for _, new in pairs}
    seen: set[str] = set()
    text_changed: list[str] = []
    for source, new in pairs:
        seen.add(source["source_id"])
        if _squash(source.get("full_text")) != _squash(new.get("full_text")):
            text_changed.append(source["source_id"])
        old_meta = source.get("metadata") or {}
        new_meta = new.get("metadata") or {}
        keep_date = (
            new_meta.get("effective_date_source") in WEAK_DATE_SOURCES
            and old_meta.get("effective_date_source") not in WEAK_DATE_SOURCES
        )
        for field in REFRESHED:
            if field == "effective_date" and keep_date:
                continue
            if field in new:
                source[field] = new[field]
        merged = {**old_meta, **new_meta}
        if keep_date:
            merged["effective_date_source"] = old_meta["effective_date_source"]
        source["metadata"] = merged

    kept = [s["source_id"] for s in curated["sources"] if s["source_id"] not in seen]
    taken = {s["source_id"] for s in curated["sources"]}
    added = [dict(s) for s in draft["sources"] if id(s) not in matched]
    for source in added:
        base, n = source["source_id"], 2
        while source["source_id"] in taken:
            source["source_id"] = f"{base}-{n}"
            n += 1
        taken.add(source["source_id"])
    curated["sources"].extend(added)
    return {
        "refreshed": len(seen),
        "text_changed": text_changed,
        "added": [s["source_id"] for s in added],
        "kept_unscraped": kept,
    }


def _write_like(path: Path, original: str, data: dict) -> None:
    body = json.dumps(data, indent=2, ensure_ascii=False)
    if original.replace("\r\n", "\n").endswith("\n"):
        body += "\n"
    path.write_text(body, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packs", nargs="+", help="state/jurisdiction-id, e.g. va/richmond-va")
    parser.add_argument("--drafts", type=Path, required=True, help="draft root written by the scraper")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    for pack in args.packs:
        curated_path = SOURCE_PACK_ROOT / pack / "manifest.json"
        draft_path = args.drafts / pack / "manifest.json"
        original = curated_path.read_text(encoding="utf-8")
        curated = json.loads(original)
        report = refresh(curated, json.loads(draft_path.read_text(encoding="utf-8")))
        print(
            f"{pack}: refreshed {report['refreshed']}, text changed {len(report['text_changed'])}, "
            f"added {len(report['added'])}, kept unscraped {len(report['kept_unscraped'])}"
        )
        for key in ("added", "kept_unscraped"):
            for source_id in report[key]:
                print(f"  {key}: {source_id}")
        if not args.dry_run:
            _write_like(curated_path, original, curated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
