from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.models import ComplianceFinding, ComplianceResult
from app.prompts import PromptRenderer
from app.settings import get_settings


COMPLIANCE_SCHEMA_JSON = json.dumps(
    {
        "feasibility": "feasible | conditional | infeasible | unknown",
        "confidence": "number from 0.0 to 1.0",
        "summary": "string",
        "findings": [
            {
                "category": "string",
                "status": "compliant | conditional | non_compliant | unknown",
                "summary": "string",
                "citation_ids": ["chunk_id"],
                "confidence": "number from 0.0 to 1.0",
            }
        ],
        "required_permits": ["string"],
        "permit_path": "by-right | special_use_permit | variance | unknown",
        "warnings": ["string"],
        "unresolved_questions": ["string"],
        "citation_chunk_ids": ["chunk_id"],
    },
    indent=2,
)


class LocalModelAnalysisProvider:
    name = "local"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = get_settings()
        headers = {"Content-Type": "application/json"}
        if settings.local_model_api_key:
            headers["Authorization"] = f"Bearer {settings.local_model_api_key}"

        chunks_json = json.dumps(_evidence_chunks(request), indent=2)
        rendered_prompt = PromptRenderer().render(
            "compliance_synthesis.md",
            project_description=request.project_description,
            district=request.district,
            inferred_use=request.inferred_use,
            chunks_json=chunks_json,
            compliance_schema_json=COMPLIANCE_SCHEMA_JSON,
        )
        response = httpx.post(
            f"{settings.local_model_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.local_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a zoning compliance drafting assistant. Return only compact JSON "
                            "matching the requested structured compliance schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": rendered_prompt,
                    },
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=settings.local_model_timeout_seconds,
        )
        response.raise_for_status()
        payload = json.loads(_extract_chat_content(response.json()))
        compliance = _compliance_from_payload(payload, request)
        decision = str(payload.get("decision", "unknown"))
        if decision == "unknown" and compliance.feasibility != "unknown":
            decision = _decision_from_feasibility(compliance.feasibility)
        if decision not in {"likely_allowed", "conditional", "restricted", "unknown"}:
            decision = "unknown"
        return AnalysisProviderResult(
            decision=decision,  # type: ignore[arg-type]
            summary=compliance.summary or str(payload.get("summary") or "Local model did not return a usable summary."),
            required_permits=compliance.required_permits,
            follow_up_questions=[str(item) for item in payload.get("follow_up_questions", [])],
            warnings=list(compliance.warnings),
            compliance=compliance,
        )


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("Local model response did not include choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("Local model response did not include message content")
    return content


def _evidence_chunks(request: AnalysisProviderRequest) -> list[dict[str, Any]]:
    if request.chunks:
        return [
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "title": chunk.title,
                "section_ref": chunk.section_ref,
                "chunk_text": chunk.chunk_text,
                "metadata": chunk.metadata,
            }
            for chunk in request.chunks
        ]
    return [
        {
            "chunk_id": f"excerpt-{index}",
            "chunk_text": excerpt,
        }
        for index, excerpt in enumerate(request.citation_excerpts)
    ]


def _compliance_from_payload(payload: dict[str, Any], request: AnalysisProviderRequest) -> ComplianceResult:
    raw = payload.get("compliance") if isinstance(payload.get("compliance"), dict) else payload
    if not isinstance(raw, dict):
        raw = {}
    allowed_ids = {chunk.chunk_id for chunk in request.chunks}
    warnings = [str(item) for item in raw.get("warnings", [])]
    citation_ids = [str(item) for item in raw.get("citation_chunk_ids", [])]
    invalid_ids = sorted({item for item in citation_ids if allowed_ids and item not in allowed_ids})
    if invalid_ids:
        warnings.append(f"Invalid citation IDs were removed: {', '.join(invalid_ids)}")
    valid_citation_ids = [item for item in citation_ids if not allowed_ids or item in allowed_ids]

    findings: list[ComplianceFinding] = []
    for item in raw.get("findings", []):
        if not isinstance(item, dict):
            continue
        finding_ids = [str(value) for value in item.get("citation_ids", [])]
        finding_ids = [value for value in finding_ids if not allowed_ids or value in allowed_ids]
        findings.append(
            ComplianceFinding(
                category=str(item.get("category") or "general"),
                status=_finding_status(str(item.get("status") or "unknown")),
                summary=str(item.get("summary") or ""),
                citation_ids=finding_ids,
                confidence=_confidence(item.get("confidence"), default=0.3),
            )
        )

    confidence = _confidence(raw.get("confidence"), default=0.3)
    if not valid_citation_ids and confidence > 0.3:
        confidence = 0.3
        warnings.append("Confidence capped because no valid citation IDs were supplied.")

    return ComplianceResult(
        feasibility=_feasibility(str(raw.get("feasibility") or "unknown")),
        confidence=confidence,
        summary=str(raw.get("summary") or payload.get("summary") or "Local model did not return a usable summary."),
        findings=findings,
        required_permits=[str(item) for item in raw.get("required_permits", payload.get("required_permits", []))],
        permit_path=str(raw.get("permit_path") or "unknown"),
        warnings=warnings,
        unresolved_questions=[str(item) for item in raw.get("unresolved_questions", [])],
        citation_chunk_ids=valid_citation_ids,
    )


def _confidence(value: Any, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _feasibility(value: str) -> str:
    return value if value in {"feasible", "conditional", "infeasible", "unknown"} else "unknown"


def _finding_status(value: str) -> str:
    return value if value in {"compliant", "conditional", "non_compliant", "unknown"} else "unknown"


def _decision_from_feasibility(value: str) -> str:
    return {
        "feasible": "likely_allowed",
        "conditional": "conditional",
        "infeasible": "restricted",
        "unknown": "unknown",
    }[value]
