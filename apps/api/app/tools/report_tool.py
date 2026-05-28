from __future__ import annotations

from typing import Any

from app.models import Checklist, ChecklistStep, PipelineStageReport, SourceCitation


class ReportTool:
    def build_initial_stage_reports(
        self,
        *,
        intake: Any,
        district: str,
        jurisdiction_name: str | None,
    ) -> list[PipelineStageReport]:
        return [
            PipelineStageReport(
                key="intake",
                label="Understand Project",
                status="completed",
                headline=f"Captured a {intake.project_category} request to {intake.user_intent}.",
                details=[
                    f"Project category: {intake.project_category}",
                    f"Inferred use: {intake.inferred_use}",
                    f"Missing details: {len(intake.missing_details)}",
                    f"Triggers: {', '.join(intake.possible_triggers) or 'none detected'}",
                ],
            ),
            PipelineStageReport(
                key="location",
                label="Resolve Property",
                status="warning" if district == "unknown" else "completed",
                headline=(
                    "Resolved jurisdiction and district context for retrieval."
                    if district != "unknown"
                    else "Jurisdiction was resolved, but the zoning district is still unknown."
                ),
                details=[
                    f"Jurisdiction: {jurisdiction_name or 'Not recorded'}",
                    f"District context: {district}",
                ],
            ),
        ]

    def build_retrieval_report(
        self,
        *,
        citations: list[SourceCitation],
        retrieval_provider_name: str,
        district: str,
        inferred_use: str,
    ) -> PipelineStageReport:
        if citations:
            return PipelineStageReport(
                key="retrieval",
                label="Retrieve Sources",
                status="completed",
                headline=f"Retrieved {len(citations)} relevant zoning source excerpts for review.",
                details=[
                    f"District searched: {district}",
                    f"Use searched: {inferred_use}",
                    *[f"{citation.title} ({citation.section_ref})" for citation in citations[:3]],
                ],
            )

        return PipelineStageReport(
            key="retrieval",
            label="Retrieve Sources",
            status="warning",
            headline="No relevant municipal ordinances were found in the current source registry.",
            details=[
                "The system could not retrieve matching zoning text for this district and use.",
                "A human review with the planning department is recommended before acting.",
            ],
        )

    def build_checklist(
        self,
        *,
        citations: list[SourceCitation],
        permits_override: list[str],
    ) -> Checklist:
        if not citations:
            checklist_steps = [
                ChecklistStep(
                    order=1,
                    action="Contact the planning department for parcel-level zoning verification",
                    required_docs=["property address", "parcel number if available", "project description"],
                    department="Planning Department",
                ),
                ChecklistStep(
                    order=2,
                    action="Request the current zoning district, permitted use table, and recent amendments",
                    required_docs=["written zoning inquiry", "site sketch if available"],
                    department="Planning Department",
                ),
                ChecklistStep(
                    order=3,
                    action="Confirm permit sequencing before spending on design or construction",
                    required_docs=["draft floor plan", "business operations summary"],
                    department="Permit Office",
                ),
            ]
        else:
            checklist_steps = [
                ChecklistStep(
                    order=1,
                    action="Request zoning verification letter for the parcel",
                    required_docs=["site plan", "property ownership proof"],
                    department="Planning Department",
                ),
                ChecklistStep(
                    order=2,
                    action="Submit change-of-use permit application",
                    required_docs=["business description", "floor plan", "parking plan"],
                    department="Permit Office",
                ),
                ChecklistStep(
                    order=3,
                    action="Complete fire and health compliance inspections",
                    required_docs=["equipment specification", "ventilation design"],
                    department="Fire Marshal and Health Department",
                ),
            ]

        return Checklist(
            steps=checklist_steps,
            permits=permits_override
            or (
                ["Zoning Verification Request", "Planning Counter Review"]
                if not citations
                else ["Change-of-Use Permit", "Business License", "Health Permit"]
            ),
            documents=(
                ["Property Address", "Project Narrative", "Parcel Number", "Site Sketch"]
                if not citations
                else ["Site Plan", "Floor Plan", "Parking Plan", "Fire Safety Plan"]
            ),
            departments=["Planning", "Permitting", "Fire", "Health"] if citations else ["Planning", "Permitting"],
        )
