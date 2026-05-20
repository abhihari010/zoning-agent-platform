from __future__ import annotations

from dataclasses import dataclass

from app.settings import Settings, get_settings


@dataclass(frozen=True)
class ProviderNames:
    analysis: str
    retrieval: str


def configured_provider_names(settings: Settings | None = None) -> ProviderNames:
    resolved = settings or get_settings()
    return ProviderNames(
        analysis=resolved.ai_provider,
        retrieval=resolved.rag_provider,
    )
