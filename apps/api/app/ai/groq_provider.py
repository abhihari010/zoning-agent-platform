from __future__ import annotations

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.ai.openai_compatible import OpenAICompatibleAnalysisProvider
from app.settings import get_settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqAnalysisProvider:
    name = "groq"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = get_settings()
        # Groq free-tier hits 429s on per-minute limits; retry with backoff so the
        # deterministic fallback isn't silently engaged on transient limits.
        return OpenAICompatibleAnalysisProvider(
            name="groq",
            base_url=GROQ_BASE_URL,
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            timeout=settings.groq_timeout_seconds,
            extra_retry_statuses=frozenset({429}),
            max_attempts=6,
        ).generate_analysis(request)
