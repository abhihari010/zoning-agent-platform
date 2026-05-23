from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.embedding_provider import LocalHashEmbeddingProvider
from app.ai.hybrid_local_retriever import HybridLocalRetrievalProvider
from app.ai.interfaces import AnalysisProviderRequest, EmbeddingProviderRequest, RetrievalProviderRequest
from app.ingestion import build_source_chunks
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider
from app.ai.watsonx_provider import WatsonXAnalysisProvider, WatsonXRetrievalProvider
from app.models import SourceRegistryEntry
from app.settings import ConfigurationError
from app.storage import SQLiteStore


def test_deterministic_provider_returns_offline_analysis() -> None:
    provider = DeterministicAnalysisProvider()

    result = provider.generate_analysis(
        AnalysisProviderRequest(
            project_description="Convert garage to bakery with employees and renovation plans.",
            district="mixed-use-core",
            citation_excerpts=[],
            missing_fields=[],
        )
    )

    assert result.decision == "conditional"
    assert "Garage-to-bakery" in result.summary


def test_source_registry_retriever_filters_by_district_and_use() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_provider_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="home-business",
                title="Home Business Rule",
                excerpt="Home occupation bakeries require review.",
                section_ref="Sec 1",
                districts=["mixed-use-core"],
                uses=["home-based-food-business"],
            )
        )
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="industrial",
                title="Industrial Rule",
                excerpt="Industrial use only.",
                section_ref="Sec 2",
                districts=["industrial-zone"],
                uses=["general"],
            )
        )

        result = SourceRegistryRetrievalProvider(source_store).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="home-based-food-business",
                project_description="garage bakery",
            )
        )

        assert [citation.source_id for citation in result.citations] == ["home-business"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_source_registry_retriever_scopes_citations_by_jurisdiction() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_provider_jurisdiction_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="blacksburg-home-business",
                title="Blacksburg Home Business Rule",
                excerpt="Blacksburg home occupation bakeries require review.",
                section_ref="Sec 1",
                jurisdiction_id="blacksburg-va",
                districts=["unknown"],
                uses=["home-based-food-business"],
            )
        )
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="montgomery-home-occupation",
                title="Montgomery County Home Occupation Rule",
                excerpt="Montgomery County home occupations require zoning, health, and inspections review.",
                section_ref="Home Occupations",
                jurisdiction_id="montgomery-county-va",
                districts=["unknown"],
                uses=["home-based-food-business"],
            )
        )

        result = SourceRegistryRetrievalProvider(source_store).retrieve(
            RetrievalProviderRequest(
                district="unknown",
                inferred_use="home-based-food-business",
                project_description="garage bakery",
                jurisdiction_id="montgomery-county-va",
            )
        )

        assert [citation.source_id for citation in result.citations] == ["montgomery-home-occupation"]
        assert all("Blacksburg" not in citation.title for citation in result.citations)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_local_embedding_provider_is_deterministic() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=8)

    first = provider.embed(EmbeddingProviderRequest(texts=["home bakery parking"])).embeddings[0]
    second = provider.embed(EmbeddingProviderRequest(texts=["home bakery parking"])).embeddings[0]

    assert first == second
    assert len(first) == 8


def test_hybrid_local_retriever_uses_indexed_chunks() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_hybrid_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="bakery-rule",
                title="Bakery Rule",
                excerpt="Home occupation bakeries require parking and fire review.",
                section_ref="Sec 10.2",
                districts=["mixed-use-core"],
                uses=["home-based-food-business"],
            )
        )
        source_store.replace_source_chunks(build_source_chunks(source_store.list_sources()))

        result = HybridLocalRetrievalProvider(
            source_store,
            embedding_provider=LocalHashEmbeddingProvider(),
        ).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="home-based-food-business",
                project_description="garage bakery parking",
            )
        )

        assert result.citations
        assert result.citations[0].source_id == "bakery-rule"
        assert "parking" in result.citations[0].excerpt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_watsonx_providers_require_credentials_by_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "AI_PROVIDER",
        "RAG_PROVIDER",
        "WATSONX_API_KEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_MODEL_ID",
        "WATSONX_VECTOR_INDEX_ID",
    ]:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("AI_PROVIDER", "watsonx")
    with pytest.raises(ConfigurationError):
        WatsonXAnalysisProvider().generate_analysis(
            AnalysisProviderRequest(
                project_description="Open a bakery.",
                district="mixed-use-core",
                citation_excerpts=[],
                missing_fields=[],
            )
        )

    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    monkeypatch.setenv("RAG_PROVIDER", "watsonx")
    with pytest.raises(ConfigurationError):
        WatsonXRetrievalProvider().retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="home-based-food-business",
                project_description="Open a bakery.",
            )
        )
