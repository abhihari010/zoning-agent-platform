from __future__ import annotations

import json

from app.ingestion import build_source_chunks
from app.jurisdictions import validate_public_support_candidate
from app.models import JurisdictionRecord, SourceRegistryEntry
from app.repositories import SQLAlchemyStore
from app.tools.jurisdiction_tool import JurisdictionTool


def test_resolve_supported_jurisdiction() -> None:
    result = JurisdictionTool().resolve(
        "250 S Main St, Blacksburg, VA 24060",
        37.2296,
        -80.4140,
        None,
    )

    assert result.jurisdiction_id == "blacksburg-va"
    assert result.jurisdiction_name == "Blacksburg, VA"
    assert result.supported is True
    assert result.coverage_status == "public_supported"
    assert result.confidence >= 0.8


def test_resolve_unsupported_jurisdiction() -> None:
    result = JurisdictionTool().resolve(
        "100 Main St, Christiansburg, VA 24073",
        37.1,
        -80.4,
        None,
    )

    assert result.jurisdiction_id == "christiansburg-va"
    assert result.supported is False
    assert result.coverage_status == "source_indexed"
    assert result.warnings


def test_explicit_jurisdiction_takes_priority() -> None:
    result = JurisdictionTool().resolve(
        "250 S Main St, Blacksburg, VA 24060",
        37.2296,
        -80.4140,
        "montgomery-county-va",
    )

    assert result.jurisdiction_id == "montgomery-county-va"
    assert result.method == "explicit"
    assert result.confidence == 1.0


def test_resolve_unknown_us_jurisdiction_returns_discovery_id() -> None:
    result = JurisdictionTool().resolve(
        "1 Main St, Richmond, VA 23219",
        37.5,
        -77.4,
        None,
        [
            {"long_name": "Richmond", "types": ["locality"]},
            {"long_name": "Richmond City", "types": ["administrative_area_level_2"]},
            {"long_name": "Virginia", "short_name": "VA", "types": ["administrative_area_level_1"]},
            {"long_name": "United States", "short_name": "US", "types": ["country"]},
        ],
    )

    assert result.jurisdiction_id == "us-va-richmond-city-richmond"
    assert result.jurisdiction_name == "Richmond, VA"
    assert result.supported is False
    assert result.coverage_status == "unsupported"
    assert result.method == "geocode"


def test_public_support_candidate_guard_passes_when_gates_exist(tmp_path) -> None:
    repository = SQLAlchemyStore(tmp_path / "promotion.sqlite3")
    jurisdiction = JurisdictionRecord(
        jurisdiction_id="blacksburg-va",
        name="Blacksburg, VA",
        state="VA",
        jurisdiction_type="municipality",
        coverage_status="public_supported",
        official_source_urls=["https://www.blacksburg.gov/departments/departments-l-z/planning-and-building/zoning"],
        planning_contact={"url": "https://www.blacksburg.gov/departments/departments-l-z/planning-and-building"},
    )
    source = SourceRegistryEntry(
        source_id="blacksburg-promotion-rule",
        title="Blacksburg Promotion Rule",
        excerpt="Home occupations require planning review with source-backed zoning guidance.",
        section_ref="Sec 1",
        jurisdiction_id="blacksburg-va",
        url="https://www.blacksburg.gov/departments/departments-l-z/planning-and-building/zoning",
        effective_date="2026-05-25",
        districts=["mixed-use-core"],
        uses=["home-based-food-business"],
    )
    scenarios_path = tmp_path / "scenarios.json"
    scenarios_path.write_text(
        json.dumps(
            [
                {
                    "id": "bburg",
                    "jurisdiction_id": "blacksburg-va",
                    "expect": {"jurisdiction_supported": True, "min_citations": 1},
                }
            ]
        ),
        encoding="utf-8",
    )

    repository.upsert_jurisdiction(jurisdiction)
    repository.upsert_source(source)
    repository.replace_source_chunks(build_source_chunks([source]))

    result = validate_public_support_candidate(
        "blacksburg-va",
        source_store=repository,
        golden_scenarios_path=scenarios_path,
    )

    assert result.eligible is True
    assert result.errors == ()


def test_public_support_candidate_guard_reports_missing_gates(tmp_path) -> None:
    repository = SQLAlchemyStore(tmp_path / "promotion-missing.sqlite3")
    repository.upsert_jurisdiction(
        JurisdictionRecord(
            jurisdiction_id="christiansburg-va",
            name="Christiansburg, VA",
            state="VA",
            jurisdiction_type="municipality",
            coverage_status="source_indexed",
            official_source_urls=[],
            planning_contact={},
        )
    )

    result = validate_public_support_candidate(
        "christiansburg-va",
        source_store=repository,
        golden_scenarios_path=tmp_path / "missing-scenarios.json",
    )

    assert result.eligible is False
    assert "Planning contact" in result.errors[0]
    assert any("official source URL" in error for error in result.errors)
    assert any("local source" in error for error in result.errors)
    assert any("Indexed source chunks" in error for error in result.errors)
    assert any("golden QA scenario" in error for error in result.errors)


def test_public_support_candidate_guard_blocks_source_indexed_jurisdictions(tmp_path) -> None:
    repository = SQLAlchemyStore(tmp_path / "promotion-source-indexed.sqlite3")
    jurisdiction = JurisdictionRecord(
        jurisdiction_id="christiansburg-va",
        name="Christiansburg, VA",
        state="VA",
        jurisdiction_type="municipality",
        coverage_status="source_indexed",
        official_source_urls=["https://www.christiansburg.org/150/Planning"],
        planning_contact={"url": "https://www.christiansburg.org/150/Planning"},
    )
    source = SourceRegistryEntry(
        source_id="christiansburg-rule",
        title="Christiansburg Rule",
        excerpt="Planning review is described for local zoning and permitting sources.",
        section_ref="Planning",
        jurisdiction_id="christiansburg-va",
        url="https://www.christiansburg.org/150/Planning",
        effective_date="2026-05-25",
        districts=["unknown"],
        uses=["general"],
    )
    scenarios_path = tmp_path / "scenarios.json"
    scenarios_path.write_text(
        json.dumps(
            [
                {
                    "id": "christiansburg",
                    "jurisdiction_id": "christiansburg-va",
                    "expect": {"jurisdiction_supported": False, "min_citations": 0},
                }
            ]
        ),
        encoding="utf-8",
    )

    repository.upsert_jurisdiction(jurisdiction)
    repository.upsert_source(source)
    repository.replace_source_chunks(build_source_chunks([source]))

    result = validate_public_support_candidate(
        "christiansburg-va",
        source_store=repository,
        golden_scenarios_path=scenarios_path,
    )

    assert result.eligible is False
    assert any("qa_ready" in error for error in result.errors)
    assert any("source-backed citations" in error for error in result.errors)
