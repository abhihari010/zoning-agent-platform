from __future__ import annotations

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult


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
        return AnalysisProviderResult(
            decision=decision,
            summary=summary,
        )
