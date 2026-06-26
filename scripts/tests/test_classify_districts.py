"""Unit tests for scripts/classify_districts.py (Stage 4 — LLM district classifier).

All tests are fully OFFLINE — no live network calls, no GROQ_API_KEY required.
The LLM function (``llm_fn``) is injected as a stub in every test that exercises
classification logic.

Covered:
  - Closed vocab constants (DISTRICT_VOCAB, USES_VOCAB) are correct
  - group_sections: correct grouping by (article, division) breadcrumb pair
  - group_sections: handles missing/empty breadcrumbs gracefully
  - parse_llm_response: valid JSON, off-vocab terms, malformed JSON, non-object JSON
  - parse_llm_response: markdown-fenced response (LLM ignores instruction)
  - coerce_vocab: off-vocab districts → unknown, off-vocab uses → general
  - coerce_vocab: deduplication, empty list fallback
  - classify_group: high-confidence → specific classification
  - classify_group: low-confidence (below threshold) → unknown/general fallback
  - classify_group: LLM call exception → safe fallback, error recorded
  - classify_group: malformed JSON from LLM → safe fallback, error recorded
  - classify_group: off-vocab LLM output → coerced, coerced=True flag
  - results_to_rules: shape matches source-classification-rules/v1
  - results_to_rules: pure-default groups omitted from rules list
  - results_to_rules: schema_version field present
  - load_manifest: valid fixture, missing sources key, bad JSON, missing file
  - write_outputs: creates classification_rules.json + _classification_report.json
  - Integration: emitted rules file classifies a SourceRegistryEntry correctly
    via the real source_classifier.py loader (pure function test, no app imports)
  - Integration: run_classification with stubbed LLM over full fixture manifest
  - main() exit codes (0 on success, 1 on missing manifest, 1 on missing API key)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import pytest

# Ensure repo root is on path (also done by conftest.py, but be explicit).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.classify_districts as cd  # noqa: E402

# Fixture directory.
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "classify_districts"


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _load_fixture_response(name: str) -> str:
    """Return the stub LLM response string from a fixture file."""
    path = _FIXTURES / name
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["response"]


def _make_stub_llm(*responses: str) -> Callable[[str], str]:
    """Return an injectable LLM stub that yields responses in sequence.

    After the sequence is exhausted, returns a safe default JSON string.
    """
    it = iter(responses)

    def _stub(prompt: str) -> str:  # noqa: ARG001
        try:
            return next(it)
        except StopIteration:
            return json.dumps(
                {
                    "districts": ["unknown"],
                    "uses": ["general"],
                    "rationale": "stub exhausted",
                    "confidence": 0.5,
                }
            )

    return _stub


def _make_manifest(tmp_path: Path, sources: list[dict]) -> Path:
    """Write a minimal manifest.json and return its path."""
    manifest = {
        "schema_version": "source-pack/v1",
        "jurisdiction": {"jurisdiction_id": "test-va"},
        "sources": sources,
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def _make_source(
    source_id: str,
    title: str,
    breadcrumb: list[str],
) -> dict:
    return {
        "source_id": source_id,
        "title": title,
        "section_ref": source_id,
        "jurisdiction_id": "test-va",
        "url": "https://example.com",
        "effective_date": "2024-01-01",
        "districts": ["unknown"],
        "uses": ["general"],
        "source_type": "zoning_ordinance",
        "metadata": {"breadcrumb": breadcrumb},
    }


# ---------------------------------------------------------------------------
# 1. Closed vocabulary constants
# ---------------------------------------------------------------------------


class TestClosedVocab:
    def test_district_vocab_contents(self):
        assert "residential-low-density" in cd.DISTRICT_VOCAB
        assert "mixed-use-core" in cd.DISTRICT_VOCAB
        assert "commercial-employment" in cd.DISTRICT_VOCAB
        assert "industrial-zone" in cd.DISTRICT_VOCAB
        assert "unknown" in cd.DISTRICT_VOCAB

    def test_uses_vocab_contents(self):
        assert "general" in cd.USES_VOCAB
        assert "food-service" in cd.USES_VOCAB
        assert "food-business" in cd.USES_VOCAB
        assert "home-based-food-business" in cd.USES_VOCAB

    def test_district_vocab_is_closed(self):
        """No extra terms leaked in."""
        assert len(cd.DISTRICT_VOCAB) == 5

    def test_uses_vocab_is_closed(self):
        assert len(cd.USES_VOCAB) == 4


# ---------------------------------------------------------------------------
# 2. group_sections
# ---------------------------------------------------------------------------


class TestGroupSections:
    def test_groups_by_article_and_division(self):
        sources = [
            _make_source("s1", "Sec. R-1", ["Chapter", "ARTICLE III", "RESIDENTIAL"]),
            _make_source("s2", "Sec. R-2", ["Chapter", "ARTICLE III", "RESIDENTIAL"]),
            _make_source("s3", "Sec. B-1", ["Chapter", "ARTICLE III", "COMMERCIAL"]),
        ]
        groups = cd.group_sections(sources)
        keys = {(g.article, g.division) for g in groups}
        assert ("ARTICLE III", "RESIDENTIAL") in keys
        assert ("ARTICLE III", "COMMERCIAL") in keys
        assert len(groups) == 2

    def test_section_count_per_group(self):
        sources = [
            _make_source("s1", "Title A", ["Ch", "ART III", "RES"]),
            _make_source("s2", "Title B", ["Ch", "ART III", "RES"]),
            _make_source("s3", "Title C", ["Ch", "ART III", "RES"]),
        ]
        groups = cd.group_sections(sources)
        assert groups[0].section_count == 3

    def test_sample_titles_capped(self):
        # More than MAX_SAMPLE_TITLES sections in one group.
        sources = [
            _make_source(f"s{i}", f"Title {i}", ["Ch", "ART III", "RES"])
            for i in range(10)
        ]
        groups = cd.group_sections(sources)
        assert len(groups[0].sample_titles) <= cd.MAX_SAMPLE_TITLES

    def test_missing_breadcrumb_uses_empty_article_division(self):
        sources = [
            {
                "source_id": "s1",
                "title": "No breadcrumb",
                "metadata": {},
                "districts": ["unknown"],
                "uses": ["general"],
            }
        ]
        groups = cd.group_sections(sources)
        assert len(groups) == 1
        assert groups[0].article == ""
        assert groups[0].division == ""

    def test_no_division_when_breadcrumb_short(self):
        sources = [
            _make_source("s1", "Title", ["Chapter", "ARTICLE I"])
        ]
        groups = cd.group_sections(sources)
        assert groups[0].article == "ARTICLE I"
        assert groups[0].division == ""

    def test_sorted_output(self):
        sources = [
            _make_source("s1", "T1", ["Ch", "ARTICLE Z", "DIV B"]),
            _make_source("s2", "T2", ["Ch", "ARTICLE A", "DIV B"]),
            _make_source("s3", "T3", ["Ch", "ARTICLE A", "DIV A"]),
        ]
        groups = cd.group_sections(sources)
        articles = [g.article for g in groups]
        # Sorted by article first.
        assert articles == sorted(articles)

    def test_ignores_non_dict_entries(self):
        sources = [
            _make_source("s1", "T1", ["Ch", "ART", "DIV"]),
            "not-a-dict",
            42,
        ]
        groups = cd.group_sections(sources)
        assert len(groups) == 1


# ---------------------------------------------------------------------------
# 3. parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    def test_valid_json_parsed(self):
        raw = json.dumps(
            {
                "districts": ["unknown", "residential-low-density"],
                "uses": ["general"],
                "rationale": "Residential district.",
                "confidence": 0.9,
            }
        )
        result = cd.parse_llm_response(raw)
        assert result["districts"] == ["unknown", "residential-low-density"]
        assert result["uses"] == ["general"]
        assert result["confidence"] == 0.9
        assert result["error"] == ""

    def test_malformed_json_returns_safe_defaults(self):
        result = cd.parse_llm_response("not valid json at all { }")
        assert result["districts"] == cd.DEFAULT_DISTRICTS
        assert result["uses"] == cd.DEFAULT_USES
        assert result["confidence"] == 0.0
        assert "error" in result
        assert result["error"]

    def test_non_object_json_returns_safe_defaults(self):
        result = cd.parse_llm_response(json.dumps(["a", "b"]))
        assert result["districts"] == cd.DEFAULT_DISTRICTS
        assert result["error"]

    def test_markdown_fences_stripped(self):
        raw = "```json\n{\"districts\": [\"unknown\"], \"uses\": [\"general\"], \"rationale\": \"x\", \"confidence\": 0.8}\n```"
        result = cd.parse_llm_response(raw)
        assert result["error"] == ""
        assert result["districts"] == ["unknown"]

    def test_confidence_clamped_to_range(self):
        raw = json.dumps(
            {"districts": ["unknown"], "uses": ["general"], "rationale": "x", "confidence": 99.0}
        )
        result = cd.parse_llm_response(raw)
        assert result["confidence"] == 1.0

    def test_confidence_negative_clamped(self):
        raw = json.dumps(
            {"districts": ["unknown"], "uses": ["general"], "rationale": "x", "confidence": -5.0}
        )
        result = cd.parse_llm_response(raw)
        assert result["confidence"] == 0.0

    def test_missing_confidence_defaults_to_zero(self):
        raw = json.dumps({"districts": ["unknown"], "uses": ["general"], "rationale": "x"})
        result = cd.parse_llm_response(raw)
        assert result["confidence"] == 0.0

    def test_non_list_districts_replaced_with_default(self):
        raw = json.dumps(
            {"districts": "residential-low-density", "uses": ["general"], "rationale": "x", "confidence": 0.8}
        )
        result = cd.parse_llm_response(raw)
        assert result["districts"] == cd.DEFAULT_DISTRICTS

    def test_empty_districts_list_replaced_with_default(self):
        raw = json.dumps(
            {"districts": [], "uses": ["general"], "rationale": "x", "confidence": 0.8}
        )
        result = cd.parse_llm_response(raw)
        assert result["districts"] == cd.DEFAULT_DISTRICTS


# ---------------------------------------------------------------------------
# 4. coerce_vocab
# ---------------------------------------------------------------------------


class TestCoerceVocab:
    def test_valid_vocab_unchanged(self):
        d, u, coerced = cd.coerce_vocab(["unknown", "residential-low-density"], ["general"])
        assert d == ["unknown", "residential-low-density"]
        assert u == ["general"]
        assert not coerced

    def test_off_vocab_district_coerced_to_unknown(self):
        d, u, coerced = cd.coerce_vocab(["invented-district"], ["general"])
        assert d == ["unknown"]
        assert coerced

    def test_off_vocab_use_coerced_to_general(self):
        d, u, coerced = cd.coerce_vocab(["unknown"], ["invented-use"])
        assert u == ["general"]
        assert coerced

    def test_mixed_valid_and_invalid(self):
        d, u, coerced = cd.coerce_vocab(
            ["residential-low-density", "made-up-zone"],
            ["food-service", "also-made-up"],
        )
        # "made-up-zone" → "unknown"; but "residential-low-density" stays.
        # "also-made-up" → "general"; "food-service" stays.
        assert "residential-low-density" in d
        assert "unknown" in d
        assert "food-service" in u
        assert "general" in u
        assert coerced

    def test_deduplication(self):
        # Two off-vocab terms both coerce to "unknown", result deduplicated.
        d, u, coerced = cd.coerce_vocab(["bad-zone-a", "bad-zone-b"], ["general"])
        assert d.count("unknown") == 1
        assert coerced

    def test_empty_lists_get_defaults(self):
        d, u, coerced = cd.coerce_vocab([], [])
        assert d == cd.DEFAULT_DISTRICTS
        assert u == cd.DEFAULT_USES

    def test_all_valid_uses_vocab(self):
        _, u, coerced = cd.coerce_vocab(
            ["unknown"],
            ["food-service", "food-business", "home-based-food-business", "general"],
        )
        assert set(u) == {"food-service", "food-business", "home-based-food-business", "general"}
        assert not coerced


# ---------------------------------------------------------------------------
# 5. classify_group — injectable LLM function
# ---------------------------------------------------------------------------


class TestClassifyGroup:
    def _make_group(
        self,
        article: str = "ARTICLE III. - DISTRICT STANDARDS",
        division: str = "DIVISION 1. - RESIDENTIAL",
        titles: list[str] | None = None,
    ) -> cd.SectionGroup:
        return cd.SectionGroup(
            article=article,
            division=division,
            sample_titles=titles or ["Sec. R-1 Single-family district."],
            section_count=1,
        )

    def test_high_confidence_residential(self):
        response = _load_fixture_response("stub_residential_response.json")
        stub = _make_stub_llm(response)
        group = self._make_group(division="DIVISION 1. - RESIDENTIAL")
        result = cd.classify_group(group, stub)
        assert "residential-low-density" in result.districts
        assert result.confidence >= 0.7
        assert not result.error

    def test_high_confidence_commercial(self):
        response = _load_fixture_response("stub_commercial_response.json")
        stub = _make_stub_llm(response)
        group = self._make_group(division="DIVISION 2. - COMMERCIAL")
        result = cd.classify_group(group, stub)
        assert "commercial-employment" in result.districts
        assert result.confidence >= 0.7

    def test_home_occupation_uses_classification(self):
        response = _load_fixture_response("stub_home_occupation_response.json")
        stub = _make_stub_llm(response)
        group = self._make_group(
            article="ARTICLE IV. - USE STANDARDS",
            division="DIVISION 1. - RESIDENTIAL USES",
        )
        result = cd.classify_group(group, stub)
        assert "home-based-food-business" in result.uses
        assert "unknown" in result.districts  # cross-cutting: unknown districts

    def test_low_confidence_falls_back_to_unknown(self):
        # Confidence below DEFAULT_MIN_CONFIDENCE (0.7).
        low_conf_response = json.dumps(
            {
                "districts": ["residential-low-density"],
                "uses": ["general"],
                "rationale": "Maybe residential?",
                "confidence": 0.5,
            }
        )
        stub = _make_stub_llm(low_conf_response)
        group = self._make_group()
        result = cd.classify_group(group, stub, min_confidence=cd.DEFAULT_MIN_CONFIDENCE)
        # Should fall back to unknown even though LLM gave a specific district.
        assert result.districts == cd.DEFAULT_DISTRICTS
        assert result.uses == cd.DEFAULT_USES
        # But the rationale and actual confidence are preserved for the report.
        assert result.confidence == 0.5
        assert result.rationale

    def test_custom_min_confidence_threshold(self):
        """A confidence of 0.6 passes when min_confidence=0.5."""
        response = json.dumps(
            {
                "districts": ["unknown", "commercial-employment"],
                "uses": ["general"],
                "rationale": "Commercial.",
                "confidence": 0.6,
            }
        )
        stub = _make_stub_llm(response)
        group = self._make_group()
        result = cd.classify_group(group, stub, min_confidence=0.5)
        assert "commercial-employment" in result.districts

    def test_llm_exception_returns_safe_defaults(self):
        def _failing_llm(prompt: str) -> str:
            raise RuntimeError("network timeout")

        group = self._make_group()
        result = cd.classify_group(group, _failing_llm)
        assert result.districts == cd.DEFAULT_DISTRICTS
        assert result.uses == cd.DEFAULT_USES
        assert result.error
        assert "network timeout" in result.error

    def test_malformed_json_returns_safe_defaults(self):
        stub = _make_stub_llm("not json at all")
        group = self._make_group()
        result = cd.classify_group(group, stub)
        assert result.districts == cd.DEFAULT_DISTRICTS
        assert result.error

    def test_off_vocab_terms_coerced(self):
        off_vocab_response = json.dumps(
            {
                "districts": ["invented-zone", "another-fake"],
                "uses": ["fake-use"],
                "rationale": "Unknown territory.",
                "confidence": 0.9,
            }
        )
        stub = _make_stub_llm(off_vocab_response)
        group = self._make_group()
        result = cd.classify_group(group, stub)
        # All off-vocab terms coerced.
        for d in result.districts:
            assert d in cd.DISTRICT_VOCAB
        for u in result.uses:
            assert u in cd.USES_VOCAB
        assert result.coerced

    def test_coercion_still_above_confidence(self):
        """Off-vocab terms get coerced but classification still succeeds if conf ≥ threshold."""
        # One valid district, one invalid — coercion replaces invalid with "unknown".
        response = json.dumps(
            {
                "districts": ["residential-low-density", "nonexistent-zone"],
                "uses": ["general"],
                "rationale": "Mixed.",
                "confidence": 0.85,
            }
        )
        stub = _make_stub_llm(response)
        group = self._make_group()
        result = cd.classify_group(group, stub)
        assert "residential-low-density" in result.districts
        assert "unknown" in result.districts
        assert result.coerced


# ---------------------------------------------------------------------------
# 6. results_to_rules
# ---------------------------------------------------------------------------


class TestResultsToRules:
    def _make_result(
        self,
        article: str = "ARTICLE III",
        division: str = "RESIDENTIAL",
        districts: list[str] | None = None,
        uses: list[str] | None = None,
    ) -> cd.ClassificationResult:
        return cd.ClassificationResult(
            article=article,
            division=division,
            districts=districts or ["unknown", "residential-low-density"],
            uses=uses or ["general"],
            rationale="Residential district.",
            confidence=0.9,
        )

    def test_schema_version_present(self):
        rules = cd.results_to_rules([self._make_result()])
        assert rules["schema_version"] == "source-classification-rules/v1"

    def test_notes_field_present(self):
        rules = cd.results_to_rules([self._make_result()])
        assert "_notes" in rules
        assert rules["_notes"]

    def test_rules_list_present(self):
        rules = cd.results_to_rules([self._make_result()])
        assert isinstance(rules.get("rules"), list)

    def test_rule_has_article_contains(self):
        rules = cd.results_to_rules([self._make_result(article="ARTICLE III")])
        rule = rules["rules"][0]
        assert rule["article_contains"] == "ARTICLE III"

    def test_rule_has_division_contains(self):
        rules = cd.results_to_rules([self._make_result(division="RESIDENTIAL")])
        rule = rules["rules"][0]
        assert rule["division_contains"] == "RESIDENTIAL"

    def test_pure_default_groups_omitted(self):
        """Groups with districts=["unknown"] and uses=["general"] carry no info and are omitted."""
        default_result = cd.ClassificationResult(
            article="ARTICLE I",
            division="",
            districts=["unknown"],
            uses=["general"],
            rationale="general",
            confidence=0.9,
        )
        rules = cd.results_to_rules([default_result])
        assert rules["rules"] == []

    def test_use_specific_group_included_even_with_unknown_districts(self):
        """A group with unknown districts but specific uses IS informative and included."""
        use_result = cd.ClassificationResult(
            article="ARTICLE IV",
            division="RESIDENTIAL USES",
            districts=["unknown"],
            uses=["home-based-food-business", "general"],
            rationale="Home occupation.",
            confidence=0.85,
        )
        rules = cd.results_to_rules([use_result])
        assert len(rules["rules"]) == 1
        assert rules["rules"][0]["uses"] == ["home-based-food-business", "general"]

    def test_notes_mentions_coerced_when_applicable(self):
        result = cd.ClassificationResult(
            article="ART",
            division="DIV",
            districts=["unknown", "residential-low-density"],
            uses=["general"],
            rationale="x",
            confidence=0.9,
            coerced=True,
        )
        rules = cd.results_to_rules([result])
        assert "coerced" in rules["_notes"].lower()

    def test_empty_article_omitted_from_rule(self):
        result = self._make_result(article="")
        rules = cd.results_to_rules([result])
        if rules["rules"]:
            assert "article_contains" not in rules["rules"][0]

    def test_empty_division_omitted_from_rule(self):
        result = self._make_result(division="")
        rules = cd.results_to_rules([result])
        if rules["rules"]:
            assert "division_contains" not in rules["rules"][0]


# ---------------------------------------------------------------------------
# 7. load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_loads_fixture_manifest(self):
        sources = cd.load_manifest(_FIXTURES / "sample_manifest.json")
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert "source_id" in sources[0]

    def test_missing_file_raises_value_error(self, tmp_path):
        missing = tmp_path / "nope.json"
        with pytest.raises(ValueError, match="Cannot read manifest"):
            cd.load_manifest(missing)

    def test_invalid_json_raises_value_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot parse"):
            cd.load_manifest(bad)

    def test_missing_sources_raises_value_error(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps({"schema_version": "source-pack/v1"}), encoding="utf-8")
        with pytest.raises(ValueError, match="missing 'sources'"):
            cd.load_manifest(p)

    def test_non_object_json_raises_value_error(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            cd.load_manifest(p)


# ---------------------------------------------------------------------------
# 8. write_outputs
# ---------------------------------------------------------------------------


class TestWriteOutputs:
    def test_creates_both_files(self, tmp_path):
        rules = {
            "schema_version": "source-classification-rules/v1",
            "_notes": "test",
            "rules": [],
        }
        report = cd.ClassificationReport(manifest_path="test", model="test-model")
        rules_path, report_path = cd.write_outputs(rules, report, tmp_path)
        assert rules_path.exists()
        assert report_path.exists()

    def test_rules_file_is_valid_json(self, tmp_path):
        rules = {
            "schema_version": "source-classification-rules/v1",
            "_notes": "test",
            "rules": [{"article_contains": "ART", "districts": ["unknown"], "uses": ["general"]}],
        }
        report = cd.ClassificationReport()
        rules_path, _ = cd.write_outputs(rules, report, tmp_path)
        loaded = json.loads(rules_path.read_text(encoding="utf-8"))
        assert loaded["schema_version"] == "source-classification-rules/v1"

    def test_report_file_has_note(self, tmp_path):
        rules = {"schema_version": "source-classification-rules/v1", "_notes": "", "rules": []}
        report = cd.ClassificationReport()
        _, report_path = cd.write_outputs(rules, report, tmp_path)
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
        assert "note" in loaded
        assert "REVIEW REQUIRED" in loaded["note"]

    def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        rules = {"schema_version": "source-classification-rules/v1", "_notes": "", "rules": []}
        report = cd.ClassificationReport()
        cd.write_outputs(rules, report, nested)
        assert (nested / "classification_rules.json").exists()


# ---------------------------------------------------------------------------
# 9. Integration: emitted rules → source_classifier.py
# ---------------------------------------------------------------------------


class TestIntegrationWithSourceClassifier:
    """Verify that the rules emitted by results_to_rules() can be loaded and
    applied by the real source_classifier.py loader, and produce the expected
    classifications on a SourceRegistryEntry.

    This test imports app.source_classifier and app.models (pure-ish functions,
    no database or settings interaction).  It never triggers prod settings.
    """

    def test_residential_rule_classifies_matching_entry(self):
        """A residential-division rule correctly maps a matching source entry."""
        # Import pure classifier functions (no prod settings).
        from app.source_classifier import classify_source, load_classification_rules  # noqa: PLC0415
        from app.models import SourceRegistryEntry  # noqa: PLC0415

        # Build a result simulating what the LLM would produce for a residential group.
        result = cd.ClassificationResult(
            article="ARTICLE III. - DISTRICT STANDARDS",
            division="DIVISION 1. - RESIDENTIAL DISTRICTS",
            districts=["unknown", "residential-low-density"],
            uses=["general"],
            rationale="Residential zoning district.",
            confidence=0.92,
        )
        rules_dict = cd.results_to_rules([result])

        # Construct a matching SourceRegistryEntry.
        entry = SourceRegistryEntry(
            source_id="test-sec-1",
            title="Sec. R-1. - Single-family district.",
            excerpt="Regulations for the R-1 single-family residential district.",
            section_ref="Sec. R-1.",
            jurisdiction_id="test-va",
            url="https://example.com",
            effective_date="2024-01-01",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
            metadata={
                "breadcrumb": [
                    "Chapter 42 - ZONING",
                    "ARTICLE III. - DISTRICT STANDARDS",
                    "DIVISION 1. - RESIDENTIAL DISTRICTS",
                ]
            },
        )

        districts, uses = classify_source(entry, rules_dict)
        assert "residential-low-density" in districts
        assert uses == ["general"]

    def test_commercial_rule_classifies_matching_entry(self):
        from app.source_classifier import classify_source  # noqa: PLC0415
        from app.models import SourceRegistryEntry  # noqa: PLC0415

        result = cd.ClassificationResult(
            article="ARTICLE III. - DISTRICT STANDARDS",
            division="DIVISION 2. - COMMERCIAL DISTRICTS",
            districts=["unknown", "commercial-employment"],
            uses=["general"],
            rationale="Commercial district.",
            confidence=0.88,
        )
        rules_dict = cd.results_to_rules([result])

        entry = SourceRegistryEntry(
            source_id="test-sec-2",
            title="Sec. B-1. - Business district.",
            excerpt="Regulations for the B-1 general business district.",
            section_ref="Sec. B-1.",
            jurisdiction_id="test-va",
            url="https://example.com",
            effective_date="2024-01-01",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
            metadata={
                "breadcrumb": [
                    "Chapter 42 - ZONING",
                    "ARTICLE III. - DISTRICT STANDARDS",
                    "DIVISION 2. - COMMERCIAL DISTRICTS",
                ]
            },
        )

        districts, uses = classify_source(entry, rules_dict)
        assert "commercial-employment" in districts

    def test_non_matching_entry_gets_defaults(self):
        from app.source_classifier import classify_source  # noqa: PLC0415
        from app.models import SourceRegistryEntry  # noqa: PLC0415

        result = cd.ClassificationResult(
            article="ARTICLE III. - DISTRICT STANDARDS",
            division="DIVISION 1. - RESIDENTIAL DISTRICTS",
            districts=["unknown", "residential-low-density"],
            uses=["general"],
            rationale="Residential.",
            confidence=0.9,
        )
        rules_dict = cd.results_to_rules([result])

        # This entry is in a completely different article — no rule matches.
        entry = SourceRegistryEntry(
            source_id="test-sec-3",
            title="Sec. 1-1. - Definitions.",
            excerpt="Definitions of terms used throughout the zoning ordinance.",
            section_ref="Sec. 1-1.",
            jurisdiction_id="test-va",
            url="https://example.com",
            effective_date="2024-01-01",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
            metadata={
                "breadcrumb": [
                    "Chapter 42 - ZONING",
                    "ARTICLE I. - IN GENERAL",
                ]
            },
        )

        districts, uses = classify_source(entry, rules_dict)
        # No rule matches → global defaults from source_classifier.
        assert districts == ["unknown"]
        assert uses == ["general"]

    def test_home_occupation_rule_classifies_use(self):
        from app.source_classifier import classify_source  # noqa: PLC0415
        from app.models import SourceRegistryEntry  # noqa: PLC0415

        result = cd.ClassificationResult(
            article="ARTICLE IV. - USE STANDARDS",
            division="DIVISION 1. - RESIDENTIAL USES",
            districts=["unknown"],
            uses=["home-based-food-business", "general"],
            rationale="Home occupation.",
            confidence=0.85,
        )
        rules_dict = cd.results_to_rules([result])

        entry = SourceRegistryEntry(
            source_id="test-sec-4",
            title="Sec. 7-1. - Home Occupation.",
            excerpt="Regulations governing home occupation permits and requirements.",
            section_ref="Sec. 7-1.",
            jurisdiction_id="test-va",
            url="https://example.com",
            effective_date="2024-01-01",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
            metadata={
                "breadcrumb": [
                    "Chapter 42 - ZONING",
                    "ARTICLE IV. - USE STANDARDS",
                    "DIVISION 1. - RESIDENTIAL USES",
                ]
            },
        )

        districts, uses = classify_source(entry, rules_dict)
        assert "home-based-food-business" in uses


# ---------------------------------------------------------------------------
# 10. Integration: run_classification with stubbed LLM
# ---------------------------------------------------------------------------


class TestRunClassification:
    def _residential_stub(self) -> str:
        return json.dumps(
            {
                "districts": ["unknown", "residential-low-density"],
                "uses": ["general"],
                "rationale": "Residential.",
                "confidence": 0.92,
            }
        )

    def _commercial_stub(self) -> str:
        return json.dumps(
            {
                "districts": ["unknown", "commercial-employment"],
                "uses": ["general"],
                "rationale": "Commercial.",
                "confidence": 0.88,
            }
        )

    def _home_occ_stub(self) -> str:
        return json.dumps(
            {
                "districts": ["unknown"],
                "uses": ["home-based-food-business", "general"],
                "rationale": "Home occupation use.",
                "confidence": 0.85,
            }
        )

    def _general_stub(self) -> str:
        return json.dumps(
            {
                "districts": ["unknown"],
                "uses": ["general"],
                "rationale": "General/cross-cutting.",
                "confidence": 0.9,
            }
        )

    def test_full_fixture_manifest(self):
        """run_classification over the sample fixture with a stubbed LLM."""
        manifest_path = _FIXTURES / "sample_manifest.json"

        # The fixture has 4 distinct (article, division) groups.
        # Provide one stub response per group; extras fall back to safe default.
        stub = _make_stub_llm(
            self._general_stub(),      # ARTICLE I - IN GENERAL
            self._residential_stub(),  # ARTICLE III - RESIDENTIAL DISTRICTS
            self._commercial_stub(),   # ARTICLE III - COMMERCIAL DISTRICTS
            self._home_occ_stub(),     # ARTICLE IV - RESIDENTIAL USES
        )

        rules, report = cd.run_classification(
            manifest_path,
            llm_fn=stub,
            model="test-stub-model",
        )

        assert rules["schema_version"] == "source-classification-rules/v1"
        assert isinstance(rules["rules"], list)
        assert report.group_count == 4
        assert report.error_count == 0

    def test_rules_output_classifies_sources(self):
        """The emitted rules correctly classify matching source entries."""
        from app.source_classifier import classify_source  # noqa: PLC0415
        from app.models import SourceRegistryEntry  # noqa: PLC0415

        manifest_path = _FIXTURES / "sample_manifest.json"
        stub = _make_stub_llm(
            self._general_stub(),
            self._residential_stub(),
            self._commercial_stub(),
            self._home_occ_stub(),
        )
        rules, _ = cd.run_classification(manifest_path, llm_fn=stub)

        # A residential section should map to residential-low-density.
        res_entry = SourceRegistryEntry(
            source_id="test-sec-x1",
            title="R-1 District regulations.",
            excerpt="Regulations for the R-1 single-family residential district.",
            section_ref="Sec. R-1.",
            jurisdiction_id="testcity-va",
            url="https://example.com",
            effective_date="2024-01-01",
            districts=["unknown"],
            uses=["general"],
            source_type="zoning_ordinance",
            metadata={
                "breadcrumb": [
                    "Chapter 42 - ZONING",
                    "ARTICLE III. - DISTRICT STANDARDS",
                    "DIVISION 1. - RESIDENTIAL DISTRICTS",
                ]
            },
        )
        districts, _ = classify_source(res_entry, rules)
        assert "residential-low-density" in districts

    def test_all_errors_reported(self, tmp_path):
        """If the LLM always fails, all groups default to unknown and errors counted."""
        manifest_path = _make_manifest(
            tmp_path,
            [
                _make_source("s1", "Title", ["Ch", "ARTICLE III", "RESIDENTIAL"]),
                _make_source("s2", "Title 2", ["Ch", "ARTICLE IV", "COMMERCIAL USES"]),
            ],
        )

        def _always_fails(prompt: str) -> str:
            raise RuntimeError("always fails")

        _, report = cd.run_classification(manifest_path, llm_fn=_always_fails)
        assert report.error_count == 2
        assert report.group_count == 2


# ---------------------------------------------------------------------------
# 11. main() exit codes
# ---------------------------------------------------------------------------


class TestMainExitCodes:
    def test_exit_1_on_missing_manifest(self, tmp_path, monkeypatch):
        missing = tmp_path / "nope.json"
        monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
        # Patch make_groq_llm_fn so it doesn't try to import openai
        monkeypatch.setattr(cd, "make_groq_llm_fn", lambda api_key, model: None)
        rc = cd.main(["--manifest", str(missing)])
        assert rc == 1

    def test_exit_1_on_missing_api_key(self, tmp_path, monkeypatch):
        manifest = _make_manifest(tmp_path, [])
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        rc = cd.main(["--manifest", str(manifest)])
        assert rc == 1

    def test_exit_0_on_success(self, tmp_path, monkeypatch):
        manifest = _make_manifest(
            tmp_path,
            [_make_source("s1", "Title", ["Ch", "ARTICLE I"])],
        )
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")

        def _fake_make_groq_llm_fn(api_key: str, model: str):
            return _make_stub_llm(
                json.dumps(
                    {
                        "districts": ["unknown"],
                        "uses": ["general"],
                        "rationale": "General.",
                        "confidence": 0.9,
                    }
                )
            )

        monkeypatch.setattr(cd, "make_groq_llm_fn", _fake_make_groq_llm_fn)
        output_dir = tmp_path / "output"
        rc = cd.main(["--manifest", str(manifest), "--output-dir", str(output_dir)])
        assert rc == 0
        assert (output_dir / "classification_rules.json").exists()

    def test_exit_1_on_all_llm_errors(self, tmp_path, monkeypatch):
        manifest = _make_manifest(
            tmp_path,
            [_make_source("s1", "Title", ["Ch", "ARTICLE III", "RESIDENTIAL"])],
        )
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")

        def _fake_make_groq_llm_fn(api_key, model):
            def _fail(prompt):
                raise RuntimeError("LLM down")
            return _fail

        monkeypatch.setattr(cd, "make_groq_llm_fn", _fake_make_groq_llm_fn)
        rc = cd.main(["--manifest", str(manifest), "--output-dir", str(tmp_path / "out")])
        assert rc == 1

    def test_dry_run_no_files_written(self, tmp_path, monkeypatch):
        manifest = _make_manifest(
            tmp_path,
            [_make_source("s1", "Title", ["Ch", "ARTICLE I"])],
        )
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        output_dir = tmp_path / "output"

        def _fake_make_groq_llm_fn(api_key, model):
            return _make_stub_llm(
                json.dumps(
                    {"districts": ["unknown"], "uses": ["general"], "rationale": "x", "confidence": 0.9}
                )
            )

        monkeypatch.setattr(cd, "make_groq_llm_fn", _fake_make_groq_llm_fn)
        rc = cd.main(
            ["--manifest", str(manifest), "--output-dir", str(output_dir), "--dry-run"]
        )
        assert rc == 0
        # No files written in dry-run.
        assert not output_dir.exists() or not (output_dir / "classification_rules.json").exists()
