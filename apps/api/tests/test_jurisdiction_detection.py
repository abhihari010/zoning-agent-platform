"""Regression tests for address -> jurisdiction detection.

Independent cities (VA) are their own county-equivalent, so geocoders return no
administrative_area_level_2 for them. Detection must still resolve them from
locality + state alone; requiring a county component rejected every real address
(the whole VA independent-city set resolved to us-va-unknown-county-* / unsupported).
"""
from __future__ import annotations

from app.jurisdictions import detect_jurisdiction


def _components(locality=None, county=None, state="Virginia"):
    out = []
    if locality:
        out.append({"long_name": locality, "types": ["locality"]})
    if county:
        out.append({"long_name": county, "types": ["administrative_area_level_2"]})
    out.append({"long_name": state, "short_name": "VA", "types": ["administrative_area_level_1"]})
    out.append({"long_name": "United States", "short_name": "US", "types": ["country"]})
    return out


def test_independent_city_resolves_without_county_component():
    # Geocoders omit the county for VA independent cities.
    match = detect_jurisdiction("921 Quail St, Norfolk, VA 23513", _components(locality="Norfolk"))
    assert match.recognized
    assert match.jurisdiction_id == "norfolk-va"


def test_county_jurisdiction_still_requires_county():
    match = detect_jurisdiction(
        "1 Harrison St SE, Leesburg, VA 20175",
        _components(locality="Leesburg", county="Loudoun County"),
    )
    assert match.recognized
    assert match.jurisdiction_id == "loudoun-county-va"


def test_locality_town_still_resolves():
    match = detect_jurisdiction(
        "400 Clay St SW, Blacksburg, VA 24060",
        _components(locality="Blacksburg", county="Montgomery County"),
    )
    assert match.recognized
    assert match.jurisdiction_id == "blacksburg-va"


def test_unknown_locality_is_not_recognized():
    match = detect_jurisdiction("123 Nowhere Rd, Faketown, VA", _components(locality="Faketown"))
    # Falls through to the unsupported us-va-* synthetic, never a real supported record.
    assert match.jurisdiction_id in (None,) or match.jurisdiction_id.startswith("us-va-")
    assert not match.supported
