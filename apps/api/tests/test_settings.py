from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import ConfigurationError, get_settings, require_openai_settings


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "AI_PROVIDER",
        "APP_ENV",
        "RAG_PROVIDER",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "VECTOR_PROVIDER",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_COLLECTION",
        "DATABASE_URL",
        "ZONING_DB_PATH",
        "IBM_ZONING_DB_PATH",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LOCAL_MODEL_BASE_URL",
        "LOCAL_MODEL_NAME",
        "LOCAL_MODEL_TIMEOUT_SECONDS",
        "ADMIN_ACCESS_KEY",
        "AUTH_PROVIDER",
        "AUTH_REQUIRED",
        "SUPABASE_PROJECT_URL",
        "SUPABASE_JWT_SECRET",
        "CORS_ALLOW_ORIGINS",
        "ADMIN_USER_EMAILS",
        "PUBLIC_SIGNUPS_ENABLED",
        "DAILY_ANALYSIS_LIMIT_FREE",
        "DAILY_PROJECT_LIMIT_FREE",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_settings_default_to_offline_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)

    settings = get_settings()

    assert settings.ai_provider == "deterministic"
    assert settings.app_env == "local"
    assert settings.rag_provider == "source_registry"
    assert settings.embedding_provider == "none"
    assert settings.vector_provider == "none"
    assert not settings.uses_openai
    assert settings.auth_provider == "disabled"
    assert settings.auth_required is False
    assert settings.daily_analysis_limit_free == 10
    assert settings.daily_project_limit_free == 25
    assert settings.local_model_base_url == "http://localhost:11434/v1"
    assert settings.local_model_name == "llama3.1:8b"


def test_production_settings_require_public_beta_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ConfigurationError, match="Production configuration is incomplete"):
        get_settings()


def test_production_settings_accept_required_public_beta_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@example.test:5432/zoning")
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "maps-key")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://zoning-agent-platform.vercel.app")

    settings = get_settings()

    assert settings.app_env == "production"
    assert settings.cors_allow_origins == ("https://zoning-agent-platform.vercel.app",)


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


def test_settings_reads_admin_access_key_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "admin-key")

    settings = get_settings()

    assert settings.admin_access_key == "admin-key"
    assert settings.admin_access_key_hash
    assert settings.admin_access_key_hash != "admin-key"


def test_settings_reads_public_auth_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("ADMIN_USER_EMAILS", "Admin@Example.com, ops@example.com")
    monkeypatch.setenv("PUBLIC_SIGNUPS_ENABLED", "false")
    monkeypatch.setenv("DAILY_ANALYSIS_LIMIT_FREE", "3")
    monkeypatch.setenv("DAILY_PROJECT_LIMIT_FREE", "4")

    settings = get_settings()

    assert settings.auth_provider == "supabase"
    assert settings.auth_required is True
    assert settings.supabase_project_url == "https://example.supabase.co"
    assert settings.supabase_jwt_secret == "jwt-secret"
    assert settings.admin_user_emails == ("admin@example.com", "ops@example.com")
    assert settings.public_signups_enabled is False
    assert settings.daily_analysis_limit_free == 3
    assert settings.daily_project_limit_free == 4


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


