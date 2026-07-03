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
        self.payload_indexes: list[tuple[str, str, object]] = []

    def get_collections(self) -> object:
        return type("R", (), {"collections": list(self._collections)})()

    def get_collection(self, collection_name: str) -> object:
        if collection_name not in self._collections:
            raise Exception(f"Collection '{collection_name}' does not exist")
        return self._collections[collection_name]

    def create_collection(self, collection_name: str, vectors_config: object) -> None:
        self._collections[collection_name] = {"vectors_config": vectors_config, "points": {}}

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: object,
        wait: bool = True,
    ) -> None:
        self._ensure_col(collection_name)
        self.payload_indexes.append((collection_name, field_name, field_schema))

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

    def set_payload(
        self,
        collection_name: str,
        payload: dict,
        points: list,
        wait: bool = True,
    ) -> None:
        col = self._ensure_col(collection_name)
        for pid in points:
            col["points"][pid]["payload"].update(payload)

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: object | None = None,
        limit: int = 10,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> object:
        col = self._ensure_col(collection_name)
        results = []
        for pid, data in col["points"].items():
            vec = data["vector"]
            score = sum(a * b for a, b in zip(query, vec))
            payload = data["payload"] if with_payload else {}
            results.append(type("Hit", (), {"id": pid, "score": score, "payload": payload})())
        results.sort(key=lambda x: x.score, reverse=True)
        return type("QueryResponse", (), {"points": results[:limit]})()

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


def test_qdrant_store_creates_payload_indexes_for_filtered_fields() -> None:
    fake_client = FakeQdrantClient()
    store = _make_store(fake_client)
    source = SourceRegistryEntry(
        source_id="coffee-rule",
        title="Coffee Rule",
        excerpt="Coffee shops are reviewed as food service uses.",
        section_ref="Sec 3",
        jurisdiction_id="blacksburg-va",
        districts=["mixed-use-core"],
        uses=["food-service"],
        source_type="zoning_ordinance",
    )
    chunks = build_source_chunks([source])

    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])
    store.query(
        [0.1, 0.2, 0.3],
        filters={
            "jurisdiction_id": "blacksburg-va",
            "district": "mixed-use-core",
            "use": "food-service",
        },
    )

    indexed_fields = {field_name for _, field_name, _ in fake_client.payload_indexes}
    assert {
        "jurisdiction_id",
        "state",
        "source_id",
        "source_type",
        "source_version",
        "districts",
        "uses",
    }.issubset(indexed_fields)


def test_qdrant_store_updates_payload_without_reembedding() -> None:
    fake_client = FakeQdrantClient()
    store = _make_store(fake_client)
    source = SourceRegistryEntry(
        source_id="coffee-rule",
        title="Coffee Rule",
        excerpt="Coffee shops are reviewed as food service uses.",
        section_ref="Sec 3",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
        source_type="zoning_ordinance",
    )
    chunks = build_source_chunks([source])
    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])

    updated, skipped = store.update_chunk_payloads(
        {
            chunks[0].chunk_id: {
                "districts": ["unknown", "commercial-employment"],
                "uses": ["food-service", "general"],
            }
        }
    )
    hits = store.query(
        [0.1, 0.2, 0.3],
        filters={"district": "commercial-employment", "use": "food-service"},
    )

    assert (updated, skipped) == (1, 0)
    assert hits[0].metadata["districts"] == ["unknown", "commercial-employment"]
    assert hits[0].metadata["uses"] == ["food-service", "general"]


def test_qdrant_store_skips_payload_for_missing_points() -> None:
    """A chunk_id not yet embedded in Qdrant is skipped, not fatal.

    Guards the regression where a single missing point raised 404 and aborted the
    whole payload retag mid-way (leaving Qdrant half-retagged) when the SQL corpus
    was ahead of the vector index.
    """
    fake_client = FakeQdrantClient()
    store = _make_store(fake_client)
    source = SourceRegistryEntry(
        source_id="present-rule",
        title="Present Rule",
        excerpt="Present chunk carries enough text to be chunked into the index.",
        section_ref="Sec 4",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
        source_type="zoning_ordinance",
    )
    chunks = build_source_chunks([source])
    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])

    updated, skipped = store.update_chunk_payloads(
        {
            chunks[0].chunk_id: {"districts": ["unknown", "commercial-employment"]},
            "never-embedded-chunk-id": {"districts": ["residential"]},
        }
    )

    assert (updated, skipped) == (1, 1)
    hits = store.query([0.1, 0.2, 0.3], filters={"district": "commercial-employment"})
    assert hits[0].metadata["districts"] == ["unknown", "commercial-employment"]


def test_qdrant_store_surfaces_query_errors() -> None:
    class BrokenQueryClient(FakeQdrantClient):
        def query_points(self, *args, **kwargs) -> object:
            raise ValueError("vector size mismatch")

    store = _make_store(BrokenQueryClient())

    with pytest.raises(RuntimeError, match="Qdrant query failed: vector size mismatch"):
        store.query([0.1, 0.2, 0.3], filters={"jurisdiction_id": "blacksburg-va"})


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


def test_qdrant_unknown_district_chunk_surfaces_for_concrete_district_query() -> None:
    # Reproduces the Blacksburg bug: the scraped-ordinance corpus is tagged
    # districts=["unknown"] (unclassified), while only a handful of hand-tagged
    # seeds carry a concrete district. A query that resolves a concrete district
    # (mixed-use-core) must still see the unknown-tagged ordinance chunk, and must
    # NOT see a chunk tagged with a *different* concrete district.
    store = _make_store()
    sources = [
        SourceRegistryEntry(
            source_id="blacksburg-permitted-uses-3061",
            title="Sec. 3061 - Permitted uses",
            excerpt="Restaurants and cafes are permitted uses subject to site standards.",
            section_ref="Sec. 3061",
            jurisdiction_id="blacksburg-va",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
        ),
        SourceRegistryEntry(
            source_id="blacksburg-residential-only-rule",
            title="Residential-only rule",
            excerpt="This standard applies only in the residential low density district.",
            section_ref="Sec. 9000",
            jurisdiction_id="blacksburg-va",
            districts=["residential-low-density"],
            uses=["general"],
            source_type="zoning_ordinance",
        ),
    ]
    chunks = build_source_chunks(sources)
    store.upsert_chunks(chunks, [[0.1, 0.2, 0.3] for _ in chunks])

    hits = store.query(
        [0.1, 0.2, 0.3],
        filters={
            "jurisdiction_id": "blacksburg-va",
            "district": "mixed-use-core",
            "use": "food-service",
        },
        limit=10,
    )
    returned = {hit.metadata["source_id"] for hit in hits}
    assert "blacksburg-permitted-uses-3061" in returned
    assert "blacksburg-residential-only-rule" not in returned


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


def test_metadata_matches_district_unknown_wildcard() -> None:
    # A chunk tagged districts=["unknown"] is unclassified-by-district and must
    # match ANY queried district, mirroring the uses=["general"] wildcard.
    # Without this, the unclassified scraped-ordinance corpus is invisible to any
    # district-specific query and only hand-tagged seeds survive.
    assert _metadata_matches({"districts": ["unknown"]}, {"district": "mixed-use-core"})
    # A chunk tagged with a *different* concrete district is still excluded.
    assert not _metadata_matches({"districts": ["R-2"]}, {"district": "R-1"})


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


def test_build_qdrant_filter_district_produces_should_with_unknown() -> None:
    # A concrete query district must match either the tagged district OR the
    # "unknown" wildcard, so unclassified scraped-ordinance chunks are not
    # filtered out of the candidate set (symmetric with the use/"general" clause).
    result = _build_qdrant_filter({"district": "mixed-use-core"})
    assert result is not None
    rendered = str(result)
    assert "mixed-use-core" in rendered
    assert "unknown" in rendered


# ---------------------------------------------------------------------------
# A.5 — sync_vector_index batching and resumability tests
# ---------------------------------------------------------------------------


from app.ai.interfaces import EmbeddingProviderResult
from app.settings import Settings


def _make_settings(batch_size: int = 2) -> Settings:
    """Return a minimal in-memory Settings with qdrant vector provider and a small batch size."""
    import dataclasses
    from app.settings import get_settings

    base = get_settings()
    return dataclasses.replace(
        base,
        vector_provider="qdrant",  # type: ignore[arg-type]
        qdrant_url="http://fake-qdrant:6333",
        qdrant_collection="test",
        vector_reindex_batch_size=batch_size,
    )


def _make_chunks(n: int) -> list:
    """Return n distinct SourceChunks using build_source_chunks."""
    sources = [
        SourceRegistryEntry(
            source_id=f"rule-{i}",
            title=f"Rule {i}",
            excerpt=f"Zoning rule number {i} for testing batch reindex.",
            section_ref=f"Sec {i}",
            jurisdiction_id="blacksburg-va",
            districts=["mixed-use-core"],
            uses=["general"],
        )
        for i in range(n)
    ]
    # build_source_chunks may produce >n chunks for multi-chunk sources;
    # take the first n so the count is predictable.
    all_chunks = build_source_chunks(sources)
    return all_chunks[:n]


class FakeEmbeddingProvider:
    """Embedding provider that records batch call arguments and returns fixed vectors."""

    name = "fake"

    def __init__(self, dims: int = 3, fail_on_batch: int | None = None) -> None:
        self._dims = dims
        self._fail_on_batch = fail_on_batch
        self.call_count = 0
        self.batch_sizes: list[int] = []

    def embed(self, request: "EmbeddingProviderRequest") -> EmbeddingProviderResult:  # type: ignore[name-defined]
        self.call_count += 1
        self.batch_sizes.append(len(request.texts))
        if self._fail_on_batch is not None and self.call_count == self._fail_on_batch:
            raise RuntimeError(f"Simulated embedding failure on batch {self.call_count}")
        return EmbeddingProviderResult(
            embeddings=[[0.1, 0.2, 0.3][: self._dims] for _ in request.texts]
        )


def _make_sync_store(fake_client: FakeQdrantClient, settings: Settings) -> QdrantVectorStore:
    """Return a QdrantVectorStore backed by fake_client, bound to the given settings."""
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        client=fake_client,
        settings=settings,
    )
    return store


def test_sync_vector_index_multi_batch_commits_all_chunks() -> None:
    """All chunks are committed and upsert is called more than once when chunks > batch_size."""
    fake_client = FakeQdrantClient()
    settings = _make_settings(batch_size=2)
    chunks = _make_chunks(5)  # 5 chunks, batch_size=2 → 3 batches

    embed_provider = FakeEmbeddingProvider(dims=3)

    # Monkey-patch sync_vector_index to inject our fake client into the store
    # by patching QdrantVectorStore.__init__ to set _client.
    original_init = QdrantVectorStore.__init__

    def patched_init(self, **kwargs):
        original_init(self, **kwargs)
        self._client = fake_client

    QdrantVectorStore.__init__ = patched_init  # type: ignore[method-assign]
    try:
        result = sync_vector_index(chunks, embed_provider, settings=settings)
    finally:
        QdrantVectorStore.__init__ = original_init  # type: ignore[method-assign]

    assert result.count == len(chunks), f"Expected {len(chunks)}, got {result.count}"
    assert result.ready is True
    assert embed_provider.call_count > 1, "Expected multiple embed calls (batching)"
    assert all(bs <= 2 for bs in embed_provider.batch_sizes), "Each batch must be <= batch_size"
    assert not result.warnings


def test_sync_vector_index_partial_failure_commits_prior_batches() -> None:
    """When batch N fails, batches 0..N-1 are durably committed; count > 0; warning present."""
    fake_client = FakeQdrantClient()
    settings = _make_settings(batch_size=2)
    chunks = _make_chunks(6)  # 6 chunks, batch_size=2 → 3 batches; fail on batch 2

    # fail_on_batch=2 → first batch (call 1) succeeds, second (call 2) raises
    embed_provider = FakeEmbeddingProvider(dims=3, fail_on_batch=2)

    original_init = QdrantVectorStore.__init__

    def patched_init(self, **kwargs):
        original_init(self, **kwargs)
        self._client = fake_client

    QdrantVectorStore.__init__ = patched_init  # type: ignore[method-assign]
    try:
        result = sync_vector_index(chunks, embed_provider, settings=settings)
    finally:
        QdrantVectorStore.__init__ = original_init  # type: ignore[method-assign]

    # First batch (2 chunks) committed; result must reflect committed progress.
    assert result.count > 0, "Prior batches should be committed even when a later batch fails"
    assert result.count < len(chunks), "Not all chunks should be committed (later batch failed)"
    assert result.ready is False
    assert any("Embedding failed" in w or "already committed" in w for w in result.warnings)


def test_sync_vector_index_resume_after_partial_failure() -> None:
    """Re-running after a partial failure skips already-present ids and finishes the rest."""
    fake_client = FakeQdrantClient()
    settings = _make_settings(batch_size=2)
    chunks = _make_chunks(6)  # 3 batches of 2; first run fails on batch 2

    failing_embed = FakeEmbeddingProvider(dims=3, fail_on_batch=2)

    original_init = QdrantVectorStore.__init__

    def patched_init(self, **kwargs):
        original_init(self, **kwargs)
        self._client = fake_client

    QdrantVectorStore.__init__ = patched_init  # type: ignore[method-assign]
    try:
        first_result = sync_vector_index(chunks, failing_embed, settings=settings)
        committed_after_first_run = first_result.count

        # Second run with a working provider — should skip already-indexed ids.
        working_embed = FakeEmbeddingProvider(dims=3)
        second_result = sync_vector_index(chunks, working_embed, settings=settings)
    finally:
        QdrantVectorStore.__init__ = original_init  # type: ignore[method-assign]

    assert committed_after_first_run > 0, "First run must commit at least one batch"
    assert second_result.count == len(chunks), (
        f"Second run should complete the index: expected {len(chunks)}, got {second_result.count}"
    )
    assert second_result.ready is True
    # The second run must embed fewer chunks than the total (already-present ones are skipped).
    total_embedded_second_run = sum(working_embed.batch_sizes)
    assert total_embedded_second_run < len(chunks), (
        "Second run should skip already-committed chunks"
    )
