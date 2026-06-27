from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app import services
from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider
from app.ingestion import import_source_documents, import_source_packs, list_source_packs, parse_source_file
from app.models import SourceRegistryEntry
from app.storage import SQLiteStore, store
from app.tools import CitationTool, IntakeTool
from app.orchestrator.pipeline_context import PipelineContext


def _clear_external_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "AI_PROVIDER",
        "RAG_PROVIDER",
        "LOCAL_MODEL_BASE_URL",
        "LOCAL_MODEL_NAME",
        "LOCAL_MODEL_TIMEOUT_SECONDS",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_normalize_address_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")

    place_payload = {
        "status": "OK",
        "candidates": [
            {
                "formatted_address": "300 Turner St NW, Blacksburg, VA 24060, USA",
                "place_id": "place-123",
                "address_components": [
                    {"long_name": "Downtown", "types": ["sublocality_level_1"]},
                    {"long_name": "Blacksburg", "types": ["locality"]},
                ],
                "geometry": {"location": {"lat": 40.1, "lng": -74.5}},
            }
        ],
    }

    geocode_payload = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "300 Turner St NW, Blacksburg, VA 24060, USA",
                "place_id": "place-123",
                "address_components": [
                    {"long_name": "Downtown", "types": ["sublocality_level_1"]},
                    {"long_name": "Blacksburg", "types": ["locality"]},
                ],
                "geometry": {"location": {"lat": 40.1, "lng": -74.5}},
            }
        ],
    }

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, params: dict, timeout: float):
        if "findplacefromtext" in url:
            return FakeResponse(place_payload)
        return FakeResponse(geocode_payload)

    monkeypatch.setattr(services.httpx, "get", fake_get)

    result = services.normalize_address("300 Turner St NW Blacksburg")

    assert result.is_valid is True
    assert result.normalized_address == "300 Turner St NW, Blacksburg, VA 24060, USA"
    assert result.place_id == "place-123"
    assert result.latitude == 40.1
    assert result.longitude == -74.5
    assert result.district == "mixed-use-core"
    assert result.district_confidence == 0.3
    assert result.district_method == "component_rule"
    assert result.support_status == "supported"
    assert result.jurisdiction_id == "blacksburg-va"
    assert result.jurisdiction_name == "Blacksburg, VA"


def test_normalize_address_does_not_default_blacksburg_to_mixed_use_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")
    _mock_google_address(
        monkeypatch,
        {
            "formatted_address": "400 Clay St SW, Blacksburg, VA 24060, USA",
            "place_id": "place-clay",
            "address_components": [
                {"long_name": "Blacksburg", "types": ["locality"]},
                {"long_name": "Montgomery County", "types": ["administrative_area_level_2"]},
                {"long_name": "Virginia", "types": ["administrative_area_level_1"]},
            ],
            "geometry": {"location": {"lat": 37.2, "lng": -80.4}},
        },
    )

    result = services.normalize_address("400 Clay St SW Blacksburg VA")

    assert result.is_valid is True
    assert result.district == "unknown"
    assert result.district_confidence == 0.0
    assert result.district_method == "unknown"


def test_normalize_address_zero_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, params: dict, timeout: float):
        if "findplacefromtext" in url:
            return FakeResponse({"status": "ZERO_RESULTS", "candidates": []})
        return FakeResponse({"status": "ZERO_RESULTS", "results": []})

    monkeypatch.setattr(services.httpx, "get", fake_get)

    result = services.normalize_address("Unknown Place")

    assert result.is_valid is False
    assert result.district == "unknown"
    assert result.support_status == "invalid"
    assert "could not be validated" in result.warnings[0].lower()


def _mock_google_address(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    class FakeResponse:
        def __init__(self, response_payload: dict) -> None:
            self._payload = response_payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, params: dict, timeout: float):
        if "findplacefromtext" in url:
            return FakeResponse({"status": "OK", "candidates": [payload]})
        return FakeResponse({"status": "OK", "results": [payload]})

    monkeypatch.setattr(services.httpx, "get", fake_get)


@pytest.mark.parametrize(
    ("formatted_address", "components", "expected_id", "expected_name"),
    [
        (
            "215 Church Ave SW, Roanoke, VA 24011, USA",
            [
                {"long_name": "Roanoke", "types": ["locality"]},
                {"long_name": "Roanoke City", "types": ["administrative_area_level_2"]},
                {"long_name": "VA", "types": ["administrative_area_level_1"]},
            ],
            "roanoke-va",
            "Roanoke, VA",
        ),
        (
            "5204 Bernard Dr, Roanoke, VA 24018, USA",
            [
                {"long_name": "Cave Spring", "types": ["locality"]},
                {"long_name": "Roanoke County", "types": ["administrative_area_level_2"]},
                {"long_name": "VA", "types": ["administrative_area_level_1"]},
            ],
            "roanoke-county-va",
            "Roanoke County, VA",
        ),
    ],
)
def test_normalize_address_source_indexed_jurisdictions_served_with_caveat(
    monkeypatch: pytest.MonkeyPatch,
    formatted_address: str,
    components: list[dict],
    expected_id: str,
    expected_name: str,
) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")
    _mock_google_address(
        monkeypatch,
        {
            "formatted_address": formatted_address,
            "place_id": "place-source-indexed",
            "address_components": components,
            "geometry": {"location": {"lat": 37.1, "lng": -80.4}},
        },
    )

    result = services.normalize_address(formatted_address)

    # source_indexed cities are servable: valid + supported, but carry a coverage caveat.
    assert result.is_valid is True
    assert result.support_status == "supported"
    assert result.coverage_status == "source_indexed"
    assert result.jurisdiction_id == expected_id
    assert result.jurisdiction_name == expected_name
    assert any("Preliminary coverage" in w for w in result.warnings)


def test_normalize_address_supported_montgomery_county_jurisdiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")
    _mock_google_address(
        monkeypatch,
        {
            "formatted_address": "755 Roanoke St, Christiansburg, VA 24073, USA",
            "place_id": "place-montgomery",
            "address_components": [
                {"long_name": "Merrimac", "types": ["locality"]},
                {"long_name": "Montgomery County", "types": ["administrative_area_level_2"]},
                {"long_name": "Virginia", "types": ["administrative_area_level_1"]},
            ],
            "geometry": {"location": {"lat": 37.1, "lng": -80.4}},
        },
    )

    result = services.normalize_address("755 Roanoke St Christiansburg VA")

    assert result.is_valid is True
    assert result.support_status == "supported"
    assert result.jurisdiction_id == "montgomery-county-va"
    assert result.jurisdiction_name == "Montgomery County, VA"
    assert result.place_id == "place-montgomery"


def test_normalize_address_valid_unrecognized_jurisdiction_is_not_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")
    _mock_google_address(
        monkeypatch,
        {
            "formatted_address": "1 Main St, Richmond, VA 23219, USA",
            "place_id": "place-unrecognized",
            "address_components": [
                {"long_name": "Richmond", "types": ["locality"]},
                {"long_name": "Richmond City", "types": ["administrative_area_level_2"]},
                {"long_name": "VA", "types": ["administrative_area_level_1"]},
            ],
            "geometry": {"location": {"lat": 37.5, "lng": -77.4}},
        },
    )

    result = services.normalize_address("1 Main St Richmond VA")

    assert result.is_valid is False
    assert result.support_status == "unsupported"
    assert result.jurisdiction_id == "us-va-richmond-city-richmond"
    assert result.jurisdiction_name == "Richmond, VA"
    assert result.coverage_status == "unsupported"
    assert "Richmond, VA" in result.warnings[0]


def test_keyword_district_rules_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_DISTRICT_KEYWORD_MAP", json.dumps({"warehouse": "industrial-zone"}))

    rules = services._load_keyword_district_rules()

    assert rules["warehouse"] == "industrial-zone"


def test_intake_tool_returns_structured_deterministic_result() -> None:
    context = PipelineContext(
        project_description="I want to convert my garage into a small coffee shop.",
        combined_description="I want to convert my garage into a small coffee shop.",
        district="mixed-use-core",
    )

    result = IntakeTool().extract(context)

    assert result.use_type == "food_service"
    assert result.project_scope == "change_of_use"
    assert result.business_activity == "coffee_shop"
    assert result.clarification_required is True
    assert "change_of_use" in result.possible_triggers
    assert "parking" in result.possible_triggers
    assert result.clarification_questions


def test_citation_tool_rejects_wrong_jurisdiction() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_citation_validation"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="wrong-city-rule",
                title="Wrong City Rule",
                excerpt="This source belongs to another jurisdiction.",
                section_ref="Sec 1",
                jurisdiction_id="christiansburg-va",
                districts=["mixed-use-core"],
                uses=["general"],
            )
        )

        validation = CitationTool(source_store).validate(
            citations=[
                services.SourceCitation(
                    source_id="wrong-city-rule",
                    title="Wrong City Rule",
                    excerpt="This source belongs to another jurisdiction.",
                    section_ref="Sec 1",
                    jurisdiction_id="christiansburg-va",
                )
            ],
            jurisdiction_id="blacksburg-va",
        )

        assert validation.valid is False
        assert validation.confidence_adjustment == "downgrade_low_confidence"
        assert "wrong-city-rule" in validation.invalid_citation_ids
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_analyze_project_runs_with_offline_default_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_external_provider_env(monkeypatch)
    store.reset()

    result = services.analyze_project(
        project_description="Convert garage to bakery with employees, hours, and renovation plans.",
        district="mixed-use-core",
    )

    assert result.feasibility.decision == "conditional"
    assert result.pipeline is not None
    assert result.pipeline.version == "single_orchestrator_v1"
    assert result.pipeline_stages
    assert result.pipeline_stages == result.agents
    assert [stage.label for stage in result.agents] == [
        "Understand Project",
        "Resolve Property",
        "Retrieve Sources",
        "Analyze Compliance",
        "Generate Checklist",
    ]
    assert result.citations
    placeholder_host = "example" + ".gov"
    assert all(placeholder_host not in (citation.url or "") for citation in result.citations)


def test_analyze_project_without_matching_citations_is_unknown_low_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_no_matching_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="industrial-only",
                title="Industrial Only Rule",
                excerpt="Industrial operations are reviewed in industrial districts.",
                section_ref="Sec 4.1",
                districts=["industrial-zone"],
                uses=["industrial-use"],
            )
        )
        retriever = SourceRegistryRetrievalProvider(source_store)

        monkeypatch.setattr(services, "get_analysis_provider", lambda: DeterministicAnalysisProvider())
        monkeypatch.setattr(services, "get_retrieval_provider", lambda: retriever)
        result = services.analyze_project(
            project_description="Open a drone repair studio with employees, hours, and renovation plans.",
            district="mixed-use-core",
        )

        assert result.feasibility.decision == "unknown"
        assert result.status == "low_confidence"
        assert result.citations == []
        assert result.citation_validation is not None
        assert result.citation_validation.valid is False
        assert result.feasibility.confidence < 0.6
        assert any("No relevant ordinances" in warning for warning in result.warnings)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_analyze_project_uses_unknown_effective_district_when_confidence_is_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CapturingRetriever:
        name = "capturing"

        def __init__(self) -> None:
            self.district = None

        def retrieve(self, request):
            from app.ai.interfaces import RetrievalProviderResult

            self.district = request.district
            return RetrievalProviderResult(citations=[], chunks=[])

    retriever = CapturingRetriever()
    monkeypatch.setattr(services, "get_analysis_provider", lambda: DeterministicAnalysisProvider())
    monkeypatch.setattr(services, "get_retrieval_provider", lambda: retriever)

    services.analyze_project(
        project_description="Open a small coffee shop with employees, hours, and renovation plans.",
        district="mixed-use-core",
        district_confidence=0.3,
        district_method="keyword_fallback",
        jurisdiction_id="blacksburg-va",
        normalized_address="400 Clay St SW, Blacksburg, VA 24060",
    )

    assert retriever.district == "unknown"


def test_dedupe_follow_up_questions_prefers_specific_prompt() -> None:
    deduped = services._dedupe_follow_up_questions(
        [
            "What are the proposed operating hours of the office?",
            "Please provide operating hours.",
            "What is the scope of any construction or renovations planned for the property?",
            "Please provide construction scope.",
            "Please provide number of employees.",
        ]
    )

    assert "What are the proposed operating hours of the office?" in deduped
    assert "What is the scope of any construction or renovations planned for the property?" in deduped
    assert "Please provide operating hours." not in deduped
    assert "Please provide construction scope." not in deduped
    assert "Please provide number of employees." in deduped


def test_parse_source_file_from_markdown() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_parse_source"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    path = temp_dir / "ordinance.md"
    try:
        path.write_text(
            "\n".join(
                [
                    "title: Mixed Use Ordinance",
                    "section_ref: Sec 10.3",
                    "districts: mixed-use-core, commercial-employment",
                    "uses: general",
                    "",
                    "Mixed-use districts may allow neighborhood commercial activity with review.",
                ]
            ),
            encoding="utf-8",
        )

        entries = parse_source_file(path)

        assert len(entries) == 1
        assert entries[0].title == "Mixed Use Ordinance"
        assert entries[0].districts == ["mixed-use-core", "commercial-employment"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_import_source_documents_reads_multiple_formats() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_import_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        markdown_path = temp_dir / "guidance.md"
        markdown_path.write_text(
            "\n".join(
                [
                    "title: Home Occupation Rules",
                    "section_ref: Sec 1.1",
                    "districts: residential-low-density",
                    "uses: home-based-food-business",
                    "",
                    "Home occupations may be conditionally permitted when traffic remains limited.",
                ]
            ),
            encoding="utf-8",
        )

        json_path = temp_dir / "parking.json"
        json_path.write_text(
            json.dumps(
                {
                    "source_id": "parking-rule",
                    "title": "Parking Rule",
                    "excerpt": "Two spaces required.",
                    "section_ref": "Sec 2.1",
                    "districts": ["mixed-use-core"],
                    "uses": ["general"],
                }
            ),
            encoding="utf-8",
        )

        entries = import_source_documents(temp_dir)

        assert len(entries) == 2
        assert {entry.source_id for entry in entries} == {"guidance", "parking-rule"}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_source_pack_manifests_validate_and_import() -> None:
    packs = list_source_packs()

    assert {pack.jurisdiction_id for pack in packs} >= {
        "blacksburg-va",
        "montgomery-county-va",
        "christiansburg-va",
        "roanoke-va",
        "roanoke-county-va",
    }

    entries = import_source_packs()

    assert any(entry.jurisdiction_id == "christiansburg-va" for entry in entries)
    assert all(entry.url for entry in entries)
    assert all(entry.effective_date for entry in entries)
