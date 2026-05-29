from __future__ import annotations

from dataclasses import dataclass

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.embedding_provider import DisabledEmbeddingProvider, GroqEmbeddingProvider, LocalHashEmbeddingProvider
from app.ai.groq_provider import GroqAnalysisProvider
from app.ai.hybrid_local_retriever import HybridLocalRetrievalProvider
from app.ai.interfaces import AnalysisProvider, EmbeddingProvider, RetrievalProvider
from app.ai.local_model_provider import LocalModelAnalysisProvider
from app.ai.openai_provider import OpenAIAnalysisProvider, OpenAIEmbeddingProvider
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class ProviderNames:
    analysis: str
    retrieval: str
    embedding: str


def configured_provider_names(settings: Settings | None = None) -> ProviderNames:
    resolved = settings or get_settings()
    return ProviderNames(
        analysis=resolved.ai_provider,
        retrieval=resolved.rag_provider,
        embedding=resolved.embedding_provider,
    )


def get_analysis_provider(settings: Settings | None = None) -> AnalysisProvider:
    resolved = settings or get_settings()
    if resolved.ai_provider == "openai":
        return OpenAIAnalysisProvider()
    if resolved.ai_provider == "groq":
        return GroqAnalysisProvider()
    if resolved.ai_provider == "local":
        return LocalModelAnalysisProvider()
    return DeterministicAnalysisProvider()


def get_retrieval_provider(settings: Settings | None = None) -> RetrievalProvider:
    resolved = settings or get_settings()
    if resolved.rag_provider == "hybrid_local":
        return HybridLocalRetrievalProvider(embedding_provider=get_embedding_provider(resolved))
    return SourceRegistryRetrievalProvider()


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved = settings or get_settings()
    if resolved.embedding_provider == "openai":
        return OpenAIEmbeddingProvider()
    if resolved.embedding_provider == "groq":
        return GroqEmbeddingProvider()
    if resolved.embedding_provider == "local":
        return LocalHashEmbeddingProvider()
    return DisabledEmbeddingProvider()
