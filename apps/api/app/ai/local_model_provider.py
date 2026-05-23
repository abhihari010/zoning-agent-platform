from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.settings import get_settings


class LocalModelAnalysisProvider:
    name = "local"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = get_settings()
        headers = {"Content-Type": "application/json"}
        if settings.local_model_api_key:
            headers["Authorization"] = f"Bearer {settings.local_model_api_key}"

        response = httpx.post(
            f"{settings.local_model_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.local_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a zoning compliance drafting assistant. Use only the supplied "
                            "source excerpts. Do not invent citations. If evidence is missing, return unknown. "
                            "Return only compact JSON with keys decision, summary, required_permits, "
                            "follow_up_questions, and warnings."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "project_description": request.project_description,
                                "district": request.district,
                                "citation_excerpts": request.citation_excerpts,
                                "missing_fields": request.missing_fields,
                            }
                        ),
                    },
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=settings.local_model_timeout_seconds,
        )
        response.raise_for_status()
        payload = json.loads(_extract_chat_content(response.json()))
        decision = str(payload.get("decision", "unknown"))
        if decision not in {"likely_allowed", "conditional", "restricted", "unknown"}:
            decision = "unknown"
        return AnalysisProviderResult(
            decision=decision,  # type: ignore[arg-type]
            summary=str(payload.get("summary") or "Local model did not return a usable summary."),
            required_permits=[str(item) for item in payload.get("required_permits", [])],
            follow_up_questions=[str(item) for item in payload.get("follow_up_questions", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
        )


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("Local model response did not include choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("Local model response did not include message content")
    return content
