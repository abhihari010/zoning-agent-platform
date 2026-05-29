from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine

from app.settings import Settings, get_settings


metadata = MetaData()


sessions = Table(
    "sessions",
    metadata,
    Column("session_id", String(36), primary_key=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("user_id", String(200), primary_key=True),
    Column("email", String(500), nullable=True, index=True),
    Column("role", String(50), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
)

projects = Table(
    "projects",
    metadata,
    Column("project_id", String(36), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("project_description", Text, nullable=True),
    Column("input_address", Text, nullable=True),
    Column("normalized_address", Text, nullable=True),
    Column("district", String(200), nullable=True),
    Column("jurisdiction_id", String(200), nullable=True, index=True),
    Column("jurisdiction_name", String(500), nullable=True),
    Column("place_id", String(500), nullable=True),
    Column("latitude", Float, nullable=True),
    Column("longitude", Float, nullable=True),
    Column("status", String(50), nullable=False),
    Column("legal_ack_at", DateTime(timezone=True), nullable=True),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

analyses = Table(
    "analyses",
    metadata,
    Column("project_id", String(36), ForeignKey("projects.project_id"), primary_key=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", String(200), nullable=False, index=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("stage", String(200), nullable=False, index=True),
    Column("details_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

feedback = Table(
    "feedback",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", String(36), ForeignKey("projects.project_id"), nullable=False, index=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("helpful", Boolean, nullable=False),
    Column("comment", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sources = Table(
    "sources",
    metadata,
    Column("source_id", String(200), primary_key=True),
    Column("title", String(500), nullable=False),
    Column("section_ref", String(200), nullable=False),
    Column("jurisdiction_id", String(200), nullable=True, index=True),
    Column("url", String(2000), nullable=True),
    Column("effective_date", String(50), nullable=True),
    Column("source_type", String(200), nullable=True),
    Column("retrieved_at", String(80), nullable=True),
    Column("source_version", String(120), nullable=True),
    Column("content_hash", String(64), nullable=True),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

source_chunks = Table(
    "source_chunks",
    metadata,
    Column("chunk_id", String(240), primary_key=True),
    Column("source_id", String(200), ForeignKey("sources.source_id"), nullable=False, index=True),
    Column("chunk_index", Integer, nullable=False),
    Column("source_text_hash", String(64), nullable=False),
    Column("jurisdiction_id", String(200), nullable=True, index=True),
    Column("source_type", String(200), nullable=True),
    Column("source_version", String(120), nullable=True),
    Column("districts_csv", String(2000), nullable=True),
    Column("uses_csv", String(2000), nullable=True),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

beta_access_events = Table(
    "beta_access_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key_label", String(200), nullable=True),
    Column("outcome", String(50), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

usage_events = Table(
    "usage_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("event_type", String(100), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

usage_counters = Table(
    "usage_counters",
    metadata,
    Column("user_id", String(200), nullable=False),
    Column("event_type", String(100), nullable=False),
    Column("usage_date", Date, nullable=False),
    Column("usage_count", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("user_id", "event_type", "usage_date", name="uq_usage_counters_daily"),
)

jurisdictions = Table(
    "jurisdictions",
    metadata,
    Column("jurisdiction_id", String(200), primary_key=True),
    Column("name", String(500), nullable=False),
    Column("state", String(100), nullable=True),
    Column("state_fips", String(10), nullable=True),
    Column("county_fips", String(10), nullable=True),
    Column("place_fips", String(10), nullable=True),
    Column("jurisdiction_type", String(50), nullable=False, default="unknown"),
    Column("parent_jurisdiction_id", String(200), nullable=True, index=True),
    Column("coverage_status", String(50), nullable=False, default="unsupported", index=True),
    Column("supported", Boolean, nullable=False, default=False),
    Column("official_source_urls_json", JSON, nullable=True),
    Column("zoning_map_url", String(2000), nullable=True),
    Column("planning_contact_json", JSON, nullable=True),
    Column("last_verified_at", String(80), nullable=True),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

jurisdiction_requests = Table(
    "jurisdiction_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(200), nullable=True, index=True),
    Column("jurisdiction_id", String(200), nullable=True, index=True),
    Column("jurisdiction_name", String(500), nullable=True),
    Column("state", String(100), nullable=True),
    Column("county", String(200), nullable=True),
    Column("locality", String(200), nullable=True),
    Column("normalized_address", Text, nullable=False),
    Column("requested_use_type", String(200), nullable=True),
    Column("comment", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def sqlite_url_from_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    return f"sqlite:///{resolved.as_posix()}"


def database_url_from_settings(settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    if resolved.database_url:
        return normalize_database_url(resolved.database_url)
    return sqlite_url_from_path(resolved.database_path)


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:")


def create_engine_for_url(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if is_sqlite_url(url) else {}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def create_database_engine(settings: Settings | None = None) -> Engine:
    return create_engine_for_url(database_url_from_settings(settings))
