from __future__ import annotations

from app.ai.interfaces import RetrievalProviderRequest
from app.ai.registry import get_embedding_provider
from app.ai.source_registry_retriever import ensure_source_index_ready
from app.models import (
    AnalyzeResult,
    Feasibility,
    PipelineMetadata,
    PipelineStageReport,
)
from app.orchestrator.pipeline_context import PIPELINE_VERSION, PipelineContext
from app.orchestrator.pipeline_events import PipelineTraceRecorder
from app.settings import get_settings
from app.tools import CitationTool, ComplianceTool, IntakeTool, ReportTool


PROMPT_VERSION = "2026_05_single_orchestrator"


class ZoningOrchestrator:
    """Single coordinator for the zoning analysis pipeline.

    The API response still exposes the legacy ``agents`` field for frontend
    compatibility, but each entry now represents a pipeline stage instead of an
    autonomous model-calling agent.
    """

    def __init__(
        self,
        *,
        intake_tool: IntakeTool | None = None,
        compliance_tool: ComplianceTool | None = None,
        report_tool: ReportTool | None = None,
    ) -> None:
        self.intake_tool = intake_tool or IntakeTool()
        self.compliance_tool = compliance_tool or ComplianceTool()
        self.report_tool = report_tool or ReportTool()

    def analyze_project(
        self,
        *,
        project_description: str,
        district: str,
        jurisdiction_id: str | None = None,
        jurisdiction_name: str | None = None,
        normalized_address: str | None = None,
        project_id: str | None = None,
        clarification_answers: dict[str, str] | None = None,
        trace_recorder: PipelineTraceRecorder | None = None,
    ) -> AnalyzeResult:
        from app import services as service_helpers

        recorder = trace_recorder or PipelineTraceRecorder(project_id=project_id)
        combined_description = service_helpers._merge_project_context(
            project_description,
            clarification_answers,
        )
        context = PipelineContext(
            project_id=project_id,
            normalized_address=normalized_address,
            project_description=project_description,
            combined_description=combined_description,
            district=district,
            jurisdiction_id=jurisdiction_id,
            jurisdiction_name=jurisdiction_name,
            clarification_answers=clarification_answers or {},
        )

        settings = get_settings()
        analysis_provider = service_helpers.get_analysis_provider()
        retrieval_provider = service_helpers.get_retrieval_provider()
        embedding_provider = get_embedding_provider(settings)
        context.analysis_provider = analysis_provider.name
        context.retrieval_provider = retrieval_provider.name
        context.embedding_provider = embedding_provider.name

        recorder.record("intake", "started")
        intake = self.intake_tool.extract(context)
        context.intake = intake
        recorder.record(
            "intake",
            "completed",
            {
                "inferred_use": intake.inferred_use,
                "missing_detail_count": len(intake.missing_details),
                "clarification_required": intake.clarification_required,
            },
        )

        recorder.record(
            "location",
            "completed" if district != "unknown" else "warning",
            {
                "jurisdiction_id": jurisdiction_id,
                "jurisdiction_name": jurisdiction_name,
                "district": district,
            },
        )

        retrieval_error: str | None = None
        retrieval_source_store = getattr(retrieval_provider, "source_store", None)
        source_readiness = (
            ensure_source_index_ready(retrieval_source_store)
            if retrieval_source_store
            else ensure_source_index_ready()
        )

        recorder.record("retrieval", "started")
        try:
            citations = retrieval_provider.retrieve(
                RetrievalProviderRequest(
                    district=district,
                    inferred_use=intake.inferred_use,
                    project_description=context.combined_description,
                    jurisdiction_id=jurisdiction_id,
                )
            ).citations
        except Exception as exc:
            citations = []
            retrieval_error = str(exc)
            recorder.record("retrieval", "failed", {"error": retrieval_error})
        else:
            recorder.record(
                "retrieval",
                "completed" if citations else "warning",
                {"citation_count": len(citations), "provider": retrieval_provider.name},
            )
        context.citations = citations

        confidence = service_helpers._confidence_score(intake.missing_details, citations)
        if not source_readiness.index_ready:
            confidence = max(0.1, min(confidence, 0.55))

        recorder.record("compliance", "started")
        compliance = self.compliance_tool.analyze(context, analysis_provider, citations)
        decision = compliance.decision
        summary = compliance.summary
        permits_override = compliance.permits_override
        follow_up = list(compliance.follow_up_questions)
        warnings = list(compliance.warnings)
        recorder.record(
            "compliance",
            "skipped" if not citations else ("warning" if compliance.warnings else "completed"),
            {
                "provider": analysis_provider.name,
                "used_model": compliance.used_model,
                "decision": decision,
            },
        )

        status = "success"
        stage_reports = self.report_tool.build_initial_stage_reports(
            intake=intake,
            district=district,
            jurisdiction_name=jurisdiction_name,
        )

        if retrieval_error:
            if retrieval_provider.name == "watsonx":
                warnings.append(f"watsonx retrieval failed: {retrieval_error}")
            else:
                warnings.append(f"Local source retrieval failed: {retrieval_error}")

        if not source_readiness.index_ready:
            warnings.extend(source_readiness.warnings)
            warnings.append("Source index readiness is incomplete; verify this result with the planning office.")

        retrieval_report = self.report_tool.build_retrieval_report(
            citations=citations,
            retrieval_provider_name=retrieval_provider.name,
            district=district,
            inferred_use=intake.inferred_use,
        )
        stage_reports.append(retrieval_report)

        if not citations:
            warnings.append(
                (
                    "No relevant ordinances were returned by watsonx retrieval for this request. Please contact the planning office."
                    if retrieval_provider.name == "watsonx"
                    else "No relevant ordinances were found in the current zoning source registry. Please contact the planning office."
                )
            )

        if intake.missing_details:
            status = "needs_clarification"
            follow_up.extend(intake.clarification_questions)
            stage_reports[0].status = "needs_clarification"
            stage_reports[0].headline = "The project brief needs a few more details before the zoning call is reliable."
            stage_reports[0].details.extend([f"Missing: {field}" for field in intake.missing_details])

        validation_source_store = (
            retrieval_source_store
            if retrieval_provider.name in {"source_registry", "hybrid_local"}
            else None
        )
        validation = CitationTool(validation_source_store).validate(
            citations=citations,
            jurisdiction_id=jurisdiction_id,
        )
        if not validation.valid or not citations:
            recorder.record(
                "citation_validation",
                "warning",
                {
                    "citation_coverage": validation.citation_coverage,
                    "unsupported_claim_count": len(validation.unsupported_claims),
                    "invalid_citation_ids": validation.invalid_citation_ids,
                },
            )
        else:
            recorder.record(
                "citation_validation",
                "completed",
                {"citation_coverage": validation.citation_coverage},
            )
        warnings.extend(validation.warnings)

        if confidence < 0.6 or not citations or district == "unknown":
            if status != "needs_clarification":
                status = "low_confidence"
            warnings.append("Confidence is low due to incomplete evidence or conflicting context.")
            warnings.append("Human-in-the-loop fallback: verify the parcel directly with the zoning or planning office.")

        checklist = self.report_tool.build_checklist(
            citations=citations,
            permits_override=permits_override,
        )
        deduped_follow_up = service_helpers._dedupe_follow_up_questions(follow_up)

        stage_reports.append(
            PipelineStageReport(
                key="compliance",
                label="Analyze Compliance",
                status=(
                    "warning"
                    if status == "low_confidence"
                    else ("needs_clarification" if status == "needs_clarification" else "completed")
                ),
                headline=summary,
                details=[
                    f"Decision: {decision}",
                    f"Confidence: {confidence:.2f}",
                    f"Citation coverage: {validation.citation_coverage:.2f}",
                ],
            )
        )
        stage_reports.append(
            PipelineStageReport(
                key="checklist",
                label="Generate Checklist",
                status="completed" if checklist.steps else "warning",
                headline="Prepared permit steps, required documents, and review departments.",
                details=[
                    f"Checklist steps: {len(checklist.steps)}",
                    f"Permits: {len(checklist.permits)}",
                    f"Warnings: {len(warnings)}",
                ],
            )
        )
        recorder.record("report", "completed")

        return AnalyzeResult(
            status=status,
            trace_id=context.trace_id,
            pipeline=PipelineMetadata(
                version=PIPELINE_VERSION,
                prompt_version=PROMPT_VERSION,
                provider=analysis_provider.name,
                rag_provider=retrieval_provider.name,
                embedding_provider=embedding_provider.name,
                trace_id=context.trace_id,
            ),
            citation_validation=validation,
            pipeline_stages=stage_reports,
            agents=stage_reports,
            feasibility=Feasibility(decision=decision, confidence=confidence, summary=summary),
            checklist=checklist,
            citations=citations,
            disclaimers=service_helpers.DISCLAIMER_TEXT,
            follow_up_questions=deduped_follow_up,
            warnings=warnings,
        )
