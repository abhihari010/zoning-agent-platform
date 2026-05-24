from __future__ import annotations

import json
from dataclasses import dataclass

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.ai.local_model_provider import COMPLIANCE_SCHEMA_JSON
from app.models import ComplianceFinding, ComplianceResult, SourceChunk, SourceCitation
from app.orchestrator.pipeline_context import PipelineContext
from app.prompts import PromptRenderer
from app.tools.compliance_tool import ComplianceTool


def _chunk(chunk_id: str = "chunk-1") -> SourceChunk:
    return SourceChunk(
        chunk_id=chunk_id,
        source_id="source-1",
        title="Zoning Rule",
        chunk_text="Food service uses may require zoning review and parking review.",
        chunk_index=0,
        source_text_hash="a" * 64,
        section_ref="Sec 1",
        jurisdiction_id="blacksburg-va",
        districts=["mixed-use-core"],
        uses=["food_service"],
    )


def _citation(chunk_id: str | None = "chunk-1") -> SourceCitation:
    return SourceCitation(
        source_id="source-1",
        title="Zoning Rule",
        excerpt="Food service uses may require zoning review and parking review.",
        section_ref="Sec 1",
        chunk_id=chunk_id,
        jurisdiction_id="blacksburg-va",
    )


def test_deterministic_compliance_returns_structured_result() -> None:
    result = DeterministicAnalysisProvider().generate_analysis(
        AnalysisProviderRequest(
            project_description="Convert garage to bakery with employees and renovation plans.",
            district="mixed-use-core",
            citation_excerpts=["Food service uses may require review."],
            missing_fields=[],
            chunks=[_chunk()],
            inferred_use="food_service",
        )
    )

    assert result.compliance is not None
    assert result.compliance.feasibility == "conditional"
    assert result.compliance.confidence == 0.5
    assert result.compliance.citation_chunk_ids == ["chunk-1"]


def test_no_citations_caps_confidence() -> None:
    result = ComplianceTool().analyze(
        PipelineContext(
            project_description="Open a bakery.",
            combined_description="Open a bakery.",
            district="mixed-use-core",
        ),
        DeterministicAnalysisProvider(),
        [],
    )

    assert result.compliance is not None
    assert result.compliance.feasibility == "unknown"
    assert result.compliance.confidence <= 0.3
    assert result.warnings


def test_invalid_citation_ids_rejected() -> None:
    @dataclass
    class FakeProvider:
        name: str = "fake"

        def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
            compliance = ComplianceResult(
                feasibility="feasible",
                confidence=0.9,
                summary="Looks feasible.",
                findings=[
                    ComplianceFinding(
                        category="permitted_use",
                        status="compliant",
                        summary="Allowed.",
                        citation_ids=["fake-id"],
                        confidence=0.9,
                    )
                ],
                required_permits=["Zoning permit"],
                permit_path="by-right",
                warnings=[],
                unresolved_questions=[],
                citation_chunk_ids=["fake-id"],
            )
            return AnalysisProviderResult(
                decision="likely_allowed",
                summary="Looks feasible.",
                required_permits=["Zoning permit"],
                compliance=compliance,
            )

    result = ComplianceTool().analyze(
        PipelineContext(
            project_description="Open a bakery.",
            combined_description="Open a bakery.",
            district="mixed-use-core",
        ),
        FakeProvider(),
        [_citation("chunk-1")],
    )

    assert result.compliance is not None
    assert result.compliance.citation_chunk_ids == []
    assert result.compliance.findings[0].citation_ids == []
    assert any("Invalid citation IDs" in warning for warning in result.warnings)
    assert result.compliance.confidence <= 0.3


def test_compliance_uses_real_evidence_chunks() -> None:
    captured: dict = {}

    @dataclass
    class FakeProvider:
        name: str = "fake"

        def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
            captured["chunk_ids"] = [chunk.chunk_id for chunk in request.chunks]
            compliance = ComplianceResult(
                feasibility="conditional",
                confidence=0.7,
                summary="Needs review.",
                findings=[
                    ComplianceFinding(
                        category="parking",
                        status="conditional",
                        summary="Parking review required.",
                        citation_ids=["real-chunk"],
                        confidence=0.7,
                    )
                ],
                required_permits=["Zoning review"],
                permit_path="special_use_permit",
                warnings=[],
                unresolved_questions=[],
                citation_chunk_ids=["real-chunk"],
            )
            return AnalysisProviderResult(
                decision="conditional",
                summary="Needs review.",
                required_permits=["Zoning review"],
                compliance=compliance,
            )

    real_chunk = _chunk("real-chunk")
    result = ComplianceTool().analyze(
        PipelineContext(
            project_description="Open a bakery.",
            combined_description="Open a bakery.",
            district="mixed-use-core",
        ),
        FakeProvider(),
        [_citation("real-chunk")],
        [real_chunk],
    )

    assert captured["chunk_ids"] == ["real-chunk"]
    assert result.compliance is not None
    assert result.compliance.citation_chunk_ids == ["real-chunk"]


def test_prompt_renderer_loads_templates() -> None:
    rendered = PromptRenderer().render(
        "compliance_synthesis.md",
        project_description="Open a bakery.",
        district="mixed-use-core",
        inferred_use="food_service",
        chunks_json="[]",
        compliance_schema_json="{}",
    )

    assert "Open a bakery." in rendered
    assert "mixed-use-core" in rendered


def test_compliance_schema_is_valid_json() -> None:
    payload = json.loads(COMPLIANCE_SCHEMA_JSON)

    assert "feasibility" in payload
    assert "findings" in payload
