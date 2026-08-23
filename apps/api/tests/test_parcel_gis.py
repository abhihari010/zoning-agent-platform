from __future__ import annotations

import json

import httpx
import pytest

from app.models import ParcelResult
from app.tools import parcel_gis
from app.tools.parcel_tool import ParcelTool


BLACKSBURG_LAT = 37.200801
BLACKSBURG_LNG = -80.395809


def _arcgis_payload(**attributes: object) -> dict[str, object]:
    return {"features": [{"attributes": attributes}]}


@pytest.fixture(autouse=True)
def _enable_gis_with_a_clean_cache(monkeypatch):
    # conftest turns the lookup off for the suite at large; these tests are the ones
    # that exercise it, always against a stubbed transport.
    monkeypatch.setenv("PARCEL_GIS_ENABLED", "true")
    parcel_gis.clear_cache()
    yield
    parcel_gis.clear_cache()


def _stub_get(monkeypatch, payload, *, capture: dict | None = None):
    def fake_get(url, params=None, timeout=None):
        if capture is not None:
            capture["url"] = url
            capture["params"] = params
            capture["timeout"] = timeout
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(parcel_gis.httpx, "get", fake_get)


def test_lookup_maps_zoning_code_to_district(monkeypatch):
    captured: dict = {}
    _stub_get(
        monkeypatch,
        _arcgis_payload(ZONING="R-4", PARCEL_ID="090112", JURISDICTI="BLACKSBURG"),
        capture=captured,
    )

    result = parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG)

    assert result is not None
    assert result.zoning_code == "R-4"
    assert result.district == "residential-low-density"
    assert result.parcel_id == "090112"

    geometry = json.loads(captured["params"]["geometry"])
    assert geometry == {
        "x": BLACKSBURG_LNG,
        "y": BLACKSBURG_LAT,
        "spatialReference": {"wkid": 4326},
    }
    assert captured["params"]["spatialRel"] == "esriSpatialRelIntersects"


def test_lookup_folds_separator_differences_between_layer_and_ordinance(monkeypatch):
    # The layer records "R1"; christiansburg's ordinance article reads "R-1".
    _stub_get(monkeypatch, _arcgis_payload(ZONING="R1", PARCEL_ID="1", JURISDICTI="CHRISTIANSBURG"))

    result = parcel_gis.lookup("christiansburg-va", 37.13, -80.41)

    assert result is not None
    assert result.district == "residential-low-density"


def test_lookup_rejects_a_parcel_in_a_different_jurisdiction(monkeypatch):
    # Shared county layer: a geocode just outside the town limits must not be answered
    # with the county's zoning under the town's name.
    _stub_get(monkeypatch, _arcgis_payload(ZONING="R2", PARCEL_ID="015255", JURISDICTI="MONTGOMERY"))

    assert parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG) is None


def test_lookup_reports_an_unmapped_code_without_guessing(monkeypatch):
    _stub_get(monkeypatch, _arcgis_payload(ZONING="UNIV", PARCEL_ID="42", JURISDICTI="BLACKSBURG"))

    result = parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG)

    assert result is not None
    assert result.zoning_code == "UNIV"
    assert result.district is None


def test_lookup_returns_none_when_upstream_fails(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise httpx.ConnectTimeout("upstream down")

    monkeypatch.setattr(parcel_gis.httpx, "get", boom)

    assert parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG) is None


def test_lookup_returns_none_on_an_arcgis_error_payload(monkeypatch):
    _stub_get(monkeypatch, {"error": {"code": 400, "message": "Invalid geometry"}})

    assert parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG) is None


def test_lookup_skips_unconfigured_jurisdictions_and_missing_coordinates(monkeypatch):
    def unexpected(url, params=None, timeout=None):  # pragma: no cover - must not run
        raise AssertionError("no network call expected")

    monkeypatch.setattr(parcel_gis.httpx, "get", unexpected)

    assert parcel_gis.lookup("richmond-va", BLACKSBURG_LAT, BLACKSBURG_LNG) is None
    assert parcel_gis.lookup("blacksburg-va", None, None) is None


def test_lookup_is_disabled_by_settings(monkeypatch):
    def unexpected(url, params=None, timeout=None):  # pragma: no cover - must not run
        raise AssertionError("no network call expected")

    monkeypatch.setattr(parcel_gis.httpx, "get", unexpected)
    monkeypatch.setenv("PARCEL_GIS_ENABLED", "false")

    assert parcel_gis.lookup("blacksburg-va", BLACKSBURG_LAT, BLACKSBURG_LNG) is None


def test_lookup_caches_repeat_requests(monkeypatch):
    calls = {"n": 0}

    def counting_get(url, params=None, timeout=None):
        calls["n"] += 1
        return httpx.Response(
            200,
            json=_arcgis_payload(ZONING="DC", PARCEL_ID="150029", JURISDICTI="BLACKSBURG"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(parcel_gis.httpx, "get", counting_get)

    for _ in range(3):
        assert parcel_gis.lookup("blacksburg-va", 37.228082, -80.412765) is not None

    assert calls["n"] == 1


def test_parcel_tool_uses_gis_when_no_fixture_matches(monkeypatch):
    _stub_get(monkeypatch, _arcgis_payload(ZONING="GC", PARCEL_ID="029406", JURISDICTI="BLACKSBURG"))

    result = ParcelTool().lookup(
        "9999 Unlisted Ave, Blacksburg, VA",
        37.184805,
        -80.408010,
        "blacksburg-va",
    )

    assert result.zoning_district == "commercial-employment"
    assert result.zoning_code == "GC"
    assert result.parcel_id == "029406"
    assert result.method == "gis_lookup"
    # Must clear the orchestrator's 0.7 district-confidence gate to reach retrieval.
    assert result.confidence >= 0.7


def test_parcel_tool_prefers_a_fixture_over_the_network(monkeypatch):
    def unexpected(url, params=None, timeout=None):  # pragma: no cover - must not run
        raise AssertionError("no network call expected")

    monkeypatch.setattr(parcel_gis.httpx, "get", unexpected)

    result = ParcelTool().lookup(
        "810 Ellett Rd, Blacksburg, VA",
        37.200801,
        -80.395809,
        "blacksburg-va",
    )

    assert result.method == "gis_verified"
    assert result.zoning_district == "residential-low-density"


def test_parcel_tool_falls_back_to_keywords_when_gis_is_silent(monkeypatch):
    _stub_get(monkeypatch, {"features": []})

    result = ParcelTool().lookup(
        "9999 Industrial Way, Blacksburg, VA",
        37.19,
        -80.39,
        "blacksburg-va",
    )

    assert result.method == "keyword_fallback"
    assert result.confidence == 0.3


def test_parcel_tool_does_not_guess_a_district_for_an_unmapped_code(monkeypatch):
    _stub_get(monkeypatch, _arcgis_payload(ZONING="UNIV", PARCEL_ID="42", JURISDICTI="BLACKSBURG"))

    result = ParcelTool().lookup(
        "9999 Unlisted Ave, Blacksburg, VA",
        BLACKSBURG_LAT,
        BLACKSBURG_LNG,
        "blacksburg-va",
    )

    assert result.zoning_district is None
    assert result.zoning_code == "UNIV"
    assert result.confidence < 0.7
    assert result.warnings and "UNIV" in result.warnings[0]


def test_configured_layers_have_the_fields_the_query_needs():
    for jurisdiction_id, config in parcel_gis.load_gis_sources().items():
        provider = config.get("provider", "arcgis")
        assert provider in ("arcgis", "arcgis_layer_per_district"), jurisdiction_id
        assert config.get("url", "").startswith("https://"), jurisdiction_id
        assert config.get("zoning_field"), jurisdiction_id
        if provider == "arcgis_layer_per_district":
            # Without the id -> name map there is nothing to read the code from.
            assert config.get("layers"), jurisdiction_id
        # The guard only runs when both halves are present, so a lone one is a silent
        # hole: a shared county layer would answer with a neighbouring town's zoning.
        assert bool(config.get("jurisdiction_field")) == bool(config.get("jurisdiction_value")), jurisdiction_id


def test_every_derived_district_category_records_its_evidence():
    # "Derived from the city's own ordinance, never guessed" is only checkable if the
    # sentence behind each mapping is committed alongside it.
    evidence_path = parcel_gis.GIS_SOURCES_PATH.with_name("parcel_gis_district_evidence.json")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    for jurisdiction_id, config in parcel_gis.load_gis_sources().items():
        if config.get("curated"):
            continue
        recorded = evidence.get(jurisdiction_id, {})
        missing = sorted(set(config["district_categories"]) - set(recorded))
        assert not missing, f"{jurisdiction_id}: {missing}"


def test_configured_district_categories_use_the_known_vocabulary():
    known = {
        "residential-low-density",
        "commercial-employment",
        "industrial-zone",
        "mixed-use-core",
        "agricultural",
    }
    sources = parcel_gis.load_gis_sources()

    assert sources, "expected at least one configured jurisdiction"
    for jurisdiction_id, config in sources.items():
        categories = config["district_categories"]
        assert categories, f"{jurisdiction_id} has no district categories"
        for code, district in categories.items():
            assert district in known, f"{jurisdiction_id}:{code} -> {district}"


def test_intake_carries_the_jurisdictions_own_zoning_code_into_the_report(monkeypatch):
    # The point of the lookup is that a report can say "your parcel is zoned R-4" rather
    # than only the coarse bucket, so the code has to survive intake and reach the
    # trust indicators the frontend renders.
    _stub_get(monkeypatch, _arcgis_payload(ZONING="DC", PARCEL_ID="150029", JURISDICTI="BLACKSBURG"))

    from app.orchestrator.pipeline_context import PipelineContext
    from app.tools.intake_tool import IntakeTool

    context = PipelineContext(
        project_description="Open a small bakery in an existing storefront.",
        combined_description="Open a small bakery in an existing storefront.",
        raw_address="250 S Main St, Blacksburg, VA",
        district="unknown",
        jurisdiction_id="blacksburg-va",
    )
    resolved = ParcelResult(
        parcel_id="150029",
        zoning_district="mixed-use-core",
        zoning_code="DC",
        confidence=0.9,
        method="gis_lookup",
    )
    monkeypatch.setattr(ParcelTool, "lookup", lambda *args, **kwargs: resolved)

    IntakeTool().extract(context)

    assert context.zoning_code == "DC"
    assert context.district == "mixed-use-core"


def test_layer_per_district_service_reads_the_district_from_the_layer_name(monkeypatch):
    # Springfield, TN draws each district as its own layer instead of storing a code
    # column, so the answer is whichever layer contains the point.
    captured: dict = {}
    _stub_get(
        monkeypatch,
        {"layers": [{"id": 12, "features": [{"attributes": {"OBJECTID": 1}}]},
                    {"id": 21, "features": []}]},
        capture=captured,
    )

    result = parcel_gis.lookup("springfield-tn", 36.509, -86.885)

    assert result is not None
    assert result.zoning_code == "R10"
    assert result.district == "residential-low-density"
    # One request for the whole service, not one per district.
    assert "layerDefs" in captured["params"]


def test_layer_per_district_declines_when_two_layers_claim_the_point(monkeypatch):
    _stub_get(
        monkeypatch,
        {"layers": [{"id": 12, "features": [{"attributes": {"OBJECTID": 1}}]},
                    {"id": 11, "features": [{"attributes": {"OBJECTID": 2}}]}]},
    )

    assert parcel_gis.lookup("springfield-tn", 36.509, -86.885) is None
