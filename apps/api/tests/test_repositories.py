from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest

from app.database import normalize_database_url
from app.models import (
    AnalysisRecord,
    AnalyzeResult,
    Checklist,
    Feasibility,
    FeedbackRecord,
    ProjectRecord,
    SourceChunk,
    SourceRegistryEntry,
)
from app.repositories import SQLAlchemyStore, StoreRepository


def _repository_cases(tmp_path) -> Iterator[tuple[str, StoreRepository]]:
    yield "sqlite", SQLAlchemyStore(tmp_path / "repository.sqlite3")

    test_database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if test_database_url:
        yield "postgres", SQLAlchemyStore(
            database_url=normalize_database_url(test_database_url),
            create_schema=True,
        )


@pytest.mark.parametrize("case_name", ["sqlite", "postgres"])
def test_repository_round_trips_current_storage_operations(tmp_path, case_name: str) -> None:
    repositories = dict(_repository_cases(tmp_path))
    if case_name not in repositories:
        pytest.skip("TEST_DATABASE_URL is not configured")

    repository = repositories[case_name]
    repository.reset()

    project = ProjectRecord(
        session_id=uuid4(),
        project_description="Convert garage to bakery with two employees and set operating hours.",
        input_address="300 Turner St NW",
        normalized_address="300 Turner St NW, Blacksburg, VA 24060, USA",
        district="mixed-use-core",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
        place_id="place-123",
        latitude=37.2296,
        longitude=-80.4139,
    )
    source = SourceRegistryEntry(
        source_id="blacksburg-home-occupation",
        title="Blacksburg Home Occupation Rules",
        excerpt="Home occupations may require zoning review when customers or employees visit.",
        section_ref="Sec. 4.2.2",
        jurisdiction_id="blacksburg-va",
        url="https://www.blacksburg.gov/",
        effective_date="2026-01-01",
        districts=["mixed-use-core"],
        uses=["home-based-food-business"],
    )
    chunk = SourceChunk(
        chunk_id="blacksburg-home-occupation:0",
        source_id=source.source_id,
        title=source.title,
        chunk_text=source.excerpt,
        chunk_index=0,
        source_text_hash="a" * 64,
        section_ref=source.section_ref,
        jurisdiction_id=source.jurisdiction_id,
        url=source.url,
        effective_date=source.effective_date,
        districts=source.districts,
        uses=source.uses,
    )
    analysis = AnalysisRecord(
        project_id=project.project_id,
        result=AnalyzeResult(
            status="success",
            trace_id="trace-123",
            feasibility=Feasibility(
                decision="conditional",
                confidence=0.82,
                summary="Likely conditional with planning review.",
            ),
            checklist=Checklist(steps=[], permits=["Zoning Permit"], documents=[], departments=[]),
            citations=[],
            disclaimers=[],
            follow_up_questions=[],
            warnings=[],
        ),
    )

    assert repository.create_project(project) == project
    assert repository.get_project(project.project_id) == project

    assert repository.upsert_source(source) == source
    assert repository.list_sources() == [source]
    assert repository.get_source_count() == 1

    assert repository.replace_source_chunks([chunk]) == [chunk]
    assert repository.list_source_chunks() == [chunk]
    assert repository.get_source_chunk_count() == 1

    assert repository.save_analysis(analysis) == analysis
    assert repository.get_analysis(project.project_id) == analysis
    analyzed_project = repository.get_project(project.project_id)
    assert analyzed_project is not None
    assert analyzed_project.status == "analyzed"

    feedback = FeedbackRecord(
        project_id=project.project_id,
        helpful=True,
        comment="The checklist is clear.",
    )
    assert repository.save_feedback(feedback) == feedback

    repository.audit(
        "pipeline.intake.completed",
        str(project.project_id),
        {"inferred_use": "home-based-food-business"},
    )
    repository.audit("source.reindex.completed", "source-registry")
    assert repository.get_latest_audit_timestamp("source.reindex.completed") is not None

    events = repository.get_audit_events(project.project_id)
    stages = [event.stage for event in events]
    assert stages == [
        "project.created",
        "analysis.saved",
        "feedback.saved",
        "pipeline.intake.completed",
    ]
    assert events[-1].details == {"inferred_use": "home-based-food-business"}
