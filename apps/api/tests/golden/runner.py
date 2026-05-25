from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import services
from app.ingestion import build_source_chunks
from app.models import AnalyzeResult, SourceRegistryEntry
from app.orchestrator.pipeline_events import PipelineTraceRecorder
from app.storage import store


SCENARIOS_PATH = Path(__file__).with_name("scenarios.json")


@dataclass(frozen=True)
class GoldenRun:
    scenario_id: str
    result: AnalyzeResult
    trace_events: list[dict[str, Any]]


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_scenario(scenario: dict[str, Any]) -> GoldenRun:
    store.reset()
    sources = [SourceRegistryEntry.model_validate(source) for source in scenario.get("sources", [])]
    for source in sources:
        store.upsert_source(source)
    if sources:
        store.replace_source_chunks(build_source_chunks(sources))

    trace_events: list[dict[str, Any]] = []

    def capture(stage: str, project_id: str, details: dict[str, Any] | None = None) -> None:
        trace_events.append(
            {
                "stage": stage,
                "project_id": project_id,
                "details": details or {},
            }
        )

    result = services.analyze_project(
        project_description=scenario["project_description"],
        district=scenario["district"],
        jurisdiction_id=scenario.get("jurisdiction_id"),
        jurisdiction_name=scenario.get("jurisdiction_name"),
        normalized_address=scenario.get("normalized_address"),
        project_id=scenario["id"],
        trace_recorder=PipelineTraceRecorder(project_id=scenario["id"], audit=capture),
    )
    return GoldenRun(scenario_id=scenario["id"], result=result, trace_events=trace_events)


def assert_expectations(run: GoldenRun, scenario: dict[str, Any]) -> None:
    expect = scenario["expect"]
    result = run.result
    assert result.feasibility.decision in expect["decisions"]
    assert result.status in expect["statuses"]
    assert len(result.citations) >= expect.get("min_citations", 0)
    if "max_citations" in expect:
        assert len(result.citations) <= expect["max_citations"]
    if "min_confidence" in expect:
        assert result.feasibility.confidence >= expect["min_confidence"]
    if "max_confidence" in expect:
        assert result.feasibility.confidence <= expect["max_confidence"]
    if "jurisdiction_supported" in expect:
        assert result.trust_indicators is not None
        assert result.trust_indicators.jurisdiction_supported is expect["jurisdiction_supported"]
    forbidden_jurisdictions = set(expect.get("forbidden_citation_jurisdiction_ids", []))
    if forbidden_jurisdictions:
        citation_jurisdictions = {citation.jurisdiction_id for citation in result.citations}
        assert citation_jurisdictions.isdisjoint(forbidden_jurisdictions)

    for warning in expect.get("required_warning_substrings", []):
        assert any(warning in candidate for candidate in result.warnings)


def write_trace(run: GoldenRun, trace_dir: Path) -> Path:
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{run.scenario_id}.json"
    trace_path.write_text(
        json.dumps(
            {
                "scenario_id": run.scenario_id,
                "result": run.result.model_dump(mode="json"),
                "trace_events": run.trace_events,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return trace_path
