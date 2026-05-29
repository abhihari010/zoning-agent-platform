from __future__ import annotations

import json
import time
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

# 429 is excluded: retrying rate-limit errors wastes quota and delays the deterministic fallback.
# Transient server errors (5xx) are still worth retrying.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_MAX_ATTEMPTS = 3


def _post_with_retry(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
    *,
    extra_retry_statuses: set[int] | None = None,
    max_attempts: int = _MAX_ATTEMPTS,
) -> dict[str, Any]:
    # Analysis (user-facing) path keeps the default behaviour: 429 is NOT retried so
    # we fail fast to the deterministic fallback. Batch paths (e.g. embedding reindex)
    # can opt into retrying 429 by passing extra_retry_statuses={429}.
    retry_statuses = _RETRYABLE_STATUS_CODES | (extra_retry_statuses or set())
    last_exc: Exception = RuntimeError("No attempts made")
    retry_after_seconds = 0.0
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(max(2**attempt, retry_after_seconds))
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=timeout)
            if response.status_code in retry_statuses:
                retry_after_seconds = _retry_after_seconds(response)
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
                continue
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            last_exc = exc
    raise RuntimeError(
        f"OpenAI request failed after {max_attempts} attempts: {last_exc}"
    ) from last_exc


def _retry_after_seconds(response: httpx.Response) -> float:
    """Parse a Retry-After header (delta-seconds form) into a float; 0.0 if absent."""
    raw = response.headers.get("retry-after", "")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


class OpenAIAnalysisProvider:
    name = "openai"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = require_openai_settings()
        payload = _post_with_retry(
            url=f"{settings.openai_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": settings.openai_model,
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
            timeout=settings.openai_timeout_seconds,
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


class OpenAIEmbeddingProvider:
    name = "openai"

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        settings = require_openai_settings()
        if not request.texts:
            return EmbeddingProviderResult(embeddings=[])

        payload = _post_with_retry(
            url=f"{settings.openai_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": settings.embedding_model,
                "input": request.texts,
                "encoding_format": "float",
            },
            timeout=settings.openai_timeout_seconds,
        )
        data = payload.get("data", [])
        embeddings = [
            item.get("embedding", [])
            for item in sorted(data, key=lambda item: item.get("index", 0))
        ]
        return EmbeddingProviderResult(embeddings=embeddings)
