from __future__ import annotations

from uuid import uuid4

from sqlalchemy import inspect

from app.database import database_url_from_settings, normalize_database_url
from app.models import ProjectRecord, SourceRegistryEntry
from app.storage import SQLiteStore


def _sample_source(source_id: str = "rule-1") -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id=source_id,
        title="Zoning Rule",
        excerpt="Coffee shops require a zoning review with enough text to chunk.",
        full_text="FULL TEXT BODY " * 200,  # large body that must not load in the list
        section_ref="Sec. 1",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
    )


def test_list_source_summaries_omits_full_text(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "local.sqlite3")
    store.upsert_source(_sample_source("rule-1"))
    store.upsert_source(_sample_source("rule-2"))

    summaries = store.list_source_summaries()

    assert {s.source_id for s in summaries} == {"rule-1", "rule-2"}
    # full_text is stripped before validation; the validator backfills the small
    # excerpt, so it never carries the large body in the catalog list.
    for summary in summaries:
        assert "FULL TEXT BODY" not in (summary.full_text or "")
        assert summary.excerpt.startswith("Coffee shops")

    # The by-id fetch returns the complete source, including full_text.
    full = store.get_source("rule-1")
    assert full is not None
    assert "FULL TEXT BODY" in (full.full_text or "")
    assert store.get_source("missing") is None


def test_list_source_summaries_paginates(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "local.sqlite3")
    for index in range(5):
        store.upsert_source(_sample_source(f"rule-{index}"))

    # Ordered by source_id ascending; a page caps how many rows are built.
    first_page = store.list_source_summaries(limit=2, offset=0)
    assert [s.source_id for s in first_page] == ["rule-0", "rule-1"]

    second_page = store.list_source_summaries(limit=2, offset=2)
    assert [s.source_id for s in second_page] == ["rule-2", "rule-3"]

    # No limit returns every summary (used by the status metadata scan).
    assert len(store.list_source_summaries()) == 5


def test_source_and_chunk_counts(tmp_path) -> None:
    from app.ingestion import build_source_chunks

    store = SQLiteStore(tmp_path / "local.sqlite3")
    assert store.get_source_count() == 0
    assert store.get_source_chunk_count() == 0

    store.upsert_source(_sample_source("rule-1"))
    store.replace_source_chunks(build_source_chunks([_sample_source("rule-1")]))

    assert store.get_source_count() == 1
    assert store.get_source_chunk_count() >= 1


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
        "users",
        "usage_events",
        "usage_counters",
        "jurisdiction_requests",
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
