from __future__ import annotations

import json

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.ai.openai_provider import _post_with_retry
from app.settings import get_settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqAnalysisProvider:
    name = "groq"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = get_settings()
        payload = _post_with_retry(
            url=f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": settings.groq_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a zoning compliance drafting assistant. Use only the supplied "
                            "citation excerpts and missing-field list. Do not invent citations.\n\n"
                            "Respond with a JSON object containing exactly these fields:\n"
                            '  "decision": one of "likely_allowed", "conditional", "restricted", "unknown"\n'
                            '  "summary": string\n'
                            '  "required_permits": array of strings\n'
                            '  "follow_up_questions": array of strings\n'
                            '  "warnings": array of strings'
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
                "response_format": {"type": "json_object"},
            },
            timeout=settings.groq_timeout_seconds,
        )
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
        return AnalysisProviderResult(
            decision=result["decision"],
            summary=result["summary"],
            required_permits=list(result.get("required_permits", [])),
            follow_up_questions=list(result.get("follow_up_questions", [])),
            warnings=list(result.get("warnings", [])),
        )
