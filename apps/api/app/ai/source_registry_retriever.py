from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai.interfaces import RetrievalProviderRequest, RetrievalProviderResult
from app.models import SourceCitation, SourceRegistryEntry
from app.storage import SQLiteStore, store


SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "source_registry.json"


@lru_cache(maxsize=1)
def _load_seed_source_registry() -> list[dict[str, Any]]:
    if not SOURCE_REGISTRY_PATH.exists():
        return []

    with SOURCE_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def ensure_seed_sources(source_store: SQLiteStore = store) -> None:
    if source_store.get_source_count() > 0:
        return

    for source in _load_seed_source_registry():
        try:
            entry = SourceRegistryEntry.model_validate(source)
        except Exception:
            continue
        source_store.upsert_source(entry)


class SourceRegistryRetrievalProvider:
    name = "source_registry"

    def __init__(self, source_store: SQLiteStore = store) -> None:
        self.source_store = source_store

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        ensure_seed_sources(self.source_store)
        hits: list[SourceCitation] = []

        for source in self.source_store.list_sources():
            jurisdiction_ok = (
                not request.jurisdiction_id
                or not source.jurisdiction_id
                or source.jurisdiction_id == request.jurisdiction_id
                or source.jurisdiction_id == "*"
            )
            district_ok = (
                request.district in source.districts
                or "*" in source.districts
                or request.district == "unknown"
            )
            use_ok = request.inferred_use in source.uses or "general" in source.uses
            if not jurisdiction_ok or not district_ok or not use_ok:
                continue
            hits.append(
                SourceCitation(
                    source_id=source.source_id,
                    title=source.title,
                    excerpt=source.excerpt,
                    section_ref=source.section_ref,
                    url=source.url,
                    effective_date=source.effective_date,
                )
            )

        return RetrievalProviderResult(citations=hits[:5])
