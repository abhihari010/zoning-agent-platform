from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.interfaces import AnalysisProviderRequest, RetrievalProviderRequest
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
