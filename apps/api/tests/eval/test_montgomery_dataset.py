"""Golden-set integrity guard for the Montgomery County VA dimensional eval.

CI-safe: this test does NOT run the real pipeline and makes no provider/network/
prod-DB calls. It locks the semantic content of the labeled dataset so accidental
edits (or a silently weakened golden set) are caught before they can mask a
real-pipeline regression. The dataset itself IS the dimensional gate; the
real-pipeline run is documented in datasets/README.md.

The authoritative golden mapping (district -> ordinance section -> metric):
    A-1  -> Sec. 10-21 (max height 40)
    R-1  -> Sec. 10-24 (lot area 20,000 / front yard 40 / side yard 15 / width 100)
    R-2  -> Sec. 10-25 (lot area 15,000)
    R-3  -> Sec. 10-26 (lot area 10,000 / front 25)
    RM-1 -> Sec. 10-27 (townhouse lot area 2,000, 16 ft width)
    GB   -> Sec. 10-28 (max height 50)
    CB   -> Sec. 10-29 (max height 35)
    M-1  -> Sec. 10-30 (front setback 75, else 35)
"""
from __future__ import annotations

from pathlib import Path

from app.models import (
    AnalyzeResult,
    Checklist,
    Feasibility,
    SourceCitation,
    TrustIndicators,
)
from app.storage import SQLiteStore
from app.models import SourceRegistryEntry
from tests.eval.runner import load_dataset, run_eval

_JURISDICTION = "montgomery-county-va"
_EXPECTED_SCENARIO_COUNT = 12

# Section refs as they actually appear in the dataset's must_cite_section_refs.
# NOTE: the dataset stores bare ordinance numbers ("10-24"), not "Sec. 10-24".
_EXPECTED_SECTION_UNION = {
    "10-21",
    "10-24",
    "10-25",
    "10-26",
    "10-27",
    "10-28",
    "10-29",
    "10-30",
}

# Scenario id -> required section ref(s). Locks the district->section mapping.
_EXPECTED_SCENARIO_SECTIONS = {
    "montgomery-county-va-r1-min-lot-area": ["10-24"],
    "montgomery-county-va-r1-front-setback": ["10-24"],
    "montgomery-county-va-r1-side-setback": ["10-24"],
    "montgomery-county-va-r1-min-lot-width": ["10-24"],
    "montgomery-county-va-r2-min-lot-area": ["10-25"],
    "montgomery-county-va-r3-min-lot-area": ["10-26"],
    "montgomery-county-va-r3-front-setback": ["10-26"],
    "montgomery-county-va-rm1-townhouse-min-lot-area": ["10-27"],
    "montgomery-county-va-a1-max-height": ["10-21"],
    "montgomery-county-va-gb-max-height": ["10-28"],
    "montgomery-county-va-cb-max-height": ["10-29"],
    "montgomery-county-va-m1-min-setback": ["10-30"],
}


# ---------------------------------------------------------------------------
# Dataset integrity
# ---------------------------------------------------------------------------


def test_dataset_parses_and_has_twelve_scenarios() -> None:
    scenarios = load_dataset(_JURISDICTION)
    assert len(scenarios) == _EXPECTED_SCENARIO_COUNT


def test_every_scenario_is_positive_dimensional() -> None:
    """All 12 are positive/dimensional scenarios (not abstention scenarios)."""
    scenarios = load_dataset(_JURISDICTION)
    for s in scenarios:
        assert s.jurisdiction_id == _JURISDICTION, s.id
        assert s.project_description.strip(), f"empty project_description: {s.id}"
        assert s.expect.must_cite_section_refs, f"no required citation: {s.id}"
        assert s.expect.should_abstain is False, f"should not abstain: {s.id}"


def test_scenario_ids_match_golden_mapping() -> None:
    scenarios = load_dataset(_JURISDICTION)
    actual_ids = {s.id for s in scenarios}
    assert actual_ids == set(_EXPECTED_SCENARIO_SECTIONS), actual_ids


def test_each_scenario_cites_expected_section() -> None:
    """Lock district -> ordinance section so a silent weakening is caught."""
    scenarios = load_dataset(_JURISDICTION)
    for s in scenarios:
        expected = _EXPECTED_SCENARIO_SECTIONS[s.id]
        assert s.expect.must_cite_section_refs == expected, (
            f"{s.id}: expected {expected}, got {s.expect.must_cite_section_refs}"
        )


def test_required_section_union_covers_all_eight_sections() -> None:
    scenarios = load_dataset(_JURISDICTION)
    union: set[str] = set()
    for s in scenarios:
        union.update(s.expect.must_cite_section_refs)
    assert union == _EXPECTED_SECTION_UNION, union


# ---------------------------------------------------------------------------
# Gate-compatibility proof (mock orchestrator, no real providers)
# ---------------------------------------------------------------------------

_EMPTY_CHECKLIST = Checklist(steps=[], permits=[], documents=[], departments=[])
_TRUST = TrustIndicators(zoning_district="unknown")


def _result_for(section_ref: str) -> AnalyzeResult:
    citation = SourceCitation(
        source_id=f"mont-{section_ref}",
        title=f"Montgomery County VA Zoning {section_ref}",
        excerpt="Dimensional standard.",
        section_ref=section_ref,
        jurisdiction_id=_JURISDICTION,
        effective_date="2026-01-01",
    )
    return AnalyzeResult(
        status="success",
        trace_id="test-trace",
        feasibility=Feasibility(decision="likely_allowed", confidence=0.88, summary="Test"),
        checklist=_EMPTY_CHECKLIST,
        citations=[citation],
        disclaimers=[],
        follow_up_questions=[],
        warnings=[],
        trust_indicators=_TRUST,
    )


class _MockOrchestrator:
    """Feeds pre-built AnalyzeResult objects in order — no real services needed."""

    def __init__(self, results: list[AnalyzeResult]) -> None:
        self._it = iter(results)

    def analyze_project(self, **_kwargs: object) -> AnalyzeResult:
        return next(self._it)


def test_dataset_is_gate_compatible_with_correct_citations(tmp_path: Path) -> None:
    """Feeding correct dimensional citations for a subset of scenarios passes all gates.

    Proves the dataset is gate-compatible without any real provider: when the
    pipeline returns the required section_ref for each scenario, run_eval reports
    gates_passed.
    """
    scenarios = load_dataset(_JURISDICTION)[:3]

    store = SQLiteStore(tmp_path / "mont.sqlite3")
    mock_results: list[AnalyzeResult] = []
    for s in scenarios:
        ref = s.expect.must_cite_section_refs[0]
        store.upsert_source(
            SourceRegistryEntry(
                source_id=f"mont-{ref}",
                title=f"Montgomery County VA Zoning {ref}",
                excerpt="Dimensional standard.",
                section_ref=ref,
                jurisdiction_id=_JURISDICTION,
                districts=["unknown"],
                uses=["general"],
                effective_date="2026-01-01",
            )
        )
        mock_results.append(_result_for(ref))

    scorecard = run_eval(
        scenarios,
        _JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=store,
        output_dir=tmp_path / "reports",
    )

    assert scorecard.gates_passed, scorecard.gate_failures
    assert scorecard.decision_accuracy == 1.0
    assert scorecard.required_citation_recall == 1.0
    assert scorecard.hallucinated_section_rate == 0.0
    assert scorecard.citation_validity_rate == 1.0
