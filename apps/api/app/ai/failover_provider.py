from __future__ import annotations

import logging
from collections.abc import Sequence

from app.ai.interfaces import AnalysisProvider, AnalysisProviderRequest, AnalysisProviderResult

logger = logging.getLogger(__name__)

_DETAIL_LIMIT = 500


def _error_detail(exc: Exception) -> str:
    """Describe a provider failure including the HTTP response body.

    httpx's ``HTTPStatusError`` string stops at the status line, and the body is the
    only place the provider names what it actually rejected -- which model slug it no
    longer serves, which quota is exhausted. Without it a chain-wide 404 is
    indistinguishable from a chain-wide outage.
    """

    detail = str(exc)
    try:
        body = getattr(getattr(exc, "response", None), "text", "")
    except Exception:  # noqa: BLE001 - never let logging mask the original failure
        body = ""
    if body:
        detail = f"{detail} | body: {body}"
    return detail[:_DETAIL_LIMIT]


class FailoverAnalysisProvider:
    """Tries an ordered chain of analysis providers, advancing on failure.

    Production resilience: when the primary provider exhausts its retries (e.g. a
    sustained 429 / rate limit) and raises, the next provider in the chain is
    tried. The first success wins. If every provider fails, the last error is
    re-raised so the orchestrator's deterministic fallback still engages.

    This is intentionally NOT used for the eval gate — mixing providers within a
    run would break reproducibility. The eval pins a single provider; failover is
    enabled only when AI_PROVIDER_FALLBACKS is configured (production).
    """

    name = "failover"

    def __init__(self, providers: Sequence[AnalysisProvider]) -> None:
        if not providers:
            raise ValueError("FailoverAnalysisProvider requires at least one provider")
        self.providers = list(providers)
        self.name = "+".join(getattr(p, "name", "provider") for p in self.providers)

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        last_exc: Exception = RuntimeError("No providers attempted")
        for index, provider in enumerate(self.providers):
            provider_name = getattr(provider, "name", f"provider-{index}")
            try:
                return provider.generate_analysis(request)
            except Exception as exc:  # noqa: BLE001 - any failure should advance the chain
                last_exc = exc
                is_last = index == len(self.providers) - 1
                logger.warning(
                    "Analysis provider %r failed (%s: %s); %s",
                    provider_name,
                    type(exc).__name__,
                    _error_detail(exc),
                    "no fallbacks left" if is_last else "trying next fallback",
                )
        raise last_exc
