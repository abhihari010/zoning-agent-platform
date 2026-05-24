from __future__ import annotations

from app.orchestrator.pipeline_events import PipelineTraceRecorder
from app.orchestrator.zoning_orchestrator import ZoningOrchestrator


def test_orchestrator_records_location_resolution_events() -> None:
    events: list[tuple[str, str, dict | None]] = []

    def audit(stage: str, project_id: str, details: dict | None = None) -> None:
        events.append((stage, project_id, details))

    result = ZoningOrchestrator().analyze_project(
        project_description="Open a small bakery with employees and renovation plans.",
        district="mixed-use-core",
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


def test_orchestrator_records_unsupported_jurisdiction_event() -> None:
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

    assert any(event[0] == "pipeline.unsupported_jurisdiction_early_exit.warning" for event in events)
    assert not any(event[0] == "pipeline.retrieval.started" for event in events)
    assert result.feasibility.decision == "unknown"
    assert result.citations == []
