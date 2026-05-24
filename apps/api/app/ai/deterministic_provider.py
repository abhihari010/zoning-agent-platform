from __future__ import annotations

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.models import ComplianceFinding, ComplianceResult


def deterministic_feasibility(project_description: str, district: str) -> tuple[str, str]:
    if district == "unknown":
        return "unknown", "District could not be confidently mapped. Additional parcel verification is required."
    if "bakery" in project_description.lower() and "garage" in project_description.lower():
        return (
            "conditional",
            "Garage-to-bakery conversion appears conditionally feasible with fire, health, and parking approvals.",
        )
    return "likely_allowed", "Proposed use appears likely allowed, subject to standard permit review."


class DeterministicAnalysisProvider:
    name = "deterministic"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        decision, summary = deterministic_feasibility(
            project_description=request.project_description,
            district=request.district,
        )
        citation_ids = [chunk.chunk_id for chunk in request.chunks if chunk.chunk_id]
        compliance = ComplianceResult(
            feasibility=_feasibility_from_decision(decision),
            confidence=0.5 if citation_ids else 0.3,
            summary=summary,
            findings=[
                ComplianceFinding(
                    category="permitted_use",
                    status="conditional" if decision == "conditional" else ("unknown" if decision == "unknown" else "compliant"),
                    summary=summary,
                    citation_ids=citation_ids[:3],
                    confidence=0.5 if citation_ids else 0.3,
                )
            ],
            required_permits=_required_permits_from_decision(decision),
            permit_path=_permit_path_from_decision(decision),
            warnings=[] if citation_ids else ["No citation-backed chunks were supplied to deterministic compliance."],
            unresolved_questions=[] if decision != "unknown" else ["Verify the parcel zoning district with the planning office."],
            citation_chunk_ids=citation_ids,
        )
        return AnalysisProviderResult(
            decision=decision,
            summary=summary,
            required_permits=compliance.required_permits,
            warnings=list(compliance.warnings),
            compliance=compliance,
        )


def _feasibility_from_decision(decision: str) -> str:
    if decision == "likely_allowed":
        return "feasible"
    if decision == "restricted":
        return "infeasible"
    if decision == "conditional":
        return "conditional"
    return "unknown"


def _permit_path_from_decision(decision: str) -> str:
    if decision == "likely_allowed":
        return "by-right"
    if decision == "conditional":
        return "special_use_permit"
    if decision == "restricted":
        return "variance"
    return "unknown"


def _required_permits_from_decision(decision: str) -> list[str]:
    if decision == "conditional":
        return ["Zoning review", "Building permit", "Health department approval"]
    if decision == "likely_allowed":
        return ["Zoning permit"]
    if decision == "restricted":
        return ["Variance or rezoning review"]
    return []
