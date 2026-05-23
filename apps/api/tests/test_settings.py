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
        "VECTOR_PROVIDER",
        "CHROMA_PATH",
        "CHROMA_COLLECTION",
        "CHROMA_RESET_ON_REINDEX",
        "DATABASE_URL",
        "ZONING_DB_PATH",
        "IBM_ZONING_DB_PATH",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LOCAL_MODEL_BASE_URL",
        "LOCAL_MODEL_NAME",
        "LOCAL_MODEL_TIMEOUT_SECONDS",
        "WATSONX_ENABLED",
        "WATSONX_API_KEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_MODEL_ID",
        "WATSONX_VECTOR_INDEX_ID",
        "BETA_ACCESS_KEY",
        "BETA_ACCESS_KEYS",
        "ADMIN_ACCESS_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_settings_default_to_offline_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)

    settings = get_settings()

    assert settings.ai_provider == "deterministic"
    assert settings.rag_provider == "source_registry"
    assert settings.embedding_provider == "none"
    assert settings.vector_provider == "none"
    assert not settings.uses_watsonx
    assert not settings.uses_openai
    assert settings.beta_access_key == ""
    assert settings.local_model_base_url == "http://localhost:11434/v1"
    assert settings.local_model_name == "llama3.1:8b"


def test_settings_accepts_local_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "local-test-model")

    settings = get_settings()

    assert settings.ai_provider == "local"
    assert settings.uses_local_model
    assert settings.local_model_base_url == "http://localhost:1234/v1"
    assert settings.local_model_name == "local-test-model"


def test_settings_prefers_new_database_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ZONING_DB_PATH", "tmp/new.sqlite3")
    monkeypatch.setenv("IBM_ZONING_DB_PATH", "tmp/legacy.sqlite3")

    assert get_settings().database_path == Path("tmp/new.sqlite3")


def test_settings_reads_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@example.test:5432/zoning")

    assert get_settings().database_url == "postgres://user:pass@example.test:5432/zoning"


def test_settings_keeps_legacy_database_path_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("IBM_ZONING_DB_PATH", "tmp/legacy.sqlite3")

    assert get_settings().database_path == Path("tmp/legacy.sqlite3")


def test_settings_reads_beta_access_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("BETA_ACCESS_KEY", "secret-beta-key")

    settings = get_settings()

    assert settings.beta_access_key == "secret-beta-key"
    assert settings.beta_access_keys[0].label == "legacy"
    assert settings.beta_access_keys[0].key_hash != "secret-beta-key"


def test_settings_reads_labeled_beta_access_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("BETA_ACCESS_KEYS", "alice:alice-key,bob:bob-key")

    settings = get_settings()

    assert [key.label for key in settings.beta_access_keys] == ["alice", "bob"]
    assert all(key.key_hash not in {"alice-key", "bob-key"} for key in settings.beta_access_keys)


def test_settings_reads_admin_access_key_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "admin-key")

    settings = get_settings()

    assert settings.admin_access_key == "admin-key"
    assert settings.admin_access_key_hash
    assert settings.admin_access_key_hash != "admin-key"


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


def test_unknown_vector_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("VECTOR_PROVIDER", "mystery")

    with pytest.raises(ConfigurationError, match="VECTOR_PROVIDER must be one of"):
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
