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
        "matched_use_term": {"type": "string"},
        "unlisted_use_determination": {"type": "boolean"},
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
                    f"HTTP {response.status_code}: {_error_detail(response)}",
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


def _error_detail(response: httpx.Response) -> str:
    """Return a short human-readable reason from an error response body.

    Gemini/OpenAI 429s carry the exceeded quota name (e.g. per-minute vs per-day)
    in the body; surfacing it turns an opaque 'HTTP 429' into an actionable warning.
    """
    try:
        message = response.json().get("error", {}).get("message", "")
    except Exception:
        message = ""
    if not message:
        message = response.text
    return message.strip().replace("\n", " ")[:300]


def _retry_after_seconds(response: httpx.Response) -> float:
    """Seconds to wait before the next retry.

    Prefers the Retry-After header (delta-seconds); falls back to Gemini's
    `retryDelay` hint inside error.details (e.g. "27s"). Returns 0.0 if neither
    is present.
    """
    raw = response.headers.get("retry-after", "")
    try:
        header_seconds = max(0.0, float(raw))
    except (TypeError, ValueError):
        header_seconds = 0.0
    if header_seconds:
        return header_seconds

    try:
        details = response.json().get("error", {}).get("details", [])
    except Exception:
        return 0.0
    for detail in details:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return max(0.0, float(delay[:-1]))
            except ValueError:
                continue
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
                            "You are a zoning compliance assistant. Given a project description "
                            "and citation excerpts from a jurisdiction's zoning ordinance, output "
                            "a JSON zoning analysis. Decide from the cited ordinance text — "
                            "especially any permitted-use table in the excerpts (e.g. a Subsection "
                            "5.1.3 'Permitted Principal Uses by Zoning District' table) — not from "
                            "prior knowledge.\n\n"
                            "STEP 0 — Is the proposed use classifiable from the table? A use is "
                            "classifiable ONLY if a row in the permitted-use table names it or "
                            "plainly and uncontroversially covers it (e.g. a clothing boutique is a "
                            "'Retail' use; an apartment building is 'Multifamily Residential'). A use "
                            "is NOT classifiable when matching it to a row would require a "
                            "similar-use determination — i.e. asserting the use is 'substantially "
                            "similar to' a listed use because no row actually describes it. Per "
                            "Subsection 5.1.1.C that determination may be made ONLY by the "
                            "jurisdiction (the Department of Building and Neighborhood Services with "
                            "Planning), never by you. Specialized production uses that are not named "
                            "— for example a brewery, distillery, or winery, even one with an "
                            "on-site taproom — are NOT classifiable; do NOT file them under 'Light "
                            "Industrial Uses', 'Heavy Industrial Uses', 'Restaurants', or any other "
                            "row. If the use is not classifiable, set unlisted_use_determination to "
                            "true, set decision to 'unknown', and stop. Otherwise set "
                            "unlisted_use_determination to false and continue.\n\n"
                            "STEP 1 — Identify the proposed principal use and the zoning district "
                            "from the project_description. If the 'district' field is 'unknown', "
                            "infer the district from the description: a named district (e.g. "
                            "'Downtown District', 'Neighborhood Commercial', 'the R3 district') or "
                            "a phrase like 'residential subdivision' or 'commercial corridor'. Map "
                            "district names to their codes using the district definitions in the "
                            "excerpts (e.g. Downtown District = DD, Neighborhood Commercial = NC, "
                            "Central Commercial = CC, Regional Commerce = RC4/RC6/RC12).\n\n"
                            "STEP 2 — Look the proposed use up in the permitted-use table in the "
                            "excerpts and read its status for the identified district. Set "
                            "matched_use_term to the exact row label you relied on (copied verbatim "
                            "from the table). Then apply the matching rule:\n"
                            "  • likely_allowed — the use is permitted by right in that district.\n"
                            "  • conditional — the use is permitted in that district subject to "
                            "additional use regulations (e.g. Subsection 5.1.4) or to "
                            "planning-commission / site-plan approval (e.g. Chapter 20 / §20.12). "
                            "Name the controlling provision in the summary and list the permits.\n"
                            "  • restricted — the use IS listed as a principal use in the table, "
                            "but the identified district is NOT among the districts permitted for "
                            "that use (i.e. not permitted there).\n\n"
                            "STEP 3 — unknown: use this when the corpus does not let you decide. "
                            "In particular, if the proposed use does not appear as a NAMED row in "
                            "the permitted-use table, return unknown — do NOT substitute a broader "
                            "category to force an answer (e.g. do not treat a 'brewery', "
                            "'distillery', 'brewpub', or other unlisted business as 'Light "
                            "Industrial Uses', 'Heavy Industrial Uses', or any other table row). "
                            "Reclassifying an unlisted use is a similar-use determination that only "
                            "the jurisdiction may make (Subsection 5.1.1.C), so the honest answer is "
                            "unknown. Also return unknown when the district cannot be determined, or "
                            "the excerpts contain no permitted-use information for the use. "
                            "Do not guess.\n\n"
                            "Output JSON with these fields: decision, summary, "
                            "required_permits (array), follow_up_questions (array), "
                            "warnings (array), matched_use_term (string), "
                            "unlisted_use_determination (boolean)."
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
                "temperature": 0,
            },
            timeout=settings.openai_timeout_seconds,
        )
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
        decision = result["decision"]
        warnings = list(result.get("warnings", []))
        # Enforce the Subsection 5.1.1.C invariant structurally: an unlisted use cannot
        # be classified by reclassifying it under a broader row (a similar-use determination
        # only the jurisdiction may make). If the model flags the use as unlisted, the honest
        # answer is unknown regardless of any row it may have reached for.
        if bool(result.get("unlisted_use_determination", False)) and decision != "unknown":
            decision = "unknown"
            warnings.append(
                "The proposed use is not a listed principal use in the permitted-use table; "
                "classifying it requires a Subsection 5.1.1.C similar-use determination made "
                "only by the jurisdiction, so no zoning conclusion can be drawn here."
            )
        return AnalysisProviderResult(
            decision=decision,
            summary=result["summary"],
            required_permits=list(result.get("required_permits", [])),
            follow_up_questions=list(result.get("follow_up_questions", [])),
            warnings=warnings,
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
