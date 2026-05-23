from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.deterministic_provider import deterministic_feasibility
from app.ai.interfaces import AnalysisProvider, AnalysisProviderRequest
from app.models import DecisionType, SourceCitation
from app.orchestrator.pipeline_context import PipelineContext


@dataclass
class ComplianceToolResult:
    decision: DecisionType
    summary: str
    permits_override: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_model: bool = False


class ComplianceTool:
    def analyze(
        self,
        context: PipelineContext,
        analysis_provider: AnalysisProvider,
        citations: list[SourceCitation],
    ) -> ComplianceToolResult:
        if not citations:
            return ComplianceToolResult(
                decision="unknown",
                summary=(
                    "We could not find enough source material for this district and project type to make a reliable zoning call."
                ),
            )

        missing_details = context.intake.missing_details if context.intake else []
        try:
            provider_output = analysis_provider.generate_analysis(
                AnalysisProviderRequest(
                    project_description=context.combined_description,
                    district=context.district,
                    citation_excerpts=[citation.excerpt for citation in citations],
                    missing_fields=missing_details,
                )
            )
        except Exception as exc:
            fallback_decision, fallback_summary = deterministic_feasibility(
                context.combined_description,
                context.district,
            )
            return ComplianceToolResult(
                decision=fallback_decision,
                summary=fallback_summary,
                warnings=[f"{analysis_provider.name} analysis fallback engaged: {exc}"],
            )

        return ComplianceToolResult(
            decision=provider_output.decision,
            summary=provider_output.summary,
            permits_override=provider_output.required_permits,
            follow_up_questions=list(provider_output.follow_up_questions),
            warnings=list(provider_output.warnings),
            used_model=analysis_provider.name != "deterministic",
        )
