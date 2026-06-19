from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


AppEnvName = Literal["local", "staging", "production"]
AIProviderName = Literal["deterministic", "openai", "local", "groq"]
RAGProviderName = Literal["source_registry", "hybrid_local"]
EmbeddingProviderName = Literal["none", "local", "openai", "gemini"]
VectorProviderName = Literal["none", "qdrant"]

VALID_APP_ENVS: set[str] = {"local", "staging", "production"}
VALID_AI_PROVIDERS: set[str] = {"deterministic", "openai", "local", "groq"}
VALID_RAG_PROVIDERS: set[str] = {"source_registry", "hybrid_local"}
VALID_EMBEDDING_PROVIDERS: set[str] = {"none", "local", "openai", "gemini"}
VALID_VECTOR_PROVIDERS: set[str] = {"none", "qdrant"}

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "app.sqlite3"
PRODUCTION_FRONTEND_ORIGIN = "https://zoning-agent-platform.vercel.app"


class ConfigurationError(RuntimeError):
    """Raised when environment configuration is invalid."""


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _provider_name(name: str, default: str, valid_values: set[str]) -> str:
    value = _env(name, default).lower()
    if value not in valid_values:
        expected = ", ".join(sorted(valid_values))
        raise ConfigurationError(f"{name} must be one of: {expected}. Got: {value or '<empty>'}")
    return value


def _hash_access_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _parse_csv(raw_value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: AppEnvName
    ai_provider: AIProviderName
    rag_provider: RAGProviderName
    embedding_provider: EmbeddingProviderName
    vector_provider: VectorProviderName
    embedding_model: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    database_url: str
    database_path: Path
    google_maps_api_key: str
    google_maps_timeout_seconds: float
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    openai_timeout_seconds: float
    groq_api_key: str
    groq_model: str
    groq_timeout_seconds: float
    gemini_api_key: str
    gemini_embedding_model: str
    gemini_embedding_dimensions: int
    gemini_timeout_seconds: float
    gemini_embedding_batch_size: int
    gemini_embedding_request_interval_seconds: float
    local_model_base_url: str
    local_model_name: str
    local_model_timeout_seconds: float
    local_model_api_key: str
    admin_access_key: str
    admin_access_key_hash: str
    auth_provider: Literal["disabled", "supabase"]
    auth_required: bool
    supabase_project_url: str
    supabase_jwt_secret: str
    supabase_anon_key: str
    admin_user_emails: tuple[str, ...]
    public_signups_enabled: bool
    daily_analysis_limit_free: int
    daily_project_limit_free: int
    auto_seed_sources: bool
    auto_reindex_on_empty: bool
    startup_reindex_enabled: bool
    source_registry_version: str
    cors_allow_origins: tuple[str, ...]
    cors_allow_origin_regex: str
    # ---------------------------------------------------------------------------
    # Workstream A — Cache settings (appended; do not reorder above fields)
    # ---------------------------------------------------------------------------
    cache_enabled: bool = True
    cache_db_path: Path = Path("app/data/cache.sqlite3")
    cache_default_ttl: int = 3600  # seconds
    source_index_version: str = ""
    prompt_version: str = "1.0"
    # ---------------------------------------------------------------------------
    # Analysis-provider failover (production resilience). Ordered fallback names
    # tried when the primary analysis provider exhausts its retries. Empty by
    # default, so the eval gate (which never sets AI_PROVIDER_FALLBACKS) always
    # runs against a single pinned provider for reproducibility.
    # ---------------------------------------------------------------------------
    ai_provider_fallbacks: tuple[str, ...] = ()
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_timeout_seconds: float = 20.0
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 20.0

    @property
    def uses_openai(self) -> bool:
        return self.ai_provider == "openai" or self.embedding_provider == "openai"

    @property
    def uses_groq(self) -> bool:
        return self.ai_provider == "groq"

    @property
    def uses_local_model(self) -> bool:
        return self.ai_provider == "local"


def get_settings() -> Settings:
    database_url = _env("DATABASE_URL")
    database_path = _env("ZONING_DB_PATH") or _env("IBM_ZONING_DB_PATH")
    admin_access_key = _env("ADMIN_ACCESS_KEY")
    admin_user_emails = tuple(
        email.strip().lower()
        for email in _env("ADMIN_USER_EMAILS").split(",")
        if email.strip()
    )

    settings = Settings(
        app_env=cast(
            AppEnvName,
            _provider_name("APP_ENV", "local", VALID_APP_ENVS),
        ),
        ai_provider=cast(
            AIProviderName,
            _provider_name("AI_PROVIDER", "deterministic", VALID_AI_PROVIDERS),
        ),
        rag_provider=cast(
            RAGProviderName,
            _provider_name("RAG_PROVIDER", "source_registry", VALID_RAG_PROVIDERS),
        ),
        embedding_provider=cast(
            EmbeddingProviderName,
            _provider_name("EMBEDDING_PROVIDER", "none", VALID_EMBEDDING_PROVIDERS),
        ),
        vector_provider=cast(
            VectorProviderName,
            _provider_name("VECTOR_PROVIDER", "none", VALID_VECTOR_PROVIDERS),
        ),
        embedding_model=_env("EMBEDDING_MODEL", "text-embedding-3-small"),
        qdrant_url=_env("QDRANT_URL").rstrip("/"),
        qdrant_api_key=_env("QDRANT_API_KEY"),
        qdrant_collection=_env("QDRANT_COLLECTION", "zoning_source_chunks"),
        database_url=database_url,
        database_path=Path(database_path) if database_path else DEFAULT_DB_PATH,
        google_maps_api_key=_env("GOOGLE_MAPS_API_KEY"),
        google_maps_timeout_seconds=float(_env("GOOGLE_MAPS_TIMEOUT_SECONDS", "8")),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_timeout_seconds=float(_env("OPENAI_TIMEOUT_SECONDS", "20")),
        groq_api_key=_env("GROQ_API_KEY"),
        groq_model=_env("GROQ_MODEL", "llama-3.3-70b-versatile"),
        groq_timeout_seconds=float(_env("GROQ_TIMEOUT_SECONDS", "20")),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_embedding_model=_env("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        gemini_embedding_dimensions=int(_env("GEMINI_EMBEDDING_DIMENSIONS", "768")),
        gemini_timeout_seconds=float(_env("GEMINI_TIMEOUT_SECONDS", "20")),
        gemini_embedding_batch_size=int(_env("GEMINI_EMBEDDING_BATCH_SIZE", "32")),
        gemini_embedding_request_interval_seconds=float(
            _env("GEMINI_EMBEDDING_REQUEST_INTERVAL_SECONDS", "1.0")
        ),
        local_model_base_url=_env("LOCAL_MODEL_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        local_model_name=_env("LOCAL_MODEL_NAME", "llama3.1:8b"),
        local_model_timeout_seconds=float(_env("LOCAL_MODEL_TIMEOUT_SECONDS", "60")),
        local_model_api_key=_env("LOCAL_MODEL_API_KEY"),
        admin_access_key=admin_access_key,
        admin_access_key_hash=_hash_access_key(admin_access_key) if admin_access_key else "",
        auth_provider=cast(
            Literal["disabled", "supabase"],
            _provider_name("AUTH_PROVIDER", "disabled", {"disabled", "supabase"}),
        ),
        auth_required=_env_bool("AUTH_REQUIRED", False),
        supabase_project_url=_env("SUPABASE_PROJECT_URL").rstrip("/"),
        supabase_jwt_secret=_env("SUPABASE_JWT_SECRET"),
        supabase_anon_key=_env("SUPABASE_ANON_KEY"),
        admin_user_emails=admin_user_emails,
        public_signups_enabled=_env_bool("PUBLIC_SIGNUPS_ENABLED", True),
        daily_analysis_limit_free=int(_env("DAILY_ANALYSIS_LIMIT_FREE", "10")),
        daily_project_limit_free=int(_env("DAILY_PROJECT_LIMIT_FREE", "25")),
        auto_seed_sources=_env_bool("AUTO_SEED_SOURCES", True),
        auto_reindex_on_empty=_env_bool("AUTO_REINDEX_ON_EMPTY", True),
        startup_reindex_enabled=_env_bool("STARTUP_REINDEX_ENABLED", True),
        source_registry_version=_env("SOURCE_REGISTRY_VERSION"),
        cors_allow_origins=_parse_csv(_env("CORS_ALLOW_ORIGINS")),
        cors_allow_origin_regex=_env("CORS_ALLOW_ORIGIN_REGEX"),
        # Workstream A — cache settings
        cache_enabled=_env_bool("CACHE_ENABLED", True),
        cache_db_path=Path(_env("CACHE_DB_PATH")) if _env("CACHE_DB_PATH") else Path("app/data/cache.sqlite3"),
        cache_default_ttl=int(_env("CACHE_DEFAULT_TTL", "3600")),
        source_index_version=_env("SOURCE_INDEX_VERSION"),
        prompt_version=_env("PROMPT_VERSION", "1.0"),
        ai_provider_fallbacks=_parse_csv(_env("AI_PROVIDER_FALLBACKS").lower()),
        cerebras_api_key=_env("CEREBRAS_API_KEY"),
        cerebras_model=_env("CEREBRAS_MODEL", "llama-3.3-70b"),
        cerebras_base_url=_env("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/"),
        cerebras_timeout_seconds=float(_env("CEREBRAS_TIMEOUT_SECONDS", "20")),
        openrouter_api_key=_env("OPENROUTER_API_KEY"),
        openrouter_model=_env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        openrouter_base_url=_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        openrouter_timeout_seconds=float(_env("OPENROUTER_TIMEOUT_SECONDS", "20")),
    )
    validate_production_settings(settings)
    return settings


def validate_production_settings(settings: Settings) -> None:
    if settings.app_env != "production":
        return

    missing: list[str] = []
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if settings.auth_provider != "supabase":
        missing.append("AUTH_PROVIDER=supabase")
    if not settings.auth_required:
        missing.append("AUTH_REQUIRED=true")
    if not settings.supabase_project_url:
        missing.append("SUPABASE_PROJECT_URL")
    if not settings.supabase_jwt_secret:
        missing.append("SUPABASE_JWT_SECRET")
    if not settings.google_maps_api_key:
        missing.append("GOOGLE_MAPS_API_KEY")
    if settings.ai_provider == "openai" and not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if settings.ai_provider == "groq" and not settings.groq_api_key:
        missing.append("GROQ_API_KEY")
    if settings.embedding_provider == "gemini" and not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if settings.vector_provider == "qdrant" and not settings.qdrant_url:
        missing.append("QDRANT_URL")
    if "*" in settings.cors_allow_origins:
        missing.append("CORS_ALLOW_ORIGINS must not be *")
    if PRODUCTION_FRONTEND_ORIGIN not in settings.cors_allow_origins:
        missing.append(f"CORS_ALLOW_ORIGINS must include {PRODUCTION_FRONTEND_ORIGIN}")

    if missing:
        raise ConfigurationError(
            "Production configuration is incomplete: " + ", ".join(missing)
        )


def require_openai_settings(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    missing: list[str] = []

    if resolved.ai_provider == "openai":
        for name, value in {
            "OPENAI_API_KEY": resolved.openai_api_key,
            "OPENAI_MODEL": resolved.openai_model,
        }.items():
            if not value:
                missing.append(name)

    if resolved.embedding_provider == "openai":
        for name, value in {
            "OPENAI_API_KEY": resolved.openai_api_key,
            "EMBEDDING_MODEL": resolved.embedding_model,
        }.items():
            if not value:
                missing.append(name)

    if missing:
        missing_list = ", ".join(dict.fromkeys(missing))
        raise ConfigurationError(f"Missing required OpenAI setting(s): {missing_list}")

    return resolved
