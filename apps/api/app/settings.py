from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


AIProviderName = Literal["deterministic", "openai", "watsonx"]
RAGProviderName = Literal["source_registry", "hybrid_local", "watsonx"]
EmbeddingProviderName = Literal["none", "local", "openai"]

VALID_AI_PROVIDERS: set[str] = {"deterministic", "openai", "watsonx"}
VALID_RAG_PROVIDERS: set[str] = {"source_registry", "hybrid_local", "watsonx"}
VALID_EMBEDDING_PROVIDERS: set[str] = {"none", "local", "openai"}

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "app.sqlite3"


class ConfigurationError(RuntimeError):
    """Raised when environment configuration is invalid."""


@dataclass(frozen=True)
class AccessKey:
    label: str
    key_hash: str


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


def _parse_labeled_access_keys(raw_value: str) -> tuple[AccessKey, ...]:
    keys: list[AccessKey] = []
    for index, entry in enumerate(raw_value.split(","), start=1):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            label, key = entry.split(":", 1)
            label = label.strip()
            key = key.strip()
        else:
            label = f"beta-{index}"
            key = entry
        if not key:
            raise ConfigurationError("BETA_ACCESS_KEYS entries must include a non-empty key")
        keys.append(AccessKey(label=label or f"beta-{index}", key_hash=_hash_access_key(key)))
    return tuple(keys)


@dataclass(frozen=True)
class Settings:
    ai_provider: AIProviderName
    rag_provider: RAGProviderName
    embedding_provider: EmbeddingProviderName
    embedding_model: str
    database_url: str
    database_path: Path
    google_maps_api_key: str
    google_maps_timeout_seconds: float
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    openai_timeout_seconds: float
    watsonx_api_key: str
    watsonx_url: str
    watsonx_project_id: str
    watsonx_model_id: str
    watsonx_vector_index_id: str
    watsonx_timeout_seconds: float
    beta_access_key: str
    beta_access_keys: tuple[AccessKey, ...]
    admin_access_key: str
    admin_access_key_hash: str
    auto_seed_sources: bool
    auto_reindex_on_empty: bool
    source_registry_version: str

    @property
    def uses_watsonx(self) -> bool:
        return self.ai_provider == "watsonx" or self.rag_provider == "watsonx"

    @property
    def uses_openai(self) -> bool:
        return self.ai_provider == "openai" or self.embedding_provider == "openai"


def get_settings() -> Settings:
    legacy_watsonx_enabled = _env("WATSONX_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    default_ai_provider = "watsonx" if legacy_watsonx_enabled else "deterministic"
    default_rag_provider = "watsonx" if legacy_watsonx_enabled else "source_registry"
    database_url = _env("DATABASE_URL")
    database_path = _env("ZONING_DB_PATH") or _env("IBM_ZONING_DB_PATH")
    beta_access_key = _env("BETA_ACCESS_KEY")
    beta_access_keys = (
        (AccessKey(label="legacy", key_hash=_hash_access_key(beta_access_key)),)
        if beta_access_key
        else ()
    ) + _parse_labeled_access_keys(_env("BETA_ACCESS_KEYS"))
    admin_access_key = _env("ADMIN_ACCESS_KEY")

    return Settings(
        ai_provider=cast(
            AIProviderName,
            _provider_name("AI_PROVIDER", default_ai_provider, VALID_AI_PROVIDERS),
        ),
        rag_provider=cast(
            RAGProviderName,
            _provider_name("RAG_PROVIDER", default_rag_provider, VALID_RAG_PROVIDERS),
        ),
        embedding_provider=cast(
            EmbeddingProviderName,
            _provider_name("EMBEDDING_PROVIDER", "none", VALID_EMBEDDING_PROVIDERS),
        ),
        embedding_model=_env("EMBEDDING_MODEL", "text-embedding-3-small"),
        database_url=database_url,
        database_path=Path(database_path) if database_path else DEFAULT_DB_PATH,
        google_maps_api_key=_env("GOOGLE_MAPS_API_KEY"),
        google_maps_timeout_seconds=float(_env("GOOGLE_MAPS_TIMEOUT_SECONDS", "8")),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_timeout_seconds=float(_env("OPENAI_TIMEOUT_SECONDS", "20")),
        watsonx_api_key=_env("WATSONX_API_KEY"),
        watsonx_url=_env("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").rstrip("/"),
        watsonx_project_id=_env("WATSONX_PROJECT_ID"),
        watsonx_model_id=_env("WATSONX_MODEL_ID"),
        watsonx_vector_index_id=_env("WATSONX_VECTOR_INDEX_ID"),
        watsonx_timeout_seconds=float(_env("WATSONX_TIMEOUT_SECONDS", "20")),
        beta_access_key=beta_access_key,
        beta_access_keys=beta_access_keys,
        admin_access_key=admin_access_key,
        admin_access_key_hash=_hash_access_key(admin_access_key) if admin_access_key else "",
        auto_seed_sources=_env_bool("AUTO_SEED_SOURCES", True),
        auto_reindex_on_empty=_env_bool("AUTO_REINDEX_ON_EMPTY", True),
        source_registry_version=_env("SOURCE_REGISTRY_VERSION"),
    )


def require_watsonx_settings(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    missing: list[str] = []

    if resolved.ai_provider == "watsonx":
        for name, value in {
            "WATSONX_API_KEY": resolved.watsonx_api_key,
            "WATSONX_URL": resolved.watsonx_url,
            "WATSONX_PROJECT_ID": resolved.watsonx_project_id,
            "WATSONX_MODEL_ID": resolved.watsonx_model_id,
        }.items():
            if not value:
                missing.append(name)

    if resolved.rag_provider == "watsonx":
        for name, value in {
            "WATSONX_API_KEY": resolved.watsonx_api_key,
            "WATSONX_PROJECT_ID": resolved.watsonx_project_id,
            "WATSONX_VECTOR_INDEX_ID": resolved.watsonx_vector_index_id,
        }.items():
            if not value:
                missing.append(name)

    if missing:
        missing_list = ", ".join(dict.fromkeys(missing))
        raise ConfigurationError(f"Missing required WatsonX setting(s): {missing_list}")

    return resolved


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
