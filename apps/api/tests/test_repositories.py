from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.database import normalize_database_url
from app.models import (
    AnalysisRecord,
    AnalyzeResult,
    Checklist,
    Feasibility,
    FeedbackRecord,
    JurisdictionRecord,
    JurisdictionRequestCreate,
    ProjectRecord,
    SourceChunk,
    SourceRegistryEntry,
    UserRecord,
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
        user_id="user-1",
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
        user_id="user-1",
    )
    assert repository.save_feedback(feedback) == feedback

    user = UserRecord(user_id="user-1", email="user@example.com", role="user")
    assert repository.upsert_user(user).user_id == "user-1"
    assert repository.get_user("user-1") is not None
    disabled_at = datetime.now(timezone.utc)
    repository.upsert_user(user.model_copy(update={"disabled_at": disabled_at}))
    assert repository.upsert_user(user).disabled_at is not None
    assert repository.get_user("user-1").disabled_at is not None
    assert repository.list_projects() == []
    assert repository.list_projects("user-1")[0].project_id == project.project_id
    assert repository.list_projects("user-2") == []

    repository.record_usage("analysis", user_id="user-1")
    assert repository.count_usage_since("analysis", project.created_at, user_id="user-1") == 1
    assert repository.count_usage_since("analysis", project.created_at, user_id="user-2") == 0
    usage_date = datetime.now(timezone.utc).date()
    assert repository.reserve_usage("project", "user-1", usage_date, 2) is True
    assert repository.reserve_usage("project", "user-1", usage_date, 2) is True
    assert repository.reserve_usage("project", "user-1", usage_date, 2) is False

    jurisdiction = JurisdictionRecord(
        jurisdiction_id="richmond-va",
        name="Richmond, VA",
        state="VA",
        jurisdiction_type="independent_city",
        coverage_status="source_discovery",
        official_source_urls=["https://www.rva.gov/planning-development-review"],
    )
    assert repository.upsert_jurisdiction(jurisdiction).supported is False
    assert repository.get_jurisdiction("richmond-va").coverage_status == "source_discovery"
    assert repository.list_jurisdictions()[0].jurisdiction_id == "richmond-va"
    request = JurisdictionRequestCreate(
        normalized_address="1 Main St, Richmond, VA",
        jurisdiction_id="richmond-va",
        jurisdiction_name="Richmond, VA",
        state="VA",
        requested_use_type="food-service",
    )
    first_request = repository.save_jurisdiction_request(request, user_id="user-1")
    second_request = repository.save_jurisdiction_request(request, user_id="user-1")
    assert first_request.status == "created"
    assert second_request.status == "existing"
    assert repository.list_jurisdiction_request_summaries()[0].request_count == 1

    repository.audit(
        "pipeline.intake.completed",
        str(project.project_id),
        {"inferred_use": "home-based-food-business"},
        user_id="user-1",
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

    assert repository.delete_project(project.project_id) is True
    assert repository.get_project(project.project_id) is None
    assert repository.get_analysis(project.project_id) is None
    assert repository.get_audit_events(project.project_id) == []
    assert repository.delete_project(project.project_id) is False

    second_project = ProjectRecord(
        session_id=uuid4(),
        user_id="user-1",
        project_description="Convert garage to bakery with two employees and set operating hours.",
        input_address="300 Turner St NW",
        normalized_address="300 Turner St NW, Blacksburg, VA 24060, USA",
        district="mixed-use-core",
    )
    repository.create_project(second_project)
    deleted_count = repository.delete_user_data("user-1")
    assert deleted_count == 1
    assert repository.get_project(second_project.project_id) is None
    assert repository.list_projects("user-1") == []
    assert repository.get_user("user-1").disabled_at is not None
