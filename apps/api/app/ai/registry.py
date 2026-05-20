from __future__ import annotations

from dataclasses import dataclass

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.interfaces import AnalysisProvider, RetrievalProvider
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider
from app.ai.watsonx_provider import WatsonXAnalysisProvider, WatsonXRetrievalProvider
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


def get_analysis_provider(settings: Settings | None = None) -> AnalysisProvider:
    resolved = settings or get_settings()
    if resolved.ai_provider == "watsonx":
        return WatsonXAnalysisProvider()
    return DeterministicAnalysisProvider()


def get_retrieval_provider(settings: Settings | None = None) -> RetrievalProvider:
    resolved = settings or get_settings()
    if resolved.rag_provider == "watsonx":
        return WatsonXRetrievalProvider()
    return SourceRegistryRetrievalProvider()
