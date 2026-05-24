from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.interfaces import EmbeddingProvider, EmbeddingProviderRequest
from app.models import SourceChunk
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class VectorQueryResult:
    chunk_id: str
    distance: float | None
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorIndexStatus:
    provider: str
    collection: str | None
    ready: bool
    count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VectorIndexSyncResult:
    provider: str
    collection: str | None
    ready: bool
    count: int
    warnings: list[str] = field(default_factory=list)


class ChromaVectorStore:
    def __init__(
        self,
        *,
        path: str | Path | None = None,
        collection_name: str | None = None,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self.path = Path(path) if path else resolved.chroma_path
        self.collection_name = collection_name or resolved.chroma_collection
        self._client = client
        self._collection: Any | None = None

    def is_available(self) -> bool:
        try:
            self._get_collection()
        except Exception:
            return False
        return True

    def upsert_chunks(self, chunks: list[SourceChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        if not chunks:
            return

        collection = self._get_collection()
        collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.chunk_text for chunk in chunks],
            embeddings=embeddings,
            metadatas=[_chunk_metadata(chunk) for chunk in chunks],
        )

    def delete_missing_chunk_ids(self, valid_chunk_ids: set[str]) -> int:
        collection = self._get_collection()
        existing = collection.get(include=[])
        existing_ids = existing.get("ids", []) if isinstance(existing, dict) else []
        stale_ids = [chunk_id for chunk_id in existing_ids if chunk_id not in valid_chunk_ids]
        if stale_ids:
            collection.delete(ids=stale_ids)
        return len(stale_ids)

    def query(
        self,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[VectorQueryResult]:
        if not query_embedding:
            return []

        filters = filters or {}
        where = _build_chroma_where(filters)
        collection = self._get_collection()
        response = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where or None,
            include=["metadatas", "distances"],
        )

        ids = _first_result_list(response.get("ids", []))
        distances = _first_result_list(response.get("distances", []))
        metadatas = _first_result_list(response.get("metadatas", []))

        results: list[VectorQueryResult] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            if not _metadata_matches(metadata, filters):
                continue
            distance = distances[index] if index < len(distances) else None
            score = 1.0 / (1.0 + float(distance)) if distance is not None else 0.0
            results.append(
                VectorQueryResult(
                    chunk_id=str(chunk_id),
                    distance=float(distance) if distance is not None else None,
                    score=score,
                    metadata=metadata,
                )
            )
        return results

    def reset_collection(self) -> None:
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None
        self._get_collection()

    def count(self) -> int:
        return int(self._get_collection().count())

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("ChromaDB is not installed. Install chromadb to use VECTOR_PROVIDER=chroma.") from exc

        self.path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.path))
        return self._client

    def _get_collection(self) -> Any:
        if self._collection is None:
            self._collection = self._get_client().get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
            )
        return self._collection


def get_vector_index_status(settings: Settings | None = None) -> VectorIndexStatus:
    resolved = settings or get_settings()
    if resolved.vector_provider == "none":
        return VectorIndexStatus(
            provider="none",
            collection=None,
            ready=False,
            count=0,
            warnings=["Vector index is disabled with VECTOR_PROVIDER=none."],
        )

    store = ChromaVectorStore(settings=resolved)
    try:
        count = store.count()
    except Exception as exc:
        return VectorIndexStatus(
            provider=resolved.vector_provider,
            collection=resolved.chroma_collection,
            ready=False,
            count=0,
            warnings=[str(exc)],
        )

    warnings = [] if count > 0 else ["Chroma vector collection is empty."]
    return VectorIndexStatus(
        provider=resolved.vector_provider,
        collection=resolved.chroma_collection,
        ready=count > 0,
        count=count,
        warnings=warnings,
    )


def sync_vector_index(
    chunks: list[SourceChunk],
    embedding_provider: EmbeddingProvider,
    settings: Settings | None = None,
) -> VectorIndexSyncResult:
    resolved = settings or get_settings()
    if resolved.vector_provider == "none":
        return VectorIndexSyncResult(
            provider="none",
            collection=None,
            ready=False,
            count=0,
            warnings=["Vector index skipped because VECTOR_PROVIDER=none."],
        )

    store = ChromaVectorStore(settings=resolved)
    try:
        if resolved.chroma_reset_on_reindex:
            store.reset_collection()
        embeddings = embedding_provider.embed(
            EmbeddingProviderRequest(texts=[chunk.chunk_text for chunk in chunks])
        ).embeddings
        if chunks and (not embeddings or any(not embedding for embedding in embeddings)):
            return VectorIndexSyncResult(
                provider=resolved.vector_provider,
                collection=resolved.chroma_collection,
                ready=False,
                count=0,
                warnings=["Embedding provider returned empty vectors; Chroma index was not updated."],
            )
        store.upsert_chunks(chunks, embeddings)
        store.delete_missing_chunk_ids({chunk.chunk_id for chunk in chunks})
        count = store.count()
    except Exception as exc:
        return VectorIndexSyncResult(
            provider=resolved.vector_provider,
            collection=resolved.chroma_collection,
            ready=False,
            count=0,
            warnings=[str(exc)],
        )

    return VectorIndexSyncResult(
        provider=resolved.vector_provider,
        collection=resolved.chroma_collection,
        ready=count > 0 and count >= len(chunks),
        count=count,
        warnings=[] if count else ["Chroma vector collection is empty."],
    )


def _chunk_metadata(chunk: SourceChunk) -> dict[str, Any]:
    metadata = {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "jurisdiction_id": chunk.jurisdiction_id or "",
        "source_type": chunk.source_type,
        "section_ref": chunk.section_ref,
        "effective_date": chunk.effective_date or "",
        "retrieved_at": chunk.retrieved_at or "",
        "districts": _list_filter_value(chunk.districts),
        "uses": _list_filter_value(chunk.uses),
        "source_version": chunk.source_version or "",
        "token_count": chunk.token_count,
    }
    for key, value in chunk.metadata.items():
        if isinstance(value, (str, int, float, bool)) and key not in metadata:
            metadata[key] = value
    return metadata


def _build_chroma_where(filters: dict[str, Any]) -> dict[str, Any]:
    conditions: list[dict[str, Any]] = []

    # Exact-match filters
    for key in ["jurisdiction_id", "source_id", "source_type", "source_version"]:
        value = filters.get(key)
        if value:
            conditions.append({key: {"$eq": value}})

    # District filter — pipe-delimited field; skip wildcard/unknown values
    district = filters.get("district")
    if district and district not in {"unknown", "*", ""}:
        conditions.append({"districts": {"$contains": f"|{district}|"}})

    # Use filter — pipe-delimited field; skip wildcard "general"
    use = filters.get("use")
    if use and use not in {"general", "*", ""}:
        # Accept chunks that match the use OR are tagged "general"
        conditions.append(
            {
                "$or": [
                    {"uses": {"$contains": f"|{use}|"}},
                    {"uses": {"$contains": "|general|"}},
                ]
            }
        )

    # Effective-date filter — include only ordinances effective on or before the date
    effective_on_or_before = filters.get("effective_on_or_before")
    if effective_on_or_before:
        # Only apply when the field is non-empty; Chroma $lte is string lexicographic here
        conditions.append(
            {
                "$or": [
                    {"effective_date": {"$eq": ""}},
                    {"effective_date": {"$lte": str(effective_on_or_before)}},
                ]
            }
        )

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _metadata_matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    district = filters.get("district")
    if district and district != "unknown" and not _list_value_contains(metadata.get("districts"), district, wildcard="*"):
        return False
    use = filters.get("use")
    if use and not (
        _list_value_contains(metadata.get("uses"), use, wildcard="general")
        or _list_value_contains(metadata.get("uses"), "general")
    ):
        return False
    effective_on_or_before = filters.get("effective_on_or_before")
    effective_date = str(metadata.get("effective_date") or "")
    if effective_on_or_before and effective_date and effective_date > str(effective_on_or_before):
        return False
    return True


def _list_filter_value(values: list[str]) -> str:
    return "|" + "|".join(sorted({value for value in values if value})) + "|"


def _list_value_contains(value: Any, needle: str, wildcard: str | None = None) -> bool:
    if isinstance(value, list):
        return needle in value or (wildcard is not None and wildcard in value)
    haystack = str(value or "")
    return f"|{needle}|" in haystack or (wildcard is not None and f"|{wildcard}|" in haystack)


def _first_result_list(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []
