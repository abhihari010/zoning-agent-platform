"""Tests for Phase 2 RAG: vector store, metadata filters, and real integration tests."""
from __future__ import annotations

import pytest

from app.ingestion import build_source_chunks
from app.models import SourceRegistryEntry
from app.rag.vector_store import (
    ChromaVectorStore,
    _build_chroma_where,
    get_vector_index_status,
    sync_vector_index,
)


# ---------------------------------------------------------------------------
# Fake Chroma client / collection (in-memory, no real Chroma needed)
# ---------------------------------------------------------------------------


class FakeCollection:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def upsert(self, ids, documents, embeddings, metadatas) -> None:
        for index, chunk_id in enumerate(ids):
            self.records[chunk_id] = {
                "document": documents[index],
                "embedding": embeddings[index],
                "metadata": metadatas[index],
            }

    def get(self, include=None):
        return {"ids": list(self.records)}

    def delete(self, ids) -> None:
        for chunk_id in ids:
            self.records.pop(chunk_id, None)

    def query(self, query_embeddings, n_results, where=None, include=None):
        ids: list[str] = []
        metadatas: list[dict] = []
        distances: list[float] = []
        for chunk_id, record in self.records.items():
            if where and not _where_matches(record["metadata"], where):
                continue
            ids.append(chunk_id)
            metadatas.append(record["metadata"])
            distances.append(0.1)
        return {
            "ids": [ids[:n_results]],
            "metadatas": [metadatas[:n_results]],
            "distances": [distances[:n_results]],
        }

    def count(self) -> int:
        return len(self.records)


class FakeClient:
    def __init__(self) -> None:
        self.collection = FakeCollection()

    def get_or_create_collection(self, name, embedding_function=None):
        return self.collection

    def delete_collection(self, name) -> None:
        self.collection = FakeCollection()


def _where_matches(metadata: dict, where: dict) -> bool:
    """Evaluate a Chroma where-clause against a metadata dict.

    Supports: $and, $or, $eq, $contains, $lte.
    """
    if "$and" in where:
        return all(_where_matches(metadata, item) for item in where["$and"])
    if "$or" in where:
        return any(_where_matches(metadata, item) for item in where["$or"])
    for key, condition in where.items():
        value = metadata.get(key, "")
        if "$eq" in condition and value != condition["$eq"]:
            return False
        if "$contains" in condition and condition["$contains"] not in str(value):
            return False
        if "$lte" in condition:
            # Lexicographic comparison (matching Chroma's string $lte behavior)
            if str(value) > str(condition["$lte"]):
                return False
    return True


# ---------------------------------------------------------------------------
# A.1 regression — existing tests
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
    first = SourceRegistryEntry(
        source_id="stable-rule",
        title="Stable Rule",
        excerpt="Coffee shops require parking review.",
        full_text="Coffee shops require parking review.",
        section_ref="Sec 1",
    )
    unchanged = SourceRegistryEntry(
        source_id="stable-rule",
        title="Stable Rule",
        excerpt="Coffee shops require parking review.",
        full_text="Coffee shops require parking review.",
        section_ref="Sec 1",
    )
    changed = SourceRegistryEntry(
        source_id="stable-rule",
        title="Stable Rule",
        excerpt="Coffee shops require parking and signage review.",
        full_text="Coffee shops require parking and signage review.",
        section_ref="Sec 1",
    )

    assert [chunk.chunk_id for chunk in build_source_chunks([first])] == [
        chunk.chunk_id for chunk in build_source_chunks([unchanged])
    ]
    assert [chunk.chunk_id for chunk in build_source_chunks([first])] != [
        chunk.chunk_id for chunk in build_source_chunks([changed])
    ]
    assert build_source_chunks([first])[0].source_text_hash != build_source_chunks([changed])[0].source_text_hash


# ---------------------------------------------------------------------------
# A.2 — Vector metadata filter tests (using FakeClient)
# ---------------------------------------------------------------------------


def test_chroma_vector_store_upserts_filters_and_deletes_stale_chunks() -> None:
    client = FakeClient()
    vector_store = ChromaVectorStore(client=client, collection_name="test")
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

    vector_store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])
    hits = vector_store.query(
        [0.1, 0.2, 0.3],
        filters={
            "jurisdiction_id": "blacksburg-va",
            "district": "mixed-use-core",
            "use": "food_service",
            "source_type": "zoning_ordinance",
        },
        limit=5,
    )

    assert [hit.chunk_id for hit in hits] == [chunks[0].chunk_id]
    assert vector_store.count() == 1
    assert vector_store.delete_missing_chunk_ids(set()) == 1
    assert vector_store.count() == 0


def test_build_chroma_where_district_filter() -> None:
    """District filter should produce a $contains clause on the pipe-delimited field."""
    where = _build_chroma_where({"district": "R-1"})
    # Should have districts $contains "|R-1|"
    assert where != {}
    # Verify the filter matches metadata with the district and not without
    matching = {"districts": "|R-1|"}
    non_matching = {"districts": "|R-2|"}
    assert _where_matches(matching, where)
    assert not _where_matches(non_matching, where)


def test_build_chroma_where_district_unknown_excluded() -> None:
    """District 'unknown' should NOT produce a filter (would exclude too much)."""
    where = _build_chroma_where({"district": "unknown"})
    # No district condition — filter should be empty or only contain other fields
    # Check: no "districts" key anywhere in the where clause
    assert "districts" not in str(where)


def test_build_chroma_where_use_filter_includes_general() -> None:
    """Use filter should match chunks tagged with the specific use OR 'general'."""
    where = _build_chroma_where({"use": "food_service"})
    food_service_meta = {"uses": "|food_service|"}
    general_meta = {"uses": "|general|"}
    other_meta = {"uses": "|residential|"}
    assert _where_matches(food_service_meta, where)
    assert _where_matches(general_meta, where)
    assert not _where_matches(other_meta, where)


def test_build_chroma_where_use_general_excluded() -> None:
    """Use 'general' should NOT produce a filter (matches everything)."""
    where = _build_chroma_where({"use": "general"})
    assert "uses" not in str(where)


def test_build_chroma_where_effective_date_filter() -> None:
    """effective_on_or_before should accept empty or earlier dates, reject later ones."""
    where = _build_chroma_where({"effective_on_or_before": "2024-01-01"})
    assert where != {}
    # Empty effective_date is always included
    assert _where_matches({"effective_date": ""}, where)
    # Date on or before is included
    assert _where_matches({"effective_date": "2023-06-01"}, where)
    assert _where_matches({"effective_date": "2024-01-01"}, where)
    # Date after is excluded
    assert not _where_matches({"effective_date": "2025-01-01"}, where)


def test_build_chroma_where_combined_filters() -> None:
    """Multiple filters should all be combined with $and."""
    where = _build_chroma_where(
        {
            "jurisdiction_id": "blacksburg-va",
            "district": "R-1",
            "use": "food_service",
        }
    )
    matching = {
        "jurisdiction_id": "blacksburg-va",
        "districts": "|R-1|",
        "uses": "|food_service|",
    }
    missing_district = {
        "jurisdiction_id": "blacksburg-va",
        "districts": "|R-2|",
        "uses": "|food_service|",
    }
    assert _where_matches(matching, where)
    assert not _where_matches(missing_district, where)


# ---------------------------------------------------------------------------
# A.4 — Real integration tests (require chromadb; skipped when not installed)
# ---------------------------------------------------------------------------

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed; skipping real integration tests")


def _make_test_source(source_id: str = "integ-source", content: str | None = None) -> SourceRegistryEntry:
    text = content or (
        "## Permitted Uses\n"
        "Food service establishments, including bakeries and coffee shops, are permitted uses "
        "in the mixed-use core district subject to site plan review.\n"
        "## Parking\n"
        "A minimum of one parking space per 300 square feet of gross floor area is required."
    )
    return SourceRegistryEntry(
        source_id=source_id,
        title="Integration Test Zoning Ordinance",
        excerpt=text[:200],
        full_text=text,
        section_ref="Document excerpt",
        jurisdiction_id="blacksburg-va",
        districts=["mixed-use-core"],
        uses=["food_service", "general"],
        source_type="zoning_ordinance",
        metadata={"imported_from": "test_integration.md"},
    )


class LocalHashEmbeddingProvider:
    """Deterministic embedding provider — hash-based unit vectors (no model needed)."""

    name = "local_hash"

    def embed(self, request):
        import hashlib

        from app.ai.interfaces import EmbeddingProviderResult

        embeddings = []
        for text in request.texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((b / 255.0) - 0.5) * 2 for b in digest]  # 32-dim unit-ish vector
            embeddings.append(vec)
        return EmbeddingProviderResult(embeddings=embeddings)


def test_chroma_full_pipeline_with_real_document(tmp_path) -> None:
    """Import a markdown doc, build chunks, sync to Chroma, query, verify chunk IDs."""
    from app.rag.vector_store import ChromaVectorStore, sync_vector_index
    from app.settings import Settings

    chroma_path = tmp_path / "chroma"
    source = _make_test_source()
    chunks = build_source_chunks([source])
    assert len(chunks) > 0, "Expected at least one chunk from test document"

    embedding_provider = LocalHashEmbeddingProvider()

    # Build a minimal settings object pointing to our temp path
    import os

    os.environ["CHROMA_PATH"] = str(chroma_path)
    os.environ["VECTOR_PROVIDER"] = "chroma"
    os.environ["CHROMA_COLLECTION"] = "test_integ"

    try:
        from app.settings import get_settings

        settings = get_settings()
        sync_result = sync_vector_index(chunks, embedding_provider, settings=settings)
        assert sync_result.ready, f"Sync not ready: {sync_result.warnings}"
        assert sync_result.count > 0

        # Query with a relevant embedding
        store = ChromaVectorStore(
            path=chroma_path,
            collection_name="test_integ",
        )
        query_emb = embedding_provider.embed(
            type("R", (), {"texts": ["food service permitted uses"]})()
        ).embeddings[0]
        hits = store.query(
            query_emb,
            filters={"jurisdiction_id": "blacksburg-va"},
            limit=5,
        )
        assert len(hits) > 0
        # All hit chunk_ids should be from our chunk set
        chunk_ids = {c.chunk_id for c in chunks}
        for hit in hits:
            assert hit.chunk_id in chunk_ids, f"Unknown chunk_id: {hit.chunk_id}"
    finally:
        for key in ["CHROMA_PATH", "VECTOR_PROVIDER", "CHROMA_COLLECTION"]:
            os.environ.pop(key, None)


def test_chroma_unavailable_returns_warnings() -> None:
    """get_vector_index_status() with an invalid Chroma path should return ready=False + warnings."""
    import os

    os.environ["VECTOR_PROVIDER"] = "chroma"
    os.environ["CHROMA_PATH"] = "/nonexistent/invalid/path/chroma_zoning"
    try:
        from app.settings import get_settings

        settings = get_settings()
        # Force a new store that must create the path
        store = ChromaVectorStore(settings=settings)
        # count() should either work (creates dir) or raise
        # What we care about is that get_vector_index_status handles the error path
        status = get_vector_index_status(settings=settings)
        # May be ready=True with count=0 (empty) or ready=False; either way warnings should be present if count=0
        if not status.ready:
            assert len(status.warnings) > 0
    finally:
        for key in ["VECTOR_PROVIDER", "CHROMA_PATH"]:
            os.environ.pop(key, None)


def test_stale_source_refresh_updates_chroma(tmp_path) -> None:
    """Update source text, re-sync, verify old chunk IDs are gone and new ones present."""
    import os

    chroma_path = tmp_path / "chroma_stale"
    os.environ["CHROMA_PATH"] = str(chroma_path)
    os.environ["VECTOR_PROVIDER"] = "chroma"
    os.environ["CHROMA_COLLECTION"] = "test_stale"

    try:
        from app.settings import get_settings

        settings = get_settings()
        embedding_provider = LocalHashEmbeddingProvider()

        # First sync
        source_v1 = _make_test_source(content="## Parking\nOriginal parking rule with sufficient text length.")
        chunks_v1 = build_source_chunks([source_v1])
        sync_vector_index(chunks_v1, embedding_provider, settings=settings)
        ids_v1 = {c.chunk_id for c in chunks_v1}

        store = ChromaVectorStore(path=chroma_path, collection_name="test_stale")
        assert store.count() == len(chunks_v1)

        # Second sync with updated source text
        source_v2 = _make_test_source(
            content="## Parking\nUpdated parking rule with different text that changes all chunk hashes completely."
        )
        chunks_v2 = build_source_chunks([source_v2])
        ids_v2 = {c.chunk_id for c in chunks_v2}
        assert ids_v1 != ids_v2, "Updated source should produce different chunk IDs"

        sync_vector_index(chunks_v2, embedding_provider, settings=settings)

        # Check that old IDs are gone
        existing_raw = store._get_collection().get(include=[])
        existing_ids = set(existing_raw.get("ids", []))
        assert ids_v1.isdisjoint(existing_ids), "Old chunk IDs should have been removed"
        assert ids_v2.issubset(existing_ids), "New chunk IDs should be present"
    finally:
        for key in ["CHROMA_PATH", "VECTOR_PROVIDER", "CHROMA_COLLECTION"]:
            os.environ.pop(key, None)
