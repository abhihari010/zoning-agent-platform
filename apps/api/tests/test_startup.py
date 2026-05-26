from __future__ import annotations

from dataclasses import dataclass

from app import startup
from app.rag.vector_store import VectorIndexStatus


@dataclass
class FailingStore:
    def audit(self, *_args, **_kwargs) -> None:
        raise RuntimeError("database unavailable")

    def get_source_count(self) -> int:
        raise RuntimeError("database unavailable")

    def get_source_chunk_count(self) -> int:
        raise RuntimeError("database unavailable")


def test_startup_readiness_fails_soft_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(startup, "store", FailingStore())
    monkeypatch.setattr(
        startup,
        "ensure_source_index_ready",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        startup,
        "get_vector_index_status",
        lambda _settings=None: VectorIndexStatus(
            provider="none",
            collection=None,
            ready=False,
            count=0,
            warnings=["Vector index is disabled."],
        ),
    )

    readiness = startup.prepare_source_index_for_startup()

    assert readiness.status == "warning"
    assert readiness.source_index_ready is False
    assert readiness.source_count == 0
    assert readiness.chunk_count == 0
    assert "Startup source readiness failed" in readiness.warnings[0]


def test_health_readiness_fails_soft_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(startup, "store", FailingStore())
    monkeypatch.setattr(
        startup,
        "ensure_source_index_ready",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        startup,
        "get_vector_index_status",
        lambda _settings=None: VectorIndexStatus(
            provider="none",
            collection=None,
            ready=False,
            count=0,
            warnings=[],
        ),
    )

    health = startup.readiness_health()

    assert health["status"] == "warning"
    assert health["source_index_ready"] is False
    assert health["source_count"] == 0
    assert health["chunk_count"] == 0
    assert "Source readiness check failed" in health["warnings"][0]


def test_liveness_health_uses_last_startup_snapshot(monkeypatch) -> None:
    startup._LAST_STARTUP_READINESS = startup.StartupReadiness(
        status="ready",
        source_count=3,
        chunk_count=3,
        source_index_ready=True,
        vector_provider="none",
        vector_index_ready=False,
        vector_count=0,
        warnings=[],
    )
    monkeypatch.setattr(
        startup,
        "ensure_source_index_ready",
        lambda: (_ for _ in ()).throw(RuntimeError("should not run deep readiness")),
    )
    monkeypatch.setattr(startup, "store", FailingStore())

    health = startup.liveness_health()

    assert health["status"] == "ok"
    assert health["source_index_ready"] is True
    assert health["source_count"] == 3
