from __future__ import annotations

from uuid import uuid4

from sqlalchemy import inspect

from app.database import database_url_from_settings, normalize_database_url
from app.models import ProjectRecord
from app.storage import SQLiteStore


def test_normalize_database_url_selects_psycopg_for_render_postgres_urls() -> None:
    assert (
        normalize_database_url("postgres://user:pass@example.test:5432/zoning")
        == "postgresql+psycopg://user:pass@example.test:5432/zoning"
    )
    assert (
        normalize_database_url("postgresql://user:pass@example.test:5432/zoning")
        == "postgresql+psycopg://user:pass@example.test:5432/zoning"
    )


def test_database_url_from_settings_prefers_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@example.test:5432/zoning")

    assert database_url_from_settings() == "postgresql+psycopg://user:pass@example.test:5432/zoning"


def test_sqlite_store_creates_foundation_tables_for_local_fallback(tmp_path) -> None:
    source_store = SQLiteStore(tmp_path / "local.sqlite3")

    table_names = set(inspect(source_store.engine).get_table_names())

    assert {
        "sessions",
        "projects",
        "analyses",
        "audit_events",
        "feedback",
        "sources",
        "source_chunks",
        "beta_access_events",
        "jurisdictions",
    }.issubset(table_names)


def test_sqlite_store_preserves_project_round_trip(tmp_path) -> None:
    source_store = SQLiteStore(tmp_path / "local.sqlite3")
    project = ProjectRecord(
        session_id=uuid4(),
        project_description="Convert garage to bakery with two employees and set operating hours.",
        input_address="123 Main St",
        normalized_address="123 Main St, Blacksburg, VA",
        district="mixed-use-core",
        jurisdiction_id="blacksburg-va",
    )

    source_store.create_project(project)
    loaded = source_store.get_project(project.project_id)

    assert loaded == project
