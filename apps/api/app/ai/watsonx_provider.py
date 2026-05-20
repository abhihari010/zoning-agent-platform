from __future__ import annotations

from typing import Any, cast

from app import watsonx_client
from app.ai.interfaces import (
    AnalysisProviderRequest,
    AnalysisProviderResult,
    RetrievalProviderRequest,
    RetrievalProviderResult,
)
from app.models import DecisionType, SourceCitation
from app.settings import require_watsonx_settings


VALID_DECISIONS: set[str] = {"likely_allowed", "conditional", "restricted", "unknown"}


def _citation_from_passage(passage: dict[str, Any], index: int) -> SourceCitation:
    text = passage.get("text") or passage.get("content") or passage.get("excerpt") or str(passage)
    title = passage.get("title") or passage.get("document_title") or "Blacksburg Code of Ordinances"
    section = passage.get("section_ref") or passage.get("section") or passage.get("chunk_id") or f"Sec {index + 1}"
    source_id = passage.get("source_id") or passage.get("id") or f"blacksburg-ordinance-{index + 1}"
    url = passage.get("url") or None
    return SourceCitation(
        source_id=str(source_id),
        title=str(title),
        excerpt=str(text),
        section_ref=str(section),
        url=url,
    )


class WatsonXRetrievalProvider:
    name = "watsonx"

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        require_watsonx_settings()
        passages = watsonx_client.search_ordinances(request.query)
        return RetrievalProviderResult(
            citations=[_citation_from_passage(passage, i) for i, passage in enumerate(passages[:5])]
        )


class WatsonXAnalysisProvider:
    name = "watsonx"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        require_watsonx_settings()
        model_output = watsonx_client.generate_watsonx_analysis(
            project_description=request.project_description,
            district=request.district,
            citation_excerpts=request.citation_excerpts,
            missing_fields=request.missing_fields,
        )
        decision = str(model_output.get("decision", "unknown"))
        if decision not in VALID_DECISIONS:
            decision = "unknown"

        return AnalysisProviderResult(
            decision=cast(DecisionType, decision),
            summary=str(model_output.get("summary", "Insufficient model summary.")),
            required_permits=[str(item) for item in model_output.get("required_permits", [])],
            follow_up_questions=[str(item) for item in model_output.get("follow_up_questions", [])],
            warnings=[str(item) for item in model_output.get("warnings", [])],
        )
