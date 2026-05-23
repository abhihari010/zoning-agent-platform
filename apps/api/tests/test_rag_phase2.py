from __future__ import annotations

from app.ingestion import build_source_chunks
from app.models import SourceRegistryEntry
from app.rag.vector_store import ChromaVectorStore


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


def _where_matches(metadata: dict, where: dict) -> bool:
    if "$and" in where:
        return all(_where_matches(metadata, item) for item in where["$and"])
    for key, condition in where.items():
        if "$eq" in condition and metadata.get(key) != condition["$eq"]:
            return False
    return True
