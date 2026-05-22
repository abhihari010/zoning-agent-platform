from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import ConfigurationError, get_settings, require_openai_settings, require_watsonx_settings


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "AI_PROVIDER",
        "RAG_PROVIDER",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "ZONING_DB_PATH",
        "IBM_ZONING_DB_PATH",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "WATSONX_ENABLED",
        "WATSONX_API_KEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_MODEL_ID",
        "WATSONX_VECTOR_INDEX_ID",
        "BETA_ACCESS_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_settings_default_to_offline_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)

    settings = get_settings()

    assert settings.ai_provider == "deterministic"
    assert settings.rag_provider == "source_registry"
    assert settings.embedding_provider == "none"
    assert not settings.uses_watsonx
    assert not settings.uses_openai
    assert settings.beta_access_key == ""


def test_settings_prefers_new_database_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ZONING_DB_PATH", "tmp/new.sqlite3")
    monkeypatch.setenv("IBM_ZONING_DB_PATH", "tmp/legacy.sqlite3")

    assert get_settings().database_path == Path("tmp/new.sqlite3")


def test_settings_keeps_legacy_database_path_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("IBM_ZONING_DB_PATH", "tmp/legacy.sqlite3")

    assert get_settings().database_path == Path("tmp/legacy.sqlite3")


def test_settings_reads_beta_access_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("BETA_ACCESS_KEY", "secret-beta-key")

    assert get_settings().beta_access_key == "secret-beta-key"


def test_unknown_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mystery")

    with pytest.raises(ConfigurationError, match="AI_PROVIDER must be one of"):
        get_settings()


def test_unknown_rag_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("RAG_PROVIDER", "mystery")

    with pytest.raises(ConfigurationError, match="RAG_PROVIDER must be one of"):
        get_settings()


def test_unknown_embedding_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mystery")

    with pytest.raises(ConfigurationError, match="EMBEDDING_PROVIDER must be one of"):
        get_settings()


def test_openai_credentials_only_required_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    require_openai_settings(get_settings())

    monkeypatch.setenv("AI_PROVIDER", "openai")
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        require_openai_settings(get_settings())


def test_watsonx_credentials_only_required_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    require_watsonx_settings(get_settings())

    monkeypatch.setenv("AI_PROVIDER", "watsonx")
    with pytest.raises(ConfigurationError, match="WATSONX_API_KEY"):
        require_watsonx_settings(get_settings())
