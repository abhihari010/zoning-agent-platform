"""Unit tests for scripts/promote_source_pack_drafts.py.

All tests are fully offline — no network, no database, no app imports.
All file I/O uses tmp_path (pytest fixture) pointing at temp directories.

Covered:
  - Curated pack written with coverage_status=source_indexed
  - coverage_status=public_supported is NEVER written (hard-forced)
  - Sources and district/use tags preserved verbatim from draft
  - schema_version set to "source-pack/v1"
  - Trailing newline on all written files
  - parent_jurisdiction_id present in source pack jurisdiction block
  - jurisdictions.json entry created with correct locality_names / county_names /
    state_names / match_strategy / district_mapping_strategy / supported=False
  - Idempotency: run twice -> files byte-identical, no duplicate jurisdictions.json entry
  - Update path: pre-existing entry replaced in place (one entry, not two)
  - Other existing entries preserved when adding a new one
  - jurisdiction_action "added" vs "updated" reported correctly
  - Missing draft id -> ValueError raised with clear message
  - main() exits non-zero on missing draft
  - County-type draft -> locality_names and county_names derived correctly
  - independent_city -> county_names as ["<X> City", "City of <X>"]
  - --id CLI path: exit code 0 on success
  - --all flag: discovers and promotes multiple drafts
  - --all with no drafts: exits 0 gracefully
  - Wrapped {"jurisdictions": [...]} top-level format handled
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.promote_source_pack_drafts as promoter  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture jurisdiction blocks (re-used across test classes)
# ---------------------------------------------------------------------------

_MUNICIPALITY_JUR: dict = {
    "jurisdiction_id": "testcity-va",
    "name": "Test City, VA",
    "state": "VA",
    "state_fips": "51",
    "county_fips": "500",
    "place_fips": "99999",
    "jurisdiction_type": "municipality",
    "coverage_status": "source_discovery",
    "official_source_urls": ["https://example.com/zoning"],
    "zoning_map_url": "https://example.com/map",
    "planning_contact": {
        "department": "Planning",
        "url": "https://example.com",
        "phone": "555-1234",
    },
    "county_name": "Test County",
}

_COUNTY_JUR: dict = {
    "jurisdiction_id": "testcounty-va",
    "name": "Test County, VA",
    "state": "VA",
    "state_fips": "51",
    "county_fips": "501",
    "jurisdiction_type": "county",
    "coverage_status": "source_discovery",
    "official_source_urls": ["https://example.com/county"],
    "zoning_map_url": "https://example.com/county-map",
    "planning_contact": {
        "department": "County Planning",
        "url": "https://example.com/cp",
    },
    "county_name": "Test County",
}

_INDEP_CITY_JUR: dict = {
    "jurisdiction_id": "testindep-va",
    "name": "Test Indep, VA",
    "state": "VA",
    "state_fips": "51",
    "county_fips": "502",
    "place_fips": "88888",
    "jurisdiction_type": "independent_city",
    "coverage_status": "source_discovery",
    "official_source_urls": ["https://example.com/indep"],
    "zoning_map_url": "https://example.com/indep-map",
    "planning_contact": {
        "department": "City Planning",
        "url": "https://example.com/cp",
    },
}


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_draft(
    tmp_path: Path,
    jurisdiction: dict,
    sources: list[dict] | None = None,
    state: str = "va",
) -> Path:
    """Write a minimal but schema-valid draft manifest.json and return its path."""
    jid = jurisdiction["jurisdiction_id"]
    if sources is None:
        sources = [
            {
                "source_id": f"{jid}-sec-1",
                "title": "Section 1.",
                "excerpt": "Test excerpt.",
                "section_ref": "Sec. 1.",
                "jurisdiction_id": jid,
                "url": "https://example.com/sec1",
                "effective_date": "2024-01-01",
                "districts": ["unknown"],
                "uses": ["general"],
                "source_type": "zoning_ordinance",
            },
            {
                "source_id": f"{jid}-sec-2",
                "title": "Section 2.",
                "excerpt": "Test excerpt 2.",
                "section_ref": "Sec. 2.",
                "jurisdiction_id": jid,
                "url": "https://example.com/sec2",
                "effective_date": "2024-01-01",
                "districts": ["unknown"],
                "uses": ["food-service"],
                "source_type": "planning_page",
            },
        ]

    manifest = {
        "schema_version": "source-pack/v1",
        "jurisdiction": jurisdiction,
        "verification_notes": "Draft generated by scraper.",
        "sources": sources,
        "scrape_provenance": {"fetcher": "test", "retrieved_at": "2026-01-01"},
    }
    draft_dir = tmp_path / "drafts" / state / jid
    draft_dir.mkdir(parents=True, exist_ok=True)
    path = draft_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _make_jurisdictions_file(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a bare-list jurisdictions.json and return its path."""
    path = tmp_path / "jurisdictions.json"
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return path


def _do_promote(
    tmp_path: Path,
    jurisdiction_id: str,
    *,
    state: str | None = "va",
    jurisdictions_file: Path | None = None,
) -> dict:
    """Convenience wrapper that builds default paths and calls promote_draft."""
    drafts_dir = tmp_path / "drafts"
    packs_dir = tmp_path / "packs"
    jfile = jurisdictions_file or (tmp_path / "jurisdictions.json")
    return promoter.promote_draft(
        jurisdiction_id,
        drafts_dir=drafts_dir,
        source_packs_dir=packs_dir,
        jurisdictions_file=jfile,
        state=state,
    )


def _load_pack(tmp_path: Path, jid: str, state: str = "va") -> dict:
    path = tmp_path / "packs" / state / jid / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jurisdictions(tmp_path: Path) -> list[dict]:
    path = tmp_path / "jurisdictions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("jurisdictions", [])
    return data


# ---------------------------------------------------------------------------
# 1. Curated source pack output
# ---------------------------------------------------------------------------


class TestCuratedPackOutput:
    def test_pack_written_at_correct_path(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        assert (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").exists()

    def test_coverage_status_forced_source_indexed(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        assert pack["jurisdiction"]["coverage_status"] == "source_indexed"

    def test_never_writes_public_supported(self, tmp_path):
        """Even if the draft has public_supported, output must be source_indexed."""
        jur = dict(_MUNICIPALITY_JUR)
        jur["coverage_status"] = "public_supported"
        _make_draft(tmp_path, jur)
        _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        assert pack["jurisdiction"]["coverage_status"] != "public_supported"
        assert pack["jurisdiction"]["coverage_status"] == "source_indexed"

    def test_schema_version_set(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        assert pack["schema_version"] == "source-pack/v1"

    def test_sources_preserved_verbatim(self, tmp_path):
        custom_sources = [
            {
                "source_id": "testcity-va-custom",
                "title": "Custom Section",
                "excerpt": "Custom excerpt.",
                "section_ref": "Sec. X.",
                "jurisdiction_id": "testcity-va",
                "url": "https://example.com/custom",
                "effective_date": "2024-06-01",
                "districts": ["unknown"],
                "uses": ["food-service", "general"],
                "source_type": "zoning_ordinance",
            }
        ]
        _make_draft(tmp_path, _MUNICIPALITY_JUR, sources=custom_sources)
        result = _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        assert pack["sources"] == custom_sources
        assert result["sources"] == 1

    def test_district_tags_preserved_as_unknown(self, tmp_path):
        """districts=["unknown"] from scraper must be preserved (no reclassification)."""
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        for src in pack["sources"]:
            assert src["districts"] == ["unknown"]

    def test_parent_jurisdiction_id_present(self, tmp_path):
        """Source pack jurisdiction block must have parent_jurisdiction_id (null ok)."""
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        pack = _load_pack(tmp_path, "testcity-va")
        assert "parent_jurisdiction_id" in pack["jurisdiction"]

    def test_trailing_newline(self, tmp_path):
        """JSON files must end with a trailing newline (style convention)."""
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        raw = (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").read_bytes()
        assert raw.endswith(b"\n")

    def test_result_reports_source_count(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        result = _do_promote(tmp_path, "testcity-va")
        assert result["sources"] == 2  # default fixture has 2 sources


# ---------------------------------------------------------------------------
# 2. jurisdictions.json entry derivation
# ---------------------------------------------------------------------------


class TestJurisdictionsEntry:
    def _promote_and_get_entry(self, tmp_path: Path, jur: dict) -> dict:
        _make_draft(tmp_path, jur)
        _do_promote(tmp_path, jur["jurisdiction_id"])
        entries = _load_jurisdictions(tmp_path)
        matches = [e for e in entries if e.get("jurisdiction_id") == jur["jurisdiction_id"]]
        assert len(matches) == 1, f"Expected exactly 1 entry, got {len(matches)}"
        return matches[0]

    def test_coverage_status_forced_source_indexed(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["coverage_status"] == "source_indexed"

    def test_supported_false(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["supported"] is False

    # --- locality_names ---

    def test_municipality_locality_names(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["locality_names"] == ["Test City"]

    def test_county_locality_names(self, tmp_path):
        """County: locality_names is derived from jurisdiction name."""
        entry = self._promote_and_get_entry(tmp_path, _COUNTY_JUR)
        assert entry["locality_names"] == ["Test County"]

    def test_independent_city_locality_names(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _INDEP_CITY_JUR)
        assert entry["locality_names"] == ["Test Indep"]

    # --- county_names ---

    def test_municipality_county_names_from_county_name_field(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["county_names"] == ["Test County"]

    def test_county_county_names(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _COUNTY_JUR)
        assert entry["county_names"] == ["Test County"]

    def test_independent_city_county_names_variants(self, tmp_path):
        """independent_city: both '<X> City' and 'City of <X>' variants."""
        entry = self._promote_and_get_entry(tmp_path, _INDEP_CITY_JUR)
        assert "Test Indep City" in entry["county_names"]
        assert "City of Test Indep" in entry["county_names"]
        assert len(entry["county_names"]) == 2

    # --- match_strategy ---

    def test_municipality_match_strategy(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["match_strategy"] == "locality"

    def test_county_match_strategy(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _COUNTY_JUR)
        assert entry["match_strategy"] == "county"

    def test_independent_city_match_strategy(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _INDEP_CITY_JUR)
        assert entry["match_strategy"] == "locality_and_county"

    # --- state_names ---

    def test_state_names_va(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert "VA" in entry["state_names"]
        assert "Virginia" in entry["state_names"]

    # --- district_mapping_strategy ---

    def test_district_mapping_strategy(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["district_mapping_strategy"] == (
            "source_indexed_until_city_zoning_code_and_gis_layers_qa_pass"
        )

    # --- last_verified_at ---

    def test_last_verified_at_is_today(self, tmp_path):
        entry = self._promote_and_get_entry(tmp_path, _MUNICIPALITY_JUR)
        assert entry["last_verified_at"] == date.today().isoformat()

    # --- jurisdictions.json format ---

    def test_jurisdictions_file_trailing_newline(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        raw = (tmp_path / "jurisdictions.json").read_bytes()
        assert raw.endswith(b"\n")


# ---------------------------------------------------------------------------
# 3. Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_pack_byte_identical_on_second_run(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        first = (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").read_bytes()
        _do_promote(tmp_path, "testcity-va")
        second = (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").read_bytes()
        assert first == second

    def test_jurisdictions_no_duplicate_on_second_run(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        _do_promote(tmp_path, "testcity-va")
        entries = _load_jurisdictions(tmp_path)
        matches = [e for e in entries if e.get("jurisdiction_id") == "testcity-va"]
        assert len(matches) == 1

    def test_jurisdictions_file_byte_identical_on_second_run(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va")
        first = (tmp_path / "jurisdictions.json").read_bytes()
        _do_promote(tmp_path, "testcity-va")
        second = (tmp_path / "jurisdictions.json").read_bytes()
        assert first == second


# ---------------------------------------------------------------------------
# 4. Update path (pre-existing entry replaced in place)
# ---------------------------------------------------------------------------


class TestUpdateExistingEntry:
    def test_existing_entry_replaced_with_new_fields(self, tmp_path):
        """Pre-seeded entry is replaced; coverage_status and supported are updated."""
        old_entry = {
            "jurisdiction_id": "testcity-va",
            "name": "Old Name, VA",
            "coverage_status": "source_discovery",
            "supported": True,
        }
        jfile = _make_jurisdictions_file(tmp_path, [old_entry])
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va", jurisdictions_file=jfile)

        entries = json.loads(jfile.read_text(encoding="utf-8"))
        matches = [e for e in entries if e.get("jurisdiction_id") == "testcity-va"]
        assert len(matches) == 1
        assert matches[0]["coverage_status"] == "source_indexed"
        assert matches[0]["supported"] is False

    def test_other_entries_untouched(self, tmp_path):
        """Entries for other jurisdiction_ids are preserved unchanged."""
        other_entry = {
            "jurisdiction_id": "other-va",
            "name": "Other City, VA",
            "coverage_status": "public_supported",
            "supported": True,
        }
        jfile = _make_jurisdictions_file(tmp_path, [other_entry])
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va", jurisdictions_file=jfile)

        entries = json.loads(jfile.read_text(encoding="utf-8"))
        other = [e for e in entries if e.get("jurisdiction_id") == "other-va"]
        assert len(other) == 1
        assert other[0]["coverage_status"] == "public_supported"

    def test_jurisdiction_action_added_when_new(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        result = _do_promote(tmp_path, "testcity-va")
        assert result["jurisdiction_action"] == "added"

    def test_jurisdiction_action_updated_when_existing(self, tmp_path):
        old_entry = {"jurisdiction_id": "testcity-va", "name": "Old, VA"}
        jfile = _make_jurisdictions_file(tmp_path, [old_entry])
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        result = _do_promote(tmp_path, "testcity-va", jurisdictions_file=jfile)
        assert result["jurisdiction_action"] == "updated"

    def test_wrapped_format_preserved(self, tmp_path):
        """If jurisdictions.json uses {"jurisdictions": [...]} wrapper, preserve it."""
        wrapped = {"jurisdictions": []}
        jfile = tmp_path / "jurisdictions.json"
        jfile.write_text(json.dumps(wrapped, indent=2) + "\n", encoding="utf-8")
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _do_promote(tmp_path, "testcity-va", jurisdictions_file=jfile)
        data = json.loads(jfile.read_text(encoding="utf-8"))
        # Must still be the wrapped format.
        assert isinstance(data, dict)
        assert "jurisdictions" in data
        matches = [
            e for e in data["jurisdictions"]
            if e.get("jurisdiction_id") == "testcity-va"
        ]
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# 5. Missing draft
# ---------------------------------------------------------------------------


class TestMissingDraft:
    def test_missing_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="(?i)not found|no draft"):
            promoter.promote_draft(
                "nonexistent-va",
                drafts_dir=tmp_path / "drafts",
                source_packs_dir=tmp_path / "packs",
                jurisdictions_file=tmp_path / "jurisdictions.json",
                state="va",
            )

    def test_main_exits_nonzero_on_missing_draft(self, tmp_path):
        rc = promoter.main([
            "--id", "nonexistent-va",
            "--state", "va",
            "--drafts-dir", str(tmp_path / "drafts"),
            "--source-packs-dir", str(tmp_path / "packs"),
            "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
        ])
        assert rc != 0


# ---------------------------------------------------------------------------
# 6. County-type draft
# ---------------------------------------------------------------------------


class TestCountyDraftPromotion:
    def _promote_county(self, tmp_path: Path) -> dict:
        _make_draft(tmp_path, _COUNTY_JUR)
        _do_promote(tmp_path, "testcounty-va")
        entries = _load_jurisdictions(tmp_path)
        return next(e for e in entries if e["jurisdiction_id"] == "testcounty-va")

    def test_locality_names_from_jurisdiction_name(self, tmp_path):
        """County locality_names strips state suffix from 'Test County, VA'."""
        entry = self._promote_county(tmp_path)
        assert entry["locality_names"] == ["Test County"]

    def test_county_names_from_county_name_field(self, tmp_path):
        entry = self._promote_county(tmp_path)
        assert entry["county_names"] == ["Test County"]

    def test_match_strategy_county(self, tmp_path):
        entry = self._promote_county(tmp_path)
        assert entry["match_strategy"] == "county"

    def test_pack_written_for_county(self, tmp_path):
        _make_draft(tmp_path, _COUNTY_JUR)
        _do_promote(tmp_path, "testcounty-va")
        assert (tmp_path / "packs" / "va" / "testcounty-va" / "manifest.json").exists()


# ---------------------------------------------------------------------------
# 7. CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def test_single_id_exits_zero(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        rc = promoter.main([
            "--id", "testcity-va",
            "--state", "va",
            "--drafts-dir", str(tmp_path / "drafts"),
            "--source-packs-dir", str(tmp_path / "packs"),
            "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
        ])
        assert rc == 0

    def test_single_id_pack_exists_after_cli(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        promoter.main([
            "--id", "testcity-va",
            "--state", "va",
            "--drafts-dir", str(tmp_path / "drafts"),
            "--source-packs-dir", str(tmp_path / "packs"),
            "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
        ])
        assert (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").exists()

    def test_all_flag_promotes_multiple_drafts(self, tmp_path):
        _make_draft(tmp_path, _MUNICIPALITY_JUR)
        _make_draft(tmp_path, _COUNTY_JUR)
        rc = promoter.main([
            "--all",
            "--state", "va",
            "--drafts-dir", str(tmp_path / "drafts"),
            "--source-packs-dir", str(tmp_path / "packs"),
            "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
        ])
        assert rc == 0
        assert (tmp_path / "packs" / "va" / "testcity-va" / "manifest.json").exists()
        assert (tmp_path / "packs" / "va" / "testcounty-va" / "manifest.json").exists()

    def test_all_flag_no_drafts_exits_zero(self, tmp_path):
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        rc = promoter.main([
            "--all",
            "--drafts-dir", str(drafts_dir),
            "--source-packs-dir", str(tmp_path / "packs"),
            "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
        ])
        assert rc == 0

    def test_missing_required_arg_exits_nonzero(self, tmp_path):
        """Running without --id or --all must exit with a non-zero code."""
        with pytest.raises(SystemExit) as exc:
            promoter.main([
                "--drafts-dir", str(tmp_path / "drafts"),
                "--source-packs-dir", str(tmp_path / "packs"),
                "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
            ])
        assert exc.value.code != 0

    def test_both_id_and_all_exits_nonzero(self, tmp_path):
        """--id and --all are mutually exclusive."""
        with pytest.raises(SystemExit) as exc:
            promoter.main([
                "--id", "testcity-va",
                "--all",
                "--drafts-dir", str(tmp_path / "drafts"),
                "--source-packs-dir", str(tmp_path / "packs"),
                "--jurisdictions-file", str(tmp_path / "jurisdictions.json"),
            ])
        assert exc.value.code != 0


class TestCleanFips:
    """FIPS sanitization: placeholders and invalid values must not be written."""

    def test_clean_fips_keeps_valid_numeric_codes(self):
        assert promoter._clean_fips("51") == "51"
        assert promoter._clean_fips("51840") == "51840"

    def test_clean_fips_drops_todo_placeholders(self):
        # discover skeleton placeholders exceed JurisdictionRecord max_length=10.
        assert promoter._clean_fips("TODO_COUNTY_FIPS") is None
        assert promoter._clean_fips("TODO_PLACE_FIPS") is None

    def test_clean_fips_drops_empty_and_non_string(self):
        assert promoter._clean_fips("") is None
        assert promoter._clean_fips(None) is None
        assert promoter._clean_fips(12345) is None

    def test_build_entry_nulls_placeholder_fips(self):
        jur = {
            "jurisdiction_id": "winchester-va",
            "name": "Winchester, VA",
            "state": "VA",
            "county_fips": "TODO_COUNTY_FIPS",
            "place_fips": "TODO_PLACE_FIPS",
            "jurisdiction_type": "independent_city",
        }
        entry = promoter._build_jurisdiction_entry(jur)
        assert entry["county_fips"] is None
        assert entry["place_fips"] is None
