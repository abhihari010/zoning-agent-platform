from __future__ import annotations

import pytest

from app.tools.parcel_tool import ParcelTool, _load_fixtures


def test_lookup_fixture_address() -> None:
    result = ParcelTool().lookup(
        "250 S Main St, Blacksburg, VA 24060",
        37.2296,
        -80.4140,
        "blacksburg-va",
    )

    assert result.parcel_id == "PARCEL-001"
    assert result.zoning_district == "mixed-use-core"
    assert result.method == "fixture"
    assert result.confidence >= 0.9


def test_lookup_unknown_address_returns_keyword_fallback() -> None:
    result = ParcelTool().lookup(
        "10 Downtown Market Street, Blacksburg, VA",
        None,
        None,
        "blacksburg-va",
    )

    assert result.zoning_district == "mixed-use-core"
    assert result.method == "keyword_fallback"
    assert result.confidence == 0.3
    assert result.warnings


def test_lookup_no_district_returns_unknown() -> None:
    result = ParcelTool().lookup(
        "10 Unmapped Ridge Lane",
        None,
        None,
        "blacksburg-va",
    )

    assert result.zoning_district is None
    assert result.method == "unknown"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Christiansburg-VA GIS-verified fixtures
# All facts verified against two authoritative sources:
#   (1) Montgomery County VA Parcel DB: maps.montva.com/server/rest/services/Land/Parcels_Public/MapServer/1
#   (2) Town of Christiansburg GeoWeb Zoning Polygon Layer (spatial intersect):
#       services.arcgis.com/hK4vGUcrLZsYhZjD/.../Town_of_Christiansburg_GeoWeb_WFL1/FeatureServer/46
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("address,parcel_id,expected_district", [
    (
        "1865 Akers St SW, Christiansburg, VA 24073",
        "034029",
        "agricultural",
    ),
    (
        "510 Canterbury St SW, Christiansburg, VA 24073",
        "070371",
        "residential-low-density",
    ),
    (
        "70 Nursery Ln NE, Christiansburg, VA 24073",
        "031600",
        "mixed-use-core",
    ),
    (
        "1380 Mud Pike Rd NW, Christiansburg, VA 24073",
        "030729",
        "commercial-employment",
    ),
    (
        "135 Technology Dr SE, Christiansburg, VA 24073",
        "100516",
        "industrial-zone",
    ),
])
def test_christiansburg_gis_verified_fixtures(
    address: str, parcel_id: str, expected_district: str
) -> None:
    """Each fixture must return the GIS-verified district at confidence 0.9."""
    # Clear LRU cache so the updated fixture file is picked up in this test session
    _load_fixtures.cache_clear()

    result = ParcelTool().lookup(address, None, None, "christiansburg-va")

    assert result.zoning_district == expected_district, (
        f"Expected {expected_district!r} for {address!r}, got {result.zoning_district!r}"
    )
    assert result.parcel_id == parcel_id, (
        f"Expected parcel_id {parcel_id!r} for {address!r}, got {result.parcel_id!r}"
    )
    assert result.confidence == 0.9
    assert result.method == "gis_verified"
    assert result.warnings == []


def test_christiansburg_wrong_jurisdiction_no_match() -> None:
    """Christiansburg fixture must NOT match when queried under a different jurisdiction."""
    _load_fixtures.cache_clear()

    result = ParcelTool().lookup(
        "1865 Akers St SW, Christiansburg, VA 24073",
        None,
        None,
        "blacksburg-va",  # wrong jurisdiction
    )

    # Should fall through to keyword/unknown — not a fixture hit
    assert result.method in ("keyword_fallback", "unknown")
    assert result.confidence < 0.9
