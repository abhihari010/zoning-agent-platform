from __future__ import annotations

from app.tools.parcel_tool import ParcelTool


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
