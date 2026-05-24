from __future__ import annotations

from app.tools.address_tool import AddressTool


def test_normalize_known_address() -> None:
    result = AddressTool().normalize("250 S Main St, Blacksburg, VA")

    assert result.normalized_address == "250 S Main St, Blacksburg, VA 24060, USA"
    assert result.lat is not None
    assert result.lng is not None
    assert result.confidence >= 0.9
    assert result.warnings == []


def test_normalize_unknown_address_returns_warnings(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    result = AddressTool().normalize("999 Mystery Road")

    assert result.normalized_address == "999 Mystery Road"
    assert result.confidence == 0.3
    assert result.warnings
