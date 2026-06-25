from __future__ import annotations

import app.services as _svc

from app.ai.interfaces import RetrievalProviderResult, RetrievalProviderRequest
from app.orchestrator.pipeline_events import PipelineTraceRecorder
from app.orchestrator.zoning_orchestrator import ZoningOrchestrator


def test_orchestrator_records_location_resolution_events() -> None:
    events: list[tuple[str, str, dict | None]] = []

    def audit(stage: str, project_id: str, details: dict | None = None) -> None:
        events.append((stage, project_id, details))

    result = ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="mixed-use-core",
        district_confidence=0.9,
        district_method="fixture",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        project_id="project-1",
        trace_recorder=PipelineTraceRecorder(project_id="project-1", audit=audit),
    )

    event_names = [event[0] for event in events]
    assert "pipeline.intake.address_normalization.completed" in event_names
    assert "pipeline.intake.jurisdiction_resolution.completed" in event_names
    assert "pipeline.intake.district_resolution.completed" in event_names
    assert result.compliance is not None


def test_orchestrator_source_indexed_jurisdiction_is_served() -> None:
    """A source_indexed jurisdiction (christiansburg-va) must NOT early-exit; it must
    be served and carry a coverage caveat in the warnings channel."""
    events: list[tuple[str, str, dict | None]] = []

    def audit(stage: str, project_id: str, details: dict | None = None) -> None:
        events.append((stage, project_id, details))

    result = ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="unknown",
        jurisdiction_id="christiansburg-va",
        jurisdiction_name="Christiansburg, VA",
        normalized_address="100 Main St, Christiansburg, VA 24073",
        project_id="project-2",
        trace_recorder=PipelineTraceRecorder(project_id="project-2", audit=audit),
    )

    # Must NOT early-exit — retrieval must have been attempted.
    assert not any(event[0] == "pipeline.unsupported_jurisdiction_early_exit.warning" for event in events)
    assert any(event[0] == "pipeline.retrieval.started" for event in events)

    # Coverage caveat must appear in warnings.
    assert any("Preliminary coverage" in w for w in result.warnings), (
        f"Expected coverage caveat in warnings, got: {result.warnings}"
    )


def test_orchestrator_truly_unsupported_jurisdiction_early_exits() -> None:
    """A jurisdiction with coverage_status=unsupported must still early-exit."""
    events: list[tuple[str, str, dict | None]] = []

    def audit(stage: str, project_id: str, details: dict | None = None) -> None:
        events.append((stage, project_id, details))

    result = ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery.",
        district="unknown",
        jurisdiction_id="nonexistent-city-va",
        jurisdiction_name="Nonexistent City, VA",
        normalized_address="1 Main St, Nonexistent City, VA 99999",
        project_id="project-unsupported",
        trace_recorder=PipelineTraceRecorder(project_id="project-unsupported", audit=audit),
    )

    assert any(event[0] == "pipeline.unsupported_jurisdiction_early_exit.warning" for event in events)
    assert not any(event[0] == "pipeline.retrieval.started" for event in events)
    assert result.feasibility.decision == "unknown"
    assert result.citations == []


def test_orchestrator_public_supported_jurisdiction_no_coverage_caveat() -> None:
    """A public_supported jurisdiction (blacksburg-va) must be served with NO coverage caveat."""
    result = ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="mixed-use-core",
        district_confidence=0.9,
        district_method="fixture",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        project_id="project-public-supported",
    )

    assert not any("Preliminary coverage" in w for w in result.warnings), (
        f"public_supported jurisdiction must not carry coverage caveat; got: {result.warnings}"
    )


class _CapturingRetriever:
    """Retrieval provider stub that records every RetrievalProviderRequest."""

    name = "capturing"
    source_store = None

    def __init__(self) -> None:
        self.requests: list[RetrievalProviderRequest] = []

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        self.requests.append(request)
        return RetrievalProviderResult(citations=[])


def test_orchestrator_low_confidence_district_routes_retrieval_to_unknown(monkeypatch) -> None:
    # B1: when district_confidence < 0.7, the orchestrator must pass district="unknown"
    # to the retrieval provider so retrieval is jurisdiction+use filtered only (no
    # district bias from a low-confidence guess like the old Blacksburg city_default).
    retriever = _CapturingRetriever()
    monkeypatch.setattr(_svc, "get_retrieval_provider", lambda: retriever)

    ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="mixed-use-core",
        district_confidence=0.5,  # < 0.7 → effective_district must be "unknown"
        district_method="keyword",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        project_id="test-low-conf",
    )

    assert len(retriever.requests) == 1
    assert retriever.requests[0].district == "unknown"


def test_orchestrator_high_confidence_district_passes_through_to_retrieval(monkeypatch) -> None:
    # B1: when district_confidence >= 0.7, the concrete district is forwarded so the
    # re-ranker can apply the precision bonus from Layer-2 additive tags.
    retriever = _CapturingRetriever()
    monkeypatch.setattr(_svc, "get_retrieval_provider", lambda: retriever)

    ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="commercial-employment",
        district_confidence=0.9,  # >= 0.7 → effective_district must be "commercial-employment"
        district_method="parcel",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        project_id="test-high-conf",
    )

    assert len(retriever.requests) == 1
    assert retriever.requests[0].district == "commercial-employment"
