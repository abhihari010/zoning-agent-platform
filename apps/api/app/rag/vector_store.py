from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.ai.interfaces import EmbeddingProvider, EmbeddingProviderRequest
from app.jurisdictions import get_jurisdiction_scope, source_applies_to_jurisdiction
from app.models import SourceChunk
from app.settings import Settings, get_settings

_CHUNK_ID_NAMESPACE = uuid.NAMESPACE_URL
_KEYWORD_PAYLOAD_INDEX_FIELDS = (
    "jurisdiction_id",
    "state",
    "source_id",
    "source_type",
    "source_version",
    "districts",
    "uses",
)


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


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self._url = url or resolved.qdrant_url
        self._api_key = api_key if api_key is not None else (resolved.qdrant_api_key or None)
        self.collection_name = collection_name or resolved.qdrant_collection
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is not installed. Install qdrant-client to use VECTOR_PROVIDER=qdrant."
            ) from exc
        self._client = QdrantClient(url=self._url, api_key=self._api_key, timeout=30)
        return self._client

    def _ensure_collection(self, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        try:
            client.get_collection(self.collection_name)
        except Exception:
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Create keyword indexes for payload fields used in Qdrant filters."""
        from qdrant_client.models import PayloadSchemaType

        client = self._get_client()
        for field_name in _KEYWORD_PAYLOAD_INDEX_FIELDS:
            try:
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            except Exception:
                # Existing indexes and providers that do not require explicit
                # payload indexes should not block indexing or retrieval. If an
                # index is truly missing, query_points will surface the error.
                continue

    def is_available(self) -> bool:
        try:
            self._get_client().get_collections()
            return True
        except Exception:
            return False

    def upsert_chunks(self, chunks: list[SourceChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        if not chunks:
            return

        from qdrant_client.models import PointStruct

        vector_size = len(embeddings[0])
        self._ensure_collection(vector_size)
        client = self._get_client()
        points = [
            PointStruct(
                id=_chunk_id_to_point_id(chunk.chunk_id),
                vector=embedding,
                payload=_chunk_metadata(chunk),
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def delete_missing_chunk_ids(self, valid_chunk_ids: set[str]) -> int:
        from qdrant_client.models import PointIdsList

        existing_chunk_ids = self._scroll_all_chunk_ids()
        stale_chunk_ids = [cid for cid in existing_chunk_ids if cid not in valid_chunk_ids]
        if stale_chunk_ids:
            stale_point_ids = [_chunk_id_to_point_id(cid) for cid in stale_chunk_ids]
            self._get_client().delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=stale_point_ids),
                wait=True,
            )
        return len(stale_chunk_ids)

    def update_chunk_payloads(self, payloads_by_chunk_id: dict[str, dict[str, Any]]) -> int:
        if not payloads_by_chunk_id:
            return 0

        client = self._get_client()
        updated = 0
        for chunk_id, payload in payloads_by_chunk_id.items():
            if not payload:
                continue
            client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[_chunk_id_to_point_id(chunk_id)],
                wait=True,
            )
            updated += 1
        return updated

    def existing_chunk_ids(self) -> set[str]:
        """Chunk ids already stored in Qdrant.

        Used to make reindexing incremental: a chunk_id encodes its source's
        content hash, so an unchanged source keeps the same id and can be
        skipped instead of re-embedded. Returns an empty set if the collection
        does not exist yet (nothing has been indexed), so callers treat a fresh
        collection as "embed everything".
        """
        try:
            return set(self._scroll_all_chunk_ids())
        except Exception:
            return set()

    def _scroll_all_chunk_ids(self) -> list[str]:
        client = self._get_client()
        chunk_ids: list[str] = []
        offset = None
        while True:
            records, next_offset = client.scroll(
                collection_name=self.collection_name,
                with_payload=["chunk_id"],
                with_vectors=False,
                limit=1000,
                offset=offset,
            )
            for record in records:
                if record.payload and "chunk_id" in record.payload:
                    chunk_ids.append(record.payload["chunk_id"])
            if next_offset is None:
                break
            offset = next_offset
        return chunk_ids

    def query(
        self,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[VectorQueryResult]:
        if not query_embedding:
            return []

        filters = filters or {}
        qdrant_filter = _build_qdrant_filter(filters)
        client = self._get_client()
        if qdrant_filter is not None:
            self._ensure_payload_indexes()

        try:
            # qdrant-client removed .search() in favour of .query_points() (the
            # response carries the ScoredPoints under .points).
            hits = client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                query_filter=qdrant_filter,
                limit=limit * 2,
                with_payload=True,
                with_vectors=False,
            ).points
        except Exception as exc:
            raise RuntimeError(f"Qdrant query failed: {exc}") from exc

        results: list[VectorQueryResult] = []
        for hit in hits:
            metadata = hit.payload or {}
            if not _metadata_matches(metadata, filters):
                continue
            score = float(hit.score)
            results.append(
                VectorQueryResult(
                    chunk_id=str(metadata.get("chunk_id", str(hit.id))),
                    distance=1.0 - score,
                    score=score,
                    metadata=metadata,
                )
            )
            if len(results) >= limit:
                break
        return results

    def reset_collection(self) -> None:
        try:
            self._get_client().delete_collection(self.collection_name)
        except Exception:
            pass

    def count(self) -> int:
        try:
            result = self._get_client().count(collection_name=self.collection_name, exact=True)
            return int(result.count)
        except Exception:
            return 0


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

    store = QdrantVectorStore(settings=resolved)
    try:
        count = store.count()
    except Exception as exc:
        return VectorIndexStatus(
            provider=resolved.vector_provider,
            collection=resolved.qdrant_collection,
            ready=False,
            count=0,
            warnings=[str(exc)],
        )

    warnings = [] if count > 0 else ["Qdrant vector collection is empty."]
    return VectorIndexStatus(
        provider=resolved.vector_provider,
        collection=resolved.qdrant_collection,
        ready=count > 0,
        count=count,
        warnings=warnings,
    )


def sync_vector_index(
    chunks: list[SourceChunk],
    embedding_provider: EmbeddingProvider,
    settings: Settings | None = None,
    *,
    full_rebuild: bool = False,
) -> VectorIndexSyncResult:
    """Reconcile Qdrant with ``chunks``, embedding only what is missing.

    Incremental by default: chunks whose id is already in Qdrant are skipped
    (their content is unchanged because the id encodes the content hash), so
    re-running after a partial/timed-out reindex resumes instead of starting
    over. Stale points are pruned at the end via ``delete_missing_chunk_ids``.
    Pass ``full_rebuild=True`` to wipe the collection and re-embed everything.
    """
    resolved = settings or get_settings()
    if resolved.vector_provider == "none":
        return VectorIndexSyncResult(
            provider="none",
            collection=None,
            ready=False,
            count=0,
            warnings=["Vector index skipped because VECTOR_PROVIDER=none."],
        )

    store = QdrantVectorStore(settings=resolved)
    try:
        if resolved.vector_provider == "qdrant" and full_rebuild:
            store.reset_collection()
        existing_ids = set() if full_rebuild else store.existing_chunk_ids()
        pending = [chunk for chunk in chunks if chunk.chunk_id not in existing_ids]
        if pending:
            embeddings = embedding_provider.embed(
                EmbeddingProviderRequest(texts=[chunk.chunk_text for chunk in pending])
            ).embeddings
            if not embeddings or any(not embedding for embedding in embeddings):
                return VectorIndexSyncResult(
                    provider=resolved.vector_provider,
                    collection=resolved.qdrant_collection,
                    ready=False,
                    count=0,
                    warnings=["Embedding provider returned empty vectors; Qdrant index was not updated."],
                )
            store.upsert_chunks(pending, embeddings)
        store.delete_missing_chunk_ids({chunk.chunk_id for chunk in chunks})
        count = store.count()
    except Exception as exc:
        return VectorIndexSyncResult(
            provider=resolved.vector_provider,
            collection=resolved.qdrant_collection,
            ready=False,
            count=0,
            warnings=[str(exc)],
        )

    return VectorIndexSyncResult(
        provider=resolved.vector_provider,
        collection=resolved.qdrant_collection,
        ready=count > 0 and count >= len(chunks),
        count=count,
        warnings=[] if count else ["Qdrant vector collection is empty."],
    )


def _chunk_id_to_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_CHUNK_ID_NAMESPACE, chunk_id))


def _chunk_metadata(chunk: SourceChunk) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "jurisdiction_id": chunk.jurisdiction_id or "",
        "jurisdiction_scope": chunk.metadata.get(
            "jurisdiction_scope",
            "global" if chunk.jurisdiction_id == "*" else "local",
        ),
        "state": chunk.metadata.get("state", ""),
        "county": chunk.metadata.get("county", ""),
        "municipality": chunk.metadata.get("municipality", ""),
        "source_type": chunk.source_type,
        "section_ref": chunk.section_ref,
        "url": chunk.url or "",
        "effective_date": chunk.effective_date or "",
        "retrieved_at": chunk.retrieved_at or "",
        "districts": [d for d in chunk.districts if d],
        "uses": [u for u in chunk.uses if u],
        "source_version": chunk.source_version or "",
        "content_hash": chunk.metadata.get("content_hash", chunk.source_text_hash),
        "coverage_status": chunk.metadata.get("coverage_status", ""),
        "token_count": chunk.token_count,
    }
    for key, value in chunk.metadata.items():
        if isinstance(value, (str, int, float, bool)) and key not in metadata:
            metadata[key] = value
    return metadata


def _build_qdrant_filter(filters: dict[str, Any]) -> Any | None:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    must: list[Any] = []

    jurisdiction_id = filters.get("jurisdiction_id")
    if jurisdiction_id:
        jurisdiction_scope = get_jurisdiction_scope(str(jurisdiction_id))
        should: list[Any] = [
            FieldCondition(key="jurisdiction_id", match=MatchValue(value=jurisdiction_id))
        ]
        if jurisdiction_scope and jurisdiction_scope.parent_jurisdiction_id:
            should.append(
                FieldCondition(
                    key="jurisdiction_id",
                    match=MatchValue(value=jurisdiction_scope.parent_jurisdiction_id),
                )
            )
        if jurisdiction_scope and jurisdiction_scope.state:
            should.append(
                Filter(
                    must=[
                        FieldCondition(key="jurisdiction_id", match=MatchValue(value="*")),
                        FieldCondition(key="state", match=MatchValue(value=jurisdiction_scope.state)),
                    ]
                )
            )
        must.append(Filter(should=should))

    for key in ["source_id", "source_type", "source_version"]:
        value = filters.get(key)
        if value:
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))

    district = filters.get("district")
    if district and district not in {"unknown", "*", ""}:
        # A chunk tagged districts=["unknown"] is unclassified-by-district and
        # applies to any queried district, mirroring the uses/"general" wildcard
        # below. Without the "unknown" branch, the unclassified scraped-ordinance
        # corpus is filtered out of every district-specific query.
        must.append(
            Filter(
                should=[
                    FieldCondition(key="districts", match=MatchValue(value=district)),
                    FieldCondition(key="districts", match=MatchValue(value="unknown")),
                ]
            )
        )

    use = filters.get("use")
    if use and use not in {"general", "*", ""}:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="uses", match=MatchValue(value=use)),
                    FieldCondition(key="uses", match=MatchValue(value="general")),
                ]
            )
        )

    # effective_date range filtering is handled in post-filter _metadata_matches
    if not must:
        return None
    return Filter(must=must)


def _metadata_matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    jurisdiction_id = filters.get("jurisdiction_id")
    if jurisdiction_id and not source_applies_to_jurisdiction(
        source_jurisdiction_id=str(metadata.get("jurisdiction_id") or "") or None,
        source_metadata=metadata,
        target_jurisdiction_id=str(jurisdiction_id),
    ):
        return False
    district = filters.get("district")
    if (
        district
        and district != "unknown"
        and not _list_value_contains(metadata.get("districts"), district, wildcard="*")
        and not _list_value_contains(metadata.get("districts"), "unknown")
    ):
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


def _list_value_contains(value: Any, needle: str, wildcard: str | None = None) -> bool:
    if isinstance(value, list):
        return needle in value or (wildcard is not None and wildcard in value)
    haystack = str(value or "")
    return f"|{needle}|" in haystack or (wildcard is not None and f"|{wildcard}|" in haystack)
