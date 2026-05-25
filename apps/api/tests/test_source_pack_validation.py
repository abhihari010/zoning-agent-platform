from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_source_packs.py"

spec = importlib.util.spec_from_file_location("validate_source_packs", VALIDATOR_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def test_valid_manifest_passes_with_unknown_district_warning(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        "va/sample-va/manifest.json",
        _valid_manifest(
            sources=[
                _valid_source(
                    source_id="sample-va-zoning",
                    jurisdiction_id="sample-va",
                    districts=["unknown"],
                ),
                _valid_source(
                    source_id="sample-va-state-building-code",
                    jurisdiction_id="*",
                    source_type="building_code",
                    districts=["general"],
                    metadata={"applies_to_states": ["VA"], "verification_status": "verified"},
                ),
            ]
        ),
    )

    result = validator.validate_source_packs(tmp_path)

    assert result.ok
    assert len(result.warnings) == 1
    assert "districts contains only 'unknown'" in result.warnings[0].message
    assert result.summaries[0].jurisdiction_id == "sample-va"
    assert result.summaries[0].source_count == 2


def test_invalid_manifest_reports_required_fields_placeholder_urls_and_scope(tmp_path: Path) -> None:
    manifest = _valid_manifest(
        sources=[
            _valid_source(source_id="duplicate-id", jurisdiction_id="sample-va"),
            {
                **_valid_source(source_id="duplicate-id", jurisdiction_id="other-va"),
                "title": "",
                "url": "https://example.gov/zoning",
                "effective_date": "",
            },
        ]
    )
    del manifest["jurisdiction"]["official_source_urls"]

    _write_manifest(tmp_path, "va/sample-va/manifest.json", manifest)

    result = validator.validate_source_packs(tmp_path)
    messages = "\n".join(error.message for error in result.errors)

    assert not result.ok
    assert "jurisdiction.official_source_urls is required" in messages
    assert "title must be non-empty" in messages
    assert "effective_date must be non-empty" in messages
    assert "placeholder URL host is not allowed: example.gov" in messages
    assert "duplicates source" in messages
    assert "jurisdiction_id must match the pack" in messages


def test_curated_local_fallback_allows_local_url_when_explicit(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        "va/sample-va/manifest.json",
        _valid_manifest(
            sources=[
                _valid_source(
                    source_id="sample-va-local-zoning",
                    jurisdiction_id="sample-va",
                    url="local://sample-va/extracted/zoning.txt",
                    metadata={
                        "curated_local_fallback": True,
                        "fallback_reason": "Official PDF has no stable deep link.",
                        "verification_status": "verified",
                    },
                )
            ]
        ),
    )

    result = validator.validate_source_packs(tmp_path)

    assert result.ok
    assert not result.errors


def test_non_http_url_fails_without_curated_fallback(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        "va/sample-va/manifest.json",
        _valid_manifest(
            sources=[
                _valid_source(
                    source_id="sample-va-local-zoning",
                    jurisdiction_id="sample-va",
                    url="local://sample-va/extracted/zoning.txt",
                )
            ]
        ),
    )

    result = validator.validate_source_packs(tmp_path)

    assert not result.ok
    assert any("url must be an http or https URL" in error.message for error in result.errors)


def _write_manifest(root: Path, relative_path: str, payload: dict) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_manifest(*, sources: list[dict]) -> dict:
    return {
        "schema_version": "source-pack/v1",
        "jurisdiction": {
            "jurisdiction_id": "sample-va",
            "name": "Sample, VA",
            "coverage_status": "source_indexed",
            "state": "VA",
            "state_fips": "51",
            "county_fips": "001",
            "place_fips": "12345",
            "jurisdiction_type": "municipality",
            "parent_jurisdiction_id": "sample-county-va",
            "official_source_urls": ["https://sampleva.gov/planning"],
            "zoning_map_url": "https://sampleva.gov/gis/zoning",
            "planning_contact": {
                "url": "https://sampleva.gov/planning/contact",
                "email": "planning@sampleva.gov",
            },
        },
        "verification_notes": "Official planning, code, and zoning map URLs reviewed.",
        "sources": sources,
    }


def _valid_source(
    *,
    source_id: str,
    jurisdiction_id: str,
    url: str = "https://sampleva.gov/code/zoning",
    source_type: str = "zoning_ordinance",
    districts: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "source_id": source_id,
        "title": "Sample Zoning Ordinance",
        "excerpt": "The zoning ordinance establishes zoning districts and use standards for local review.",
        "section_ref": "Chapter 18",
        "jurisdiction_id": jurisdiction_id,
        "url": url,
        "effective_date": "2026-05-01",
        "source_type": source_type,
        "districts": districts or ["mixed-use-core"],
        "uses": ["general"],
        "metadata": metadata or {"verification_status": "verified"},
    }
