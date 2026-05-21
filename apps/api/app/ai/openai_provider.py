from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.interfaces import (
    AnalysisProviderRequest,
    AnalysisProviderResult,
    EmbeddingProviderRequest,
    EmbeddingProviderResult,
)
from app.settings import require_openai_settings


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["likely_allowed", "conditional", "restricted", "unknown"],
        },
        "summary": {"type": "string"},
        "required_permits": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "decision",
        "summary",
        "required_permits",
        "follow_up_questions",
        "warnings",
    ],
}


class OpenAIAnalysisProvider:
    name = "openai"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = require_openai_settings()
        response = httpx.post(
            f"{settings.openai_base_url}/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "instructions": (
                    "You are a zoning compliance drafting assistant. Use only the supplied "
                    "citation excerpts and missing-field list. Do not invent citations."
                ),
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(
                                    {
                                        "project_description": request.project_description,
                                        "district": request.district,
                                        "citation_excerpts": request.citation_excerpts,
                                        "missing_fields": request.missing_fields,
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "zoning_analysis",
                        "schema": ANALYSIS_SCHEMA,
                        "strict": True,
                    }
                },
            },
            timeout=settings.openai_timeout_seconds,
        )
        response.raise_for_status()
        payload = json.loads(_extract_response_text(response.json()))
        return AnalysisProviderResult(
            decision=payload["decision"],
            summary=payload["summary"],
            required_permits=list(payload.get("required_permits", [])),
            follow_up_questions=list(payload.get("follow_up_questions", [])),
            warnings=list(payload.get("warnings", [])),
        )


class OpenAIEmbeddingProvider:
    name = "openai"

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        settings = require_openai_settings()
        if not request.texts:
            return EmbeddingProviderResult(embeddings=[])

        response = httpx.post(
            f"{settings.openai_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": request.texts,
                "encoding_format": "float",
            },
            timeout=settings.openai_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        embeddings = [item.get("embedding", []) for item in sorted(data, key=lambda item: item.get("index", 0))]
        return EmbeddingProviderResult(embeddings=embeddings)


def _extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]

    raise ValueError("OpenAI response did not include output text")
