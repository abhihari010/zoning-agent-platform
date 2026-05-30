"""Build a schema-valid ``source-pack/v1`` manifest from SectionRecords.

One :class:`SectionRecord` becomes one manifest source.  This is deliberate:
``apps/api/app/ingestion.build_source_chunks`` only does section-aware splitting
for ``.md`` imports; for source-pack sources it runs plain ``_chunk_text`` over
the whole ``full_text``.  By emitting one source per ordinance section we keep
each source's ``section_ref`` and ``url`` accurate and the resulting chunks
coherent — exactly what legal citations require.

The jurisdiction block reuses the skeleton from
``scripts/discover_jurisdiction_sources.build_draft_manifest`` so FIPS/contact
fields stay consistent with the rest of the pipeline; the scraper fills in the
official URLs, coverage status, and the real sources.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .fetchers.base import SectionRecord

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXCERPT_MAX = 500
_FULL_TEXT_MAX = 250_000  # matches SourceRegistryEntry.full_text max_length


def _load_discover_module():
    """Import ``scripts/discover_jurisdiction_sources.py`` without requiring the
    repo to be installed as a package."""
    path = _REPO_ROOT / "scripts" / "discover_jurisdiction_sources.py"
    spec = importlib.util.spec_from_file_location("_ws1_discover_sources", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _excerpt(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized[:_EXCERPT_MAX]


def _make_source_id(jurisdiction_id: str, record: SectionRecord, used: set[str]) -> str:
    ref_slug = slugify(record.section_ref) or slugify(record.heading) or "section"
    base = f"{jurisdiction_id}-{ref_slug}"
    source_id = base
    counter = 2
    while source_id in used:
        source_id = f"{base}-{counter}"
        counter += 1
    used.add(source_id)
    return source_id


def section_to_source(
    record: SectionRecord,
    *,
    jurisdiction_id: str,
    used_ids: set[str],
    retrieved_at: str,
    fallback_effective_date: str,
) -> dict[str, Any]:
    """Convert one SectionRecord into a manifest source dict."""
    full_text = " ".join(record.text.split())[:_FULL_TEXT_MAX]
    effective = record.effective_date or fallback_effective_date
    metadata: dict[str, Any] = {
        "verification_status": "scraped",
        "scraper": record.metadata.get("scraper", "ws1"),
        **record.metadata,
    }
    if record.breadcrumb:
        metadata["breadcrumb"] = record.breadcrumb
    if not record.effective_date:
        metadata["effective_date_source"] = "retrieval_date"

    return {
        "source_id": _make_source_id(jurisdiction_id, record, used_ids),
        "title": record.heading.strip() or record.section_ref,
        "excerpt": _excerpt(record.text),
        "full_text": full_text,
        "section_ref": record.section_ref.strip(),
        "jurisdiction_id": jurisdiction_id,
        "url": record.url,
        "effective_date": effective,
        "retrieved_at": retrieved_at,
        "districts": ["unknown"],
        "uses": ["general"],
        "source_type": record.source_type,
        "metadata": metadata,
    }


def build_manifest(
    *,
    city: str,
    state: str,
    records: list[SectionRecord],
    jurisdiction_type: str = "municipality",
    county: str | None = None,
    jurisdiction_id: str | None = None,
    official_source_urls: list[str] | None = None,
    planning_contact: dict[str, str] | None = None,
    zoning_map_url: str | None = None,
    coverage_status: str = "source_indexed",
    effective_date: str | None = None,
    provenance: dict[str, Any] | None = None,
    base_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a complete ``source-pack/v1`` manifest dict.

    ``records`` must be non-empty; the schema requires a non-empty ``sources``
    array.  ``coverage_status`` defaults to ``source_indexed`` (promotion to
    ``public_supported`` happens later after QA).
    """
    if not records:
        raise ValueError("Cannot build a manifest with zero sections.")

    discover = _load_discover_module()
    skeleton = base_manifest or discover.build_draft_manifest(
        jurisdiction_name=city,
        state=state,
        jurisdiction_type=jurisdiction_type,
        county=county,
        jurisdiction_id=jurisdiction_id,
    )

    jurisdiction = dict(skeleton["jurisdiction"])
    jurisdiction["coverage_status"] = coverage_status

    urls = list(official_source_urls or jurisdiction.get("official_source_urls") or [])
    if not urls and provenance and provenance.get("source_home_url"):
        urls = [provenance["source_home_url"]]
    if not urls and records:
        urls = [records[0].url]
    jurisdiction["official_source_urls"] = urls

    if zoning_map_url:
        jurisdiction["zoning_map_url"] = zoning_map_url
    if planning_contact:
        jurisdiction["planning_contact"] = planning_contact
    elif not _contact_has_value(jurisdiction.get("planning_contact")):
        # Validator needs url/email/phone; fall back to the official source URL.
        jurisdiction["planning_contact"] = {"url": urls[0] if urls else records[0].url}

    resolved_jurisdiction_id = str(jurisdiction["jurisdiction_id"])
    retrieved_at = datetime.now(timezone.utc).date().isoformat()
    fallback_effective = effective_date or retrieved_at

    used_ids: set[str] = set()
    sources = [
        section_to_source(
            record,
            jurisdiction_id=resolved_jurisdiction_id,
            used_ids=used_ids,
            retrieved_at=retrieved_at,
            fallback_effective_date=fallback_effective,
        )
        for record in records
    ]

    notes = (
        f"WS1 scraped source pack generated on {date.today().isoformat()} "
        f"({len(sources)} ordinance section(s)). Coverage status is "
        f"'{coverage_status}'; promote to public_supported only after district "
        "mapping and golden QA pass."
    )
    if provenance:
        fetcher = provenance.get("fetcher") or (provenance.get("provenance") or {}).get("fetcher")
        if fetcher:
            notes += f" Fetcher: {fetcher}."

    return {
        "schema_version": "source-pack/v1",
        "jurisdiction": jurisdiction,
        "verification_notes": notes,
        "sources": sources,
        "scrape_provenance": provenance or {},
    }


def _contact_has_value(contact: object) -> bool:
    if not isinstance(contact, dict):
        return False
    return any(
        str(contact.get(key) or "").strip() for key in ("url", "email", "phone")
    )
