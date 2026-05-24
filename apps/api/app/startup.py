from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.registry import get_embedding_provider
from app.ai.source_registry_retriever import ensure_source_index_ready
from app.rag.vector_store import get_vector_index_status, sync_vector_index
from app.settings import get_settings
from app.storage import store


@dataclass(frozen=True)
class StartupReadiness:
    status: str
    source_count: int
    chunk_count: int
    source_index_ready: bool
    vector_provider: str
    vector_index_ready: bool
    vector_count: int
    warnings: list[str] = field(default_factory=list)


def prepare_source_index_for_startup() -> StartupReadiness:
    settings = get_settings()
    if not settings.startup_reindex_enabled:
        vector_status = get_vector_index_status(settings)
        source_count, chunk_count = _safe_source_counts()
        return StartupReadiness(
            status="skipped",
            source_count=source_count,
            chunk_count=chunk_count,
            source_index_ready=chunk_count > 0,
            vector_provider=vector_status.provider,
            vector_index_ready=vector_status.ready,
            vector_count=vector_status.count,
            warnings=["Startup reindex is disabled with STARTUP_REINDEX_ENABLED=false."],
        )

    try:
        readiness = ensure_source_index_ready()
        chunks = store.list_source_chunks()
        vector_result = sync_vector_index(chunks, get_embedding_provider(settings), settings)
        warnings = [*readiness.warnings, *vector_result.warnings]
        status = "ready" if readiness.index_ready else "warning"
        _safe_audit(
            "source.startup_reindex.completed",
            "source-registry",
            {
                "source_count": readiness.source_count,
                "chunk_count": readiness.chunk_count,
                "source_index_ready": readiness.index_ready,
                "vector_provider": vector_result.provider,
                "vector_count": vector_result.count,
                "vector_index_ready": vector_result.ready,
                "warnings": warnings,
            },
        )
        return StartupReadiness(
            status=status,
            source_count=readiness.source_count,
            chunk_count=readiness.chunk_count,
            source_index_ready=readiness.index_ready,
            vector_provider=vector_result.provider,
            vector_index_ready=vector_result.ready,
            vector_count=vector_result.count,
            warnings=warnings,
        )
    except Exception as exc:
        _safe_audit("source.startup_reindex.failed", "source-registry", {"error": str(exc)})
        vector_status = get_vector_index_status(settings)
        source_count, chunk_count = _safe_source_counts()
        return StartupReadiness(
            status="warning",
            source_count=source_count,
            chunk_count=chunk_count,
            source_index_ready=False,
            vector_provider=vector_status.provider,
            vector_index_ready=vector_status.ready,
            vector_count=vector_status.count,
            warnings=[f"Startup source readiness failed: {exc}"],
        )


def readiness_health() -> dict[str, object]:
    try:
        readiness = ensure_source_index_ready()
        vector_status = get_vector_index_status()
        warnings = [*readiness.warnings, *vector_status.warnings]
        return {
            "status": "ok" if readiness.index_ready else "warning",
            "source_index_ready": readiness.index_ready,
            "source_count": readiness.source_count,
            "chunk_count": readiness.chunk_count,
            "vector_provider": vector_status.provider,
            "vector_index_ready": vector_status.ready,
            "vector_count": vector_status.count,
            "warnings": warnings,
        }
    except Exception as exc:
        vector_status = get_vector_index_status()
        source_count, chunk_count = _safe_source_counts()
        return {
            "status": "warning",
            "source_index_ready": False,
            "source_count": source_count,
            "chunk_count": chunk_count,
            "vector_provider": vector_status.provider,
            "vector_index_ready": vector_status.ready,
            "vector_count": vector_status.count,
            "warnings": [f"Source readiness check failed: {exc}"],
        }


def _safe_audit(stage: str, project_id: str, details: dict) -> None:
    try:
        store.audit(stage, project_id, details)
    except Exception:
        return


def _safe_source_counts() -> tuple[int, int]:
    try:
        return store.get_source_count(), store.get_source_chunk_count()
    except Exception:
        return 0, 0
