"""Tests for the RAG vector store layer (Qdrant backend)."""
from __future__ import annotations

import pytest

from app.ingestion import build_source_chunks
from app.models import SourceRegistryEntry
from app.rag.vector_store import (
    QdrantVectorStore,
    _build_qdrant_filter,
    _metadata_matches,
    get_vector_index_status,
    sync_vector_index,
)

qdrant_client = pytest.importorskip("qdrant_client", reason="qdrant-client not installed")


# ---------------------------------------------------------------------------
# Fake Qdrant client (in-memory, no real Qdrant needed)
# ---------------------------------------------------------------------------


class FakeQdrantClient:
    def __init__(self) -> None:
        self._collections: dict[str, dict] = {}

    def get_collections(self) -> object:
        return type("R", (), {"collections": list(self._collections)})()

    def get_collection(self, collection_name: str) -> object:
        if collection_name not in self._collections:
            raise Exception(f"Collection '{collection_name}' does not exist")
        return self._collections[collection_name]

    def create_collection(self, collection_name: str, vectors_config: object) -> None:
        self._collections[collection_name] = {"vectors_config": vectors_config, "points": {}}

    def delete_collection(self, collection_name: str) -> None:
        self._collections.pop(collection_name, None)

    def upsert(self, collection_name: str, points: list, wait: bool = True) -> None:
        col = self._ensure_col(collection_name)
        for point in points:
            col["points"][point.id] = {
                "vector": point.vector,
                "payload": point.payload or {},
            }

    def scroll(
        self,
        collection_name: str,
        with_payload: bool | list[str] = True,
        with_vectors: bool = False,
        limit: int = 10,
        offset: object | None = None,
    ) -> tuple[list, object | None]:
        col = self._ensure_col(collection_name)
        items = list(col["points"].items())
        if offset is not None:
            ids = [k for k, _ in items]
            try:
                start = ids.index(offset) + 1
                items = items[start:]
            except ValueError:
                items = []
        page, rest = items[:limit], items[limit:]

        def _payload(data: dict) -> dict:
            if with_payload is False:
                return {}
            if isinstance(with_payload, list):
                return {k: v for k, v in data["payload"].items() if k in with_payload}
            return data["payload"]

        records = [
            type("Record", (), {"id": pid, "payload": _payload(data)})()
            for pid, data in page
        ]
        next_offset = rest[0][0] if rest else None
        return records, next_offset

    def delete(self, collection_name: str, points_selector: object, wait: bool = True) -> None:
        col = self._ensure_col(collection_name)
        for pid in points_selector.points:
            col["points"].pop(pid, None)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        query_filter: object | None = None,
        limit: int = 10,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> list:
        col = self._ensure_col(collection_name)
        results = []
        for pid, data in col["points"].items():
            vec = data["vector"]
            score = sum(a * b for a, b in zip(query_vector, vec))
            payload = data["payload"] if with_payload else {}
            results.append(type("Hit", (), {"id": pid, "score": score, "payload": payload})())
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def count(self, collection_name: str, exact: bool = True) -> object:
        col = self._ensure_col(collection_name)
        return type("CountResult", (), {"count": len(col["points"])})()

    def _ensure_col(self, name: str) -> dict:
        if name not in self._collections:
            self._collections[name] = {"points": {}}
        return self._collections[name]


# ---------------------------------------------------------------------------
# A.1 — Chunk-building tests (no Qdrant dependency)
# ---------------------------------------------------------------------------


def test_full_text_chunks_preserve_body_beyond_excerpt() -> None:
    full_text = " ".join([f"parking clause {index}" for index in range(180)])
    source = SourceRegistryEntry(
        source_id="long-parking-rule",
        title="Long Parking Rule",
        excerpt=full_text[:500],
        full_text=full_text,
        section_ref="Sec 9",
        jurisdiction_id="blacksburg-va",
        districts=["mixed-use-core"],
        uses=["food_service"],
    )
    chunks = build_source_chunks([source])
    assert len(chunks) > 1
    assert any("parking clause 179" in chunk.chunk_text for chunk in chunks)
    assert all(chunk.source_version == source.source_version for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_stable_chunk_ids_change_only_when_source_text_changes() -> None:
    base = dict(
        source_id="stable-rule",
        title="Stable Rule",
        excerpt="Coffee shops require parking review.",
        full_text="Coffee shops require parking review.",
        section_ref="Sec 1",
    )
    changed = {**base, "excerpt": "Coffee shops require parking and signage review.", "full_text": "Coffee shops require parking and signage review."}

    first_ids = [c.chunk_id for c in build_source_chunks([SourceRegistryEntry(**base)])]
    unchanged_ids = [c.chunk_id for c in build_source_chunks([SourceRegistryEntry(**base)])]
    changed_ids = [c.chunk_id for c in build_source_chunks([SourceRegistryEntry(**changed)])]

    assert first_ids == unchanged_ids
    assert first_ids != changed_ids
    assert build_source_chunks([SourceRegistryEntry(**base)])[0].source_text_hash != build_source_chunks([SourceRegistryEntry(**changed)])[0].source_text_hash


# ---------------------------------------------------------------------------
# A.2 — QdrantVectorStore unit tests (FakeQdrantClient)
# ---------------------------------------------------------------------------


def _make_store(fake_client: FakeQdrantClient | None = None) -> QdrantVectorStore:
    store = QdrantVectorStore(url="http://localhost:6333", collection_name="test")
    store._client = fake_client or FakeQdrantClient()
    return store


def test_qdrant_store_upserts_queries_and_deletes() -> None:
    store = _make_store()
    source = SourceRegistryEntry(
        source_id="coffee-rule",
        title="Coffee Rule",
        excerpt="Coffee shops are reviewed as food service uses.",
        section_ref="Sec 3",
        jurisdiction_id="blacksburg-va",
        districts=["mixed-use-core"],
        uses=["food_service"],
        source_type="zoning_ordinance",
    )
    chunks = build_source_chunks([source])

    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])
    hits = store.query(
        [0.1, 0.2, 0.3],
        filters={
            "jurisdiction_id": "blacksburg-va",
            "district": "mixed-use-core",
            "use": "food_service",
        },
        limit=5,
    )

    assert len(hits) > 0
    assert hits[0].chunk_id == chunks[0].chunk_id
    assert store.count() == 1
    assert store.delete_missing_chunk_ids(set()) == 1
    assert store.count() == 0


def test_qdrant_jurisdiction_filter_prevents_cross_jurisdiction_hits() -> None:
    store = _make_store()
    sources = [
        SourceRegistryEntry(
            source_id="blacksburg-cafe-rule",
            title="Blacksburg Cafe Rule",
            excerpt="Cafe uses require zoning review in the mixed-use core district.",
            section_ref="Sec 1",
            jurisdiction_id="blacksburg-va",
            districts=["mixed-use-core"],
            uses=["food-service"],
        ),
        SourceRegistryEntry(
            source_id="roanoke-cafe-rule",
            title="Roanoke Cafe Rule",
            excerpt="Cafe uses require zoning review in the mixed-use core district.",
            section_ref="Sec 1",
            jurisdiction_id="roanoke-va",
            districts=["mixed-use-core"],
            uses=["food-service"],
        ),
    ]
    chunks = build_source_chunks(sources)
    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])

    hits = store.query(
        [0.1, 0.2, 0.3],
        filters={"jurisdiction_id": "roanoke-va", "district": "mixed-use-core"},
        limit=10,
    )
    assert {hit.metadata["source_id"] for hit in hits} == {"roanoke-cafe-rule"}


def test_qdrant_global_source_included_for_matching_state() -> None:
    store = _make_store()
    sources = [
        SourceRegistryEntry(
            source_id="va-food-permit-rule",
            title="Virginia Food Permit Rule",
            excerpt="Food service establishments in Virginia require health department permit review.",
            section_ref="Food permit",
            jurisdiction_id="*",
            districts=["unknown", "*"],
            uses=["food-service", "general"],
            source_type="health_code",
            metadata={"jurisdiction_scope": "global", "state": "VA", "applies_to_states": ["VA"]},
        ),
        SourceRegistryEntry(
            source_id="md-food-permit-rule",
            title="Maryland Food Permit Rule",
            excerpt="Food service establishments in Maryland require health department permit review.",
            section_ref="Food permit",
            jurisdiction_id="*",
            districts=["unknown", "*"],
            uses=["food-service", "general"],
            source_type="health_code",
            metadata={"jurisdiction_scope": "global", "state": "MD", "applies_to_states": ["MD"]},
        ),
    ]
    chunks = build_source_chunks(sources)
    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])

    hits = store.query(
        [0.1, 0.2, 0.3],
        filters={"jurisdiction_id": "roanoke-va", "use": "food-service"},
        limit=10,
    )
    assert {hit.metadata["source_id"] for hit in hits} == {"va-food-permit-rule"}


# ---------------------------------------------------------------------------
# A.3 — Metadata post-filter tests (no Qdrant client needed)
# ---------------------------------------------------------------------------


def test_metadata_matches_district_list() -> None:
    assert _metadata_matches({"districts": ["R-1", "mixed-use"]}, {"district": "R-1"})
    assert not _metadata_matches({"districts": ["R-2"]}, {"district": "R-1"})


def test_metadata_matches_use_general_wildcard() -> None:
    assert _metadata_matches({"uses": ["general"]}, {"use": "food_service"})
    assert _metadata_matches({"uses": ["food_service", "retail"]}, {"use": "food_service"})
    assert not _metadata_matches({"uses": ["retail"]}, {"use": "food_service"})


def test_metadata_matches_effective_date_filter() -> None:
    assert _metadata_matches({"effective_date": "2023-06-01"}, {"effective_on_or_before": "2024-01-01"})
    assert _metadata_matches({"effective_date": ""}, {"effective_on_or_before": "2024-01-01"})
    assert not _metadata_matches({"effective_date": "2025-01-01"}, {"effective_on_or_before": "2024-01-01"})


# ---------------------------------------------------------------------------
# A.4 — Filter structure tests (qdrant_client models required)
# ---------------------------------------------------------------------------


def test_build_qdrant_filter_district_unknown_excluded() -> None:
    result = _build_qdrant_filter({"district": "unknown"})
    assert "districts" not in str(result)


def test_build_qdrant_filter_use_general_excluded() -> None:
    result = _build_qdrant_filter({"use": "general"})
    assert "uses" not in str(result)


def test_build_qdrant_filter_empty_returns_none() -> None:
    assert _build_qdrant_filter({}) is None


def test_build_qdrant_filter_district_produces_condition() -> None:
    result = _build_qdrant_filter({"district": "R-1"})
    assert result is not None
    assert "R-1" in str(result)


def test_build_qdrant_filter_use_produces_should_clause() -> None:
    result = _build_qdrant_filter({"use": "food_service"})
    assert result is not None
    assert "food_service" in str(result)
    assert "general" in str(result)
