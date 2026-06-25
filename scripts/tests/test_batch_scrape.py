"""Unit tests for scripts/batch_scrape.py.

All tests are fully offline — no live network, no file-system side effects
from the real scraper or validator.  ``_scraper_run`` and ``_validate_draft``
are monkeypatched in every test that exercises the batch loop.

Covered:
  - city-list JSON parsing (valid, missing fields, wrong type, bad file)
  - ``_entry_to_namespace`` field mapping and defaults
  - ``run_batch`` continue-on-error when a city's run() returns non-zero
  - ``run_batch`` continue-on-error when a city's run() raises SystemExit
  - report aggregation shape and counters
  - ``--skip-existing`` skips a city whose draft already validates
  - ``BatchReport.to_dict()`` contains the required safety note
  - ``main()`` exit codes (0 on success, 1 on any failure/block)
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on path (also done by conftest.py, but be explicit).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.batch_scrape as bs  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_city_list(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a JSON city-list file and return its path."""
    p = tmp_path / "cities.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def _minimal_entry(city: str = "TestCity", state: str = "VA") -> dict:
    return {"city": city, "state": state}


# ---------------------------------------------------------------------------
# 1. City-list parsing
# ---------------------------------------------------------------------------


class TestParseCityList:
    def test_valid_minimal_entries(self, tmp_path):
        p = _make_city_list(tmp_path, [{"city": "Foo", "state": "VA"}])
        entries = bs.parse_city_list(p)
        assert len(entries) == 1
        assert entries[0]["city"] == "Foo"
        assert entries[0]["state"] == "VA"

    def test_multiple_entries(self, tmp_path):
        data = [
            {"city": "Alpha", "state": "VA"},
            {"city": "Beta", "state": "NC", "county": "Wake", "fetcher": "generic_html"},
        ]
        p = _make_city_list(tmp_path, data)
        entries = bs.parse_city_list(p)
        assert len(entries) == 2
        assert entries[1]["county"] == "Wake"

    def test_missing_city_raises(self, tmp_path):
        p = _make_city_list(tmp_path, [{"state": "VA"}])
        with pytest.raises(ValueError, match="missing required field"):
            bs.parse_city_list(p)

    def test_missing_state_raises(self, tmp_path):
        p = _make_city_list(tmp_path, [{"city": "Foo"}])
        with pytest.raises(ValueError, match="missing required field"):
            bs.parse_city_list(p)

    def test_not_array_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"city": "Foo", "state": "VA"}))
        with pytest.raises(ValueError, match="JSON array"):
            bs.parse_city_list(p)

    def test_nonobject_entry_raises(self, tmp_path):
        p = _make_city_list(tmp_path, ["not-a-dict"])
        with pytest.raises(ValueError, match="JSON object"):
            bs.parse_city_list(p)

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "nope.json"
        with pytest.raises(ValueError, match="Cannot read"):
            bs.parse_city_list(missing)

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json!", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot read"):
            bs.parse_city_list(p)

    def test_optional_fields_preserved(self, tmp_path):
        entry = {
            "city": "Blacksburg",
            "state": "VA",
            "county": "Montgomery",
            "fetcher": "municode",
            "max_sections": 10,
            "delay": 2.5,
            "jurisdiction_id": "blacksburg-va",
            "jurisdiction_type": "municipality",
            "coverage_status": "source_indexed",
            "url": ["https://example.com"],
            "host_slug": "blacksburg",
            "chapters": ["10_ZONING"],
            "county_fips": "121",
            "place_fips": "08720",
            "county_name": "Montgomery County",
        }
        p = _make_city_list(tmp_path, [entry])
        entries = bs.parse_city_list(p)
        assert entries[0]["fetcher"] == "municode"
        assert entries[0]["max_sections"] == 10
        assert entries[0]["county_fips"] == "121"


# ---------------------------------------------------------------------------
# 2. _entry_to_namespace field mapping
# ---------------------------------------------------------------------------


class TestEntryToNamespace:
    def test_minimal_entry_defaults(self, tmp_path):
        entry = {"city": "TestCity", "state": "VA"}
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=None)
        assert ns.city == "TestCity"
        assert ns.state == "VA"
        assert ns.fetcher == "municode"
        assert ns.delay == 1.0
        assert ns.max_sections is None
        assert ns.output_root == tmp_path

    def test_fetcher_override(self, tmp_path):
        entry = {"city": "Foo", "state": "VA", "fetcher": "generic_html", "url": ["https://x.com"]}
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=None)
        assert ns.fetcher == "generic_html"
        assert ns.url == ["https://x.com"]

    def test_delay_priority(self, tmp_path):
        # Per-entry delay overrides global delay.
        entry = {"city": "Foo", "state": "VA", "delay": 3.0}
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=5.0)
        assert ns.delay == 3.0

    def test_global_delay_used_when_no_entry_delay(self, tmp_path):
        entry = {"city": "Foo", "state": "VA"}
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=2.5)
        assert ns.delay == 2.5

    def test_municipalcodeonline_fields(self, tmp_path):
        entry = {
            "city": "Montgomery County",
            "state": "VA",
            "fetcher": "municipalcodeonline",
            "host_slug": "montgomery",
            "chapters": ["10_ZONING"],
        }
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=None)
        assert ns.host_slug == "montgomery"
        assert ns.chapters == ["10_ZONING"]

    def test_max_sections_passed_through(self, tmp_path):
        entry = {"city": "Foo", "state": "VA", "max_sections": 3}
        ns = bs._entry_to_namespace(entry, output_root=tmp_path, global_delay=None)
        assert ns.max_sections == 3

    def test_output_root_always_batch_level(self, tmp_path):
        # Even if the entry tried to specify output_root it would be ignored;
        # the batch level always wins.
        entry = {"city": "Foo", "state": "VA"}
        custom_root = tmp_path / "custom"
        ns = bs._entry_to_namespace(entry, output_root=custom_root, global_delay=None)
        assert ns.output_root == custom_root


# ---------------------------------------------------------------------------
# 3. run_batch — continue-on-error
# ---------------------------------------------------------------------------


def _noop_validate(draft_root, jurisdiction_id):
    """Stub: always returns (True, 0, 0) for any city.

    Signature mirrors the real ``_validate_draft(draft_root, jurisdiction_id)``
    which is now per-city scoped.
    """
    return True, 0, 0


class TestRunBatchContinueOnError:
    """Tests that a failed/blocked city does not abort the batch."""

    def test_one_failed_one_ok(self, tmp_path, monkeypatch):
        """First city fails (exit 1), second succeeds (exit 0). Both run."""
        call_order = []

        def fake_run(ns):
            call_order.append(ns.city)
            if ns.city == "FailCity":
                return 1
            # For OkCity, pretend a manifest was written.
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"sources": [{"id": "s1"}]}), encoding="utf-8"
            )
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [
            {"city": "FailCity", "state": "VA"},
            {"city": "OkCity", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)

        # Both cities were attempted.
        assert call_order == ["FailCity", "OkCity"]
        assert report.total == 2
        assert report.failed == 1
        assert report.scraped == 1

    def test_one_blocked_one_ok(self, tmp_path, monkeypatch):
        """First city is blocked (exit 2), second succeeds."""
        call_order = []

        def fake_run(ns):
            call_order.append(ns.city)
            if ns.city == "BlockedCity":
                return 2
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [
            {"city": "BlockedCity", "state": "VA"},
            {"city": "OkCity", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)

        assert call_order == ["BlockedCity", "OkCity"]
        assert report.blocked == 1
        assert report.scraped == 1
        assert report.failed == 0

    def test_systemexit_from_scraper_treated_as_failure(self, tmp_path, monkeypatch):
        """SystemExit from the scraper (e.g. bad fetcher args) is caught, not propagated."""
        call_order = []

        def fake_run(ns):
            call_order.append(ns.city)
            if ns.city == "BadArgs":
                raise SystemExit("--fetcher generic_html requires at least one --url.")
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": [{"id": "x"}]}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [
            {"city": "BadArgs", "state": "VA"},
            {"city": "GoodCity", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)

        assert call_order == ["BadArgs", "GoodCity"]
        assert report.failed == 1
        assert report.scraped == 1
        # SystemExit message captured.
        bad = next(c for c in report.cities if c.city == "BadArgs")
        assert "SystemExit" in bad.error_detail

    def test_exception_from_scraper_treated_as_failure(self, tmp_path, monkeypatch):
        """A generic Exception from the scraper is caught, not propagated."""
        def fake_run(ns):
            raise RuntimeError("network timeout")

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [{"city": "CrashCity", "state": "VA"}]
        report = bs.run_batch(entries, output_root=tmp_path)

        assert report.failed == 1
        assert report.scraped == 0
        assert "network timeout" in report.cities[0].error_detail

    def test_all_failed_gives_zero_scraped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bs, "_scraper_run", lambda ns: 1)

        entries = [
            {"city": "A", "state": "VA"},
            {"city": "B", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)
        assert report.scraped == 0
        assert report.failed == 2
        assert report.validated_ok == 0


# ---------------------------------------------------------------------------
# 4. Report aggregation shape
# ---------------------------------------------------------------------------


class TestBatchReportShape:
    def test_to_dict_has_required_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bs, "_scraper_run", lambda ns: 1)

        entries = [{"city": "X", "state": "VA"}]
        report = bs.run_batch(entries, output_root=tmp_path)
        d = report.to_dict()

        assert "run_at" in d
        assert "summary" in d
        assert "cities" in d
        assert "note" in d
        # Safety note must be present.
        assert "DRAFTS ONLY" in d["note"]
        assert "reindex" in d["note"].lower()

    def test_summary_counters_are_correct(self, tmp_path, monkeypatch):
        def fake_run(ns):
            if ns.city == "Ok":
                manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(json.dumps({"sources": [{"id": "1"}, {"id": "2"}]}), encoding="utf-8")
                return 0
            return 2  # blocked

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [
            {"city": "Ok", "state": "VA"},
            {"city": "Blocked", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)
        d = report.to_dict()

        assert d["summary"]["total"] == 2
        assert d["summary"]["scraped"] == 1
        assert d["summary"]["blocked"] == 1
        assert d["summary"]["failed"] == 0

    def test_per_city_section_count_recorded(self, tmp_path, monkeypatch):
        def fake_run(ns):
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"sources": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]}),
                encoding="utf-8",
            )
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        entries = [{"city": "SectionCity", "state": "VA"}]
        report = bs.run_batch(entries, output_root=tmp_path)

        assert report.cities[0].section_count == 3


# ---------------------------------------------------------------------------
# 4b. Per-city validation scoping (Fix 1)
# ---------------------------------------------------------------------------


class _FakeSummary:
    """Mimics validate_source_packs' JurisdictionSummary."""

    def __init__(self, jurisdiction_id, error_count=0, warning_count=0):
        self.jurisdiction_id = jurisdiction_id
        self.error_count = error_count
        self.warning_count = warning_count


class _FakeResult:
    def __init__(self, summaries):
        self.summaries = summaries
        self.errors = []
        self.warnings = []

    @property
    def ok(self):
        return True


class TestPerCityValidationScoping:
    """Fix 1: validation counts are scoped to THIS city, not the whole root."""

    def test_one_city_error_does_not_leak_onto_clean_city(self, tmp_path, monkeypatch):
        """City A is clean; City B has an error. A's row must stay clean."""

        def fake_run(ns):
            jid = ns.jurisdiction_id or f"{ns.city.lower()}-{ns.state.lower()}"
            manifest = tmp_path / ns.state.lower() / jid / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": [{"id": "1"}]}), encoding="utf-8")
            return 0

        # The validator always reports A clean and B with 2 errors, regardless
        # of which city triggered the call (the whole root is walked each time).
        fake_summaries = [
            _FakeSummary("citya-va", error_count=0, warning_count=1),
            _FakeSummary("cityb-va", error_count=2, warning_count=0),
        ]

        def fake_validate(root):
            return _FakeResult(fake_summaries)

        fake_validator = MagicMock()
        fake_validator.validate_source_packs = fake_validate

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_load_validate_module", lambda: fake_validator)

        entries = [
            {"city": "CityA", "state": "VA"},
            {"city": "CityB", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path)

        a = next(c for c in report.cities if c.jurisdiction_id == "citya-va")
        b = next(c for c in report.cities if c.jurisdiction_id == "cityb-va")

        # City A stays clean even though City B has errors in the same root.
        assert a.validation_ok is True
        assert a.validation_errors == 0
        assert a.validation_warnings == 1
        # City B reflects only its own errors.
        assert b.validation_ok is False
        assert b.validation_errors == 2
        assert b.validation_warnings == 0

    def test_missing_summary_is_graceful_failure(self, tmp_path, monkeypatch):
        """If no summary matches the city's id, record a graceful failure."""

        def fake_run(ns):
            jid = ns.jurisdiction_id or f"{ns.city.lower()}-{ns.state.lower()}"
            manifest = tmp_path / ns.state.lower() / jid / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        def fake_validate(root):
            return _FakeResult([])  # no summaries at all

        fake_validator = MagicMock()
        fake_validator.validate_source_packs = fake_validate

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_load_validate_module", lambda: fake_validator)

        entries = [{"city": "Orphan", "state": "VA"}]
        report = bs.run_batch(entries, output_root=tmp_path)

        c = report.cities[0]
        assert c.validation_ok is False
        assert c.validation_errors == 1


# ---------------------------------------------------------------------------
# 5. --skip-existing
# ---------------------------------------------------------------------------


class TestSkipExisting:
    def test_skip_when_draft_validates(self, tmp_path, monkeypatch):
        """City with an existing validated draft should be skipped; scraper not called."""
        scraper_calls = []

        def fake_run(ns):
            scraper_calls.append(ns.city)
            return 0

        # Pretend the draft already validates.
        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)
        monkeypatch.setattr(bs, "_draft_validates", lambda root, state, jid: True)

        entries = [{"city": "AlreadyDone", "state": "VA", "jurisdiction_id": "alreadydone-va"}]
        report = bs.run_batch(entries, output_root=tmp_path, skip_existing=True)

        # Scraper was NOT called.
        assert scraper_calls == []
        assert report.skipped == 1
        assert report.scraped == 0
        assert report.cities[0].status == bs.SCRAPE_SKIPPED

    def test_no_skip_when_draft_absent(self, tmp_path, monkeypatch):
        """City with no existing draft should be scraped even with --skip-existing."""
        scraper_calls = []

        def fake_run(ns):
            scraper_calls.append(ns.city)
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)
        monkeypatch.setattr(bs, "_draft_validates", lambda root, state, jid: False)

        entries = [{"city": "NewCity", "state": "VA"}]
        report = bs.run_batch(entries, output_root=tmp_path, skip_existing=True)

        assert scraper_calls == ["NewCity"]
        assert report.scraped == 1
        assert report.skipped == 0

    def test_skip_mixes_with_normal(self, tmp_path, monkeypatch):
        """Some cities skipped, others scraped — all tracked correctly."""
        scraper_calls = []

        def fake_draft_validates(root, state, jid):
            return jid == "existing-va"

        def fake_run(ns):
            scraper_calls.append(ns.city)
            manifest = tmp_path / ns.state.lower() / f"{ns.jurisdiction_id or ns.city.lower() + '-' + ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)
        monkeypatch.setattr(bs, "_draft_validates", fake_draft_validates)

        entries = [
            {"city": "Existing", "state": "VA", "jurisdiction_id": "existing-va"},
            {"city": "NewCity", "state": "VA"},
        ]
        report = bs.run_batch(entries, output_root=tmp_path, skip_existing=True)

        assert "NewCity" in scraper_calls
        assert "Existing" not in scraper_calls
        assert report.skipped == 1
        assert report.scraped == 1


# ---------------------------------------------------------------------------
# 6. main() exit codes
# ---------------------------------------------------------------------------


class TestMainExitCodes:
    def test_exit_0_on_all_success(self, tmp_path, monkeypatch):
        city_list = _make_city_list(tmp_path, [{"city": "OkCity", "state": "VA"}])

        def fake_run(ns):
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        rc = bs.main(["--city-list", str(city_list), "--output-root", str(tmp_path)])
        assert rc == 0

    def test_exit_1_on_any_failure(self, tmp_path, monkeypatch):
        city_list = _make_city_list(tmp_path, [{"city": "FailCity", "state": "VA"}])
        monkeypatch.setattr(bs, "_scraper_run", lambda ns: 1)

        rc = bs.main(["--city-list", str(city_list), "--output-root", str(tmp_path)])
        assert rc == 1

    def test_exit_1_on_any_block(self, tmp_path, monkeypatch):
        city_list = _make_city_list(tmp_path, [{"city": "BlockedCity", "state": "VA"}])
        monkeypatch.setattr(bs, "_scraper_run", lambda ns: 2)

        rc = bs.main(["--city-list", str(city_list), "--output-root", str(tmp_path)])
        assert rc == 1

    def test_exit_1_on_bad_city_list(self, tmp_path):
        bad_list = tmp_path / "bad.json"
        bad_list.write_text("{}", encoding="utf-8")  # object, not array

        rc = bs.main(["--city-list", str(bad_list), "--output-root", str(tmp_path)])
        assert rc == 1

    def test_report_file_written(self, tmp_path, monkeypatch):
        city_list = _make_city_list(tmp_path, [{"city": "City1", "state": "VA"}])

        def fake_run(ns):
            manifest = tmp_path / ns.state.lower() / f"{ns.city.lower()}-{ns.state.lower()}" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            return 0

        monkeypatch.setattr(bs, "_scraper_run", fake_run)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)

        bs.main(["--city-list", str(city_list), "--output-root", str(tmp_path)])

        report_file = tmp_path / "_batch_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert "DRAFTS ONLY" in data["note"]
        assert data["summary"]["total"] == 1

    def test_skip_existing_flag_wired(self, tmp_path, monkeypatch):
        """--skip-existing is passed through to run_batch."""
        city_list = _make_city_list(
            tmp_path,
            [{"city": "AlreadyDone", "state": "VA", "jurisdiction_id": "alreadydone-va"}],
        )
        monkeypatch.setattr(bs, "_scraper_run", lambda ns: 0)
        monkeypatch.setattr(bs, "_validate_draft", _noop_validate)
        monkeypatch.setattr(bs, "_draft_validates", lambda root, state, jid: True)

        rc = bs.main([
            "--city-list", str(city_list),
            "--output-root", str(tmp_path),
            "--skip-existing",
        ])
        assert rc == 0
