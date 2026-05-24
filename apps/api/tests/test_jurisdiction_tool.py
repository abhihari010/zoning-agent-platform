from __future__ import annotations

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
