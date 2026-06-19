from __future__ import annotations

from dataclasses import dataclass

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.embedding_provider import DisabledEmbeddingProvider, GeminiEmbeddingProvider, LocalHashEmbeddingProvider
from app.ai.failover_provider import FailoverAnalysisProvider
from app.ai.groq_provider import GroqAnalysisProvider
from app.ai.hybrid_local_retriever import HybridLocalRetrievalProvider
from app.ai.interfaces import AnalysisProvider, EmbeddingProvider, RetrievalProvider
from app.ai.local_model_provider import LocalModelAnalysisProvider
from app.ai.openai_compatible import OpenAICompatibleAnalysisProvider
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


def _build_named_analysis_provider(name: str, settings: Settings) -> AnalysisProvider | None:
    """Resolve an analysis provider by config name.

    Returns None when the named provider cannot be used as-is (e.g. a Cerebras /
    OpenRouter fallback with no API key configured), so callers can skip it.
    """
    if name == "openai":
        return OpenAIAnalysisProvider()
    if name == "groq":
        return GroqAnalysisProvider()
    if name == "local":
        return LocalModelAnalysisProvider()
    if name == "deterministic":
        return DeterministicAnalysisProvider()
    if name == "cerebras":
        if not settings.cerebras_api_key:
            return None
        return OpenAICompatibleAnalysisProvider(
            name="cerebras",
            base_url=settings.cerebras_base_url,
            api_key=settings.cerebras_api_key,
            model=settings.cerebras_model,
            timeout=settings.cerebras_timeout_seconds,
        )
    if name == "openrouter":
        if not settings.openrouter_api_key:
            return None
        return OpenAICompatibleAnalysisProvider(
            name="openrouter",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            timeout=settings.openrouter_timeout_seconds,
        )
    return None


def get_analysis_provider(settings: Settings | None = None) -> AnalysisProvider:
    resolved = settings or get_settings()
    primary = _build_named_analysis_provider(resolved.ai_provider, resolved)
    if primary is None:
        primary = DeterministicAnalysisProvider()

    # Failover is production-only resilience: it activates solely when
    # AI_PROVIDER_FALLBACKS is set. The eval gate never sets it, so eval always
    # runs against the single pinned primary provider (reproducible).
    fallbacks: list[AnalysisProvider] = []
    for name in resolved.ai_provider_fallbacks:
        if name == resolved.ai_provider:
            continue  # never duplicate the primary in the chain
        provider = _build_named_analysis_provider(name, resolved)
        if provider is not None:
            fallbacks.append(provider)

    if fallbacks:
        return FailoverAnalysisProvider([primary, *fallbacks])
    return primary


def get_retrieval_provider(settings: Settings | None = None) -> RetrievalProvider:
    resolved = settings or get_settings()
    if resolved.rag_provider == "hybrid_local":
        return HybridLocalRetrievalProvider(embedding_provider=get_embedding_provider(resolved))
    return SourceRegistryRetrievalProvider()


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved = settings or get_settings()
    if resolved.embedding_provider == "openai":
        return OpenAIEmbeddingProvider()
    if resolved.embedding_provider == "gemini":
        return GeminiEmbeddingProvider()
    if resolved.embedding_provider == "local":
        return LocalHashEmbeddingProvider()
    return DisabledEmbeddingProvider()
