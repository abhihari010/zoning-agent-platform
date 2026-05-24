from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.ai.deterministic_provider import deterministic_feasibility
from app.ai.interfaces import AnalysisProvider, AnalysisProviderRequest
from app.models import ComplianceFinding, ComplianceResult, DecisionType, SourceChunk, SourceCitation
from app.orchestrator.pipeline_context import PipelineContext


@dataclass
class ComplianceToolResult:
    decision: DecisionType
    summary: str
    permits_override: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_model: bool = False
    compliance: ComplianceResult | None = None


class ComplianceTool:
    def analyze(
        self,
        context: PipelineContext,
        analysis_provider: AnalysisProvider,
        citations: list[SourceCitation],
        evidence_chunks: list[SourceChunk] | None = None,
    ) -> ComplianceToolResult:
        if not citations:
            compliance = ComplianceResult(
                feasibility="unknown",
                confidence=0.3,
                summary="We could not find enough source material for this district and project type to make a reliable zoning call.",
                findings=[],
                required_permits=[],
                permit_path="unknown",
                warnings=["No citation-backed evidence was available."],
                unresolved_questions=["Confirm the applicable zoning district and use standards with the planning office."],
                citation_chunk_ids=[],
            )
            return ComplianceToolResult(
                decision="unknown",
                summary=compliance.summary,
                warnings=list(compliance.warnings),
                compliance=compliance,
            )

        missing_details = context.intake.missing_details if context.intake else []
        evidence_chunks = evidence_chunks or _chunks_from_citations(citations)
        try:
            provider_output = analysis_provider.generate_analysis(
                AnalysisProviderRequest(
                    project_description=context.combined_description,
                    district=context.district,
                    citation_excerpts=[citation.excerpt for citation in citations],
                    missing_fields=missing_details,
                    chunks=evidence_chunks,
                    inferred_use=context.intake.inferred_use if context.intake else "general",
                )
            )
        except Exception as exc:
            fallback_decision, fallback_summary = deterministic_feasibility(
                context.combined_description,
                context.district,
            )
            compliance = _legacy_compliance_result(
                decision=fallback_decision,
                summary=fallback_summary,
                required_permits=[],
                warnings=[f"{analysis_provider.name} analysis fallback engaged: {exc}"],
                citations=citations,
            )
            return ComplianceToolResult(
                decision=fallback_decision,
                summary=fallback_summary,
                warnings=list(compliance.warnings),
                compliance=compliance,
            )

        compliance = provider_output.compliance or _legacy_compliance_result(
            decision=provider_output.decision,
            summary=provider_output.summary,
            required_permits=provider_output.required_permits,
            warnings=provider_output.warnings,
            citations=citations,
        )
        compliance = _validate_compliance_citations(compliance, citations)
        return ComplianceToolResult(
            decision=provider_output.decision,
            summary=compliance.summary or provider_output.summary,
            permits_override=compliance.required_permits,
            follow_up_questions=list(provider_output.follow_up_questions),
            warnings=list(compliance.warnings),
            used_model=analysis_provider.name != "deterministic",
            compliance=compliance,
        )


def _legacy_compliance_result(
    *,
    decision: DecisionType,
    summary: str,
    required_permits: list[str],
    warnings: list[str],
    citations: list[SourceCitation],
) -> ComplianceResult:
    citation_ids = [citation.chunk_id for citation in citations if citation.chunk_id]
    confidence = 0.5 if citation_ids else 0.3
    return ComplianceResult(
        feasibility=_feasibility_from_decision(decision),
        confidence=confidence,
        summary=summary,
        findings=[
            ComplianceFinding(
                category="general",
                status=_finding_status_from_decision(decision),
                summary=summary,
                citation_ids=citation_ids[:3],
                confidence=confidence,
            )
        ],
        required_permits=required_permits,
        permit_path=_permit_path_from_decision(decision),
        warnings=list(warnings),
        unresolved_questions=[] if decision != "unknown" else ["Evidence is insufficient for a reliable zoning decision."],
        citation_chunk_ids=citation_ids,
    )


def _chunks_from_citations(citations: list[SourceCitation]) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    for index, citation in enumerate(citations):
        chunk_id = citation.chunk_id or f"citation-{index}"
        text = citation.excerpt if len(citation.excerpt) >= 10 else f"{citation.excerpt} citation"
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks.append(
            SourceChunk(
                chunk_id=chunk_id,
                source_id=citation.source_id,
                title=citation.title,
                chunk_text=text,
                chunk_index=index,
                source_text_hash=text_hash,
                section_ref=citation.section_ref,
                jurisdiction_id=citation.jurisdiction_id,
                url=citation.url,
                effective_date=citation.effective_date,
                districts=[],
                uses=[],
                source_type=citation.source_type or "zoning_ordinance",
                retrieved_at=citation.retrieved_at,
                source_version=None,
                token_count=len(text.split()),
                metadata=citation.metadata,
            )
        )
    return chunks


def _validate_compliance_citations(
    compliance: ComplianceResult,
    citations: list[SourceCitation],
) -> ComplianceResult:
    valid_ids = {citation.chunk_id for citation in citations if citation.chunk_id}
    cited_ids = set(compliance.citation_chunk_ids)
    for finding in compliance.findings:
        cited_ids.update(finding.citation_ids)
    invalid_ids = sorted(cited_ids.difference(valid_ids))
    warnings = list(compliance.warnings)
    if invalid_ids:
        warnings.append(f"Invalid citation IDs were removed: {', '.join(invalid_ids)}")

    cleaned_findings = [
        finding.model_copy(
            update={"citation_ids": [chunk_id for chunk_id in finding.citation_ids if chunk_id in valid_ids]}
        )
        for finding in compliance.findings
    ]
    cleaned_chunk_ids = [chunk_id for chunk_id in compliance.citation_chunk_ids if chunk_id in valid_ids]
    confidence = compliance.confidence
    if not cleaned_chunk_ids and confidence > 0.3:
        confidence = 0.3
        warnings.append("Confidence capped because no valid citation IDs support the finding.")

    return compliance.model_copy(
        update={
            "confidence": confidence,
            "findings": cleaned_findings,
            "citation_chunk_ids": cleaned_chunk_ids,
            "warnings": warnings,
        }
    )


def _feasibility_from_decision(decision: DecisionType) -> str:
    if decision == "likely_allowed":
        return "feasible"
    if decision == "restricted":
        return "infeasible"
    if decision == "conditional":
        return "conditional"
    return "unknown"


def _finding_status_from_decision(decision: DecisionType) -> str:
    if decision == "likely_allowed":
        return "compliant"
    if decision == "restricted":
        return "non_compliant"
    if decision == "conditional":
        return "conditional"
    return "unknown"


def _permit_path_from_decision(decision: DecisionType) -> str:
    if decision == "likely_allowed":
        return "by-right"
    if decision == "conditional":
        return "special_use_permit"
    if decision == "restricted":
        return "variance"
    return "unknown"
