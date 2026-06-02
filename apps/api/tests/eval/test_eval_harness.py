"""Self-tests for the eval harness using a synthetic fixture city.

Uses a mocked orchestrator (no real providers, no API keys, no network).
Covers all five metric calculations and verifies that gate failures cause
a non-zero exit code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import (
    AnalyzeResult,
    Checklist,
    ComplianceResult,
    Feasibility,
    PipelineMetadata,
    SourceCitation,
    TrustIndicators,
)
from app.models import SourceChunk, SourceRegistryEntry
from app.storage import SQLiteStore
from tests.eval.dataset_schema import EvalScenario, ScenarioExpect
from tests.eval.runner import (
    GATE_ABSTENTION_CORRECTNESS,
    GATE_CITATION_VALIDITY,
    GATE_DECISION_ACCURACY,
    GATE_HALLUCINATED_SECTION,
    GATE_REQUIRED_CITATION_RECALL,
    ScorecardResult,
    load_dataset,
    main,
    run_eval,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_CHECKLIST = Checklist(steps=[], permits=[], documents=[], departments=[])
_TRUST = TrustIndicators(zoning_district="unknown")


def _make_result(
    decision: str,
    confidence: float,
    citations: list[SourceCitation] | None = None,
    status: str = "success",
) -> AnalyzeResult:
    return AnalyzeResult(
        status=status,
        trace_id="test-trace",
        feasibility=Feasibility(decision=decision, confidence=confidence, summary="Test"),
        checklist=_EMPTY_CHECKLIST,
        citations=citations or [],
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


# ---------------------------------------------------------------------------
# Fixture: synthetic "synthville" city with 2 scenarios
# ---------------------------------------------------------------------------

_SYNTHVILLE_JURISDICTION = "synthville"

_SYNTHVILLE_SOURCE = SourceRegistryEntry(
    source_id="syn-ordinance-bakery",
    title="Bakery Use Standard",
    excerpt="Bakeries are permitted in commercial zones with a site plan review.",
    section_ref="Sec. 1.1",
    jurisdiction_id=_SYNTHVILLE_JURISDICTION,
    districts=["unknown"],
    uses=["general"],
    effective_date="2026-01-01",
)

_SYNTHVILLE_SCENARIOS = [
    EvalScenario(
        id="synthville-bakery-allowed",
        address="123 Main St, Synthville, SY 00001",
        project_description="Open a small retail bakery in a commercial storefront.",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        expect=ScenarioExpect(
            decision_in=["likely_allowed", "conditional"],
            must_cite_section_refs=["Sec. 1.1"],
            should_abstain=False,
        ),
    ),
    EvalScenario(
        id="synthville-abstain-ambiguous",
        address="456 Oak Ave, Synthville, SY 00001",
        project_description="Operate a nuclear waste storage facility.",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        expect=ScenarioExpect(
            decision_in=["unknown"],
            should_abstain=True,
        ),
    ),
]


def _synthville_citation() -> SourceCitation:
    return SourceCitation(
        source_id="syn-ordinance-bakery",
        title="Bakery Use Standard",
        excerpt="Bakeries are permitted in commercial zones.",
        section_ref="Sec. 1.1",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        effective_date="2026-01-01",
    )


def _synthville_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "synth.sqlite3")
    store.upsert_source(_SYNTHVILLE_SOURCE)
    return store


# ---------------------------------------------------------------------------
# Tests: all gates pass
# ---------------------------------------------------------------------------


def test_all_gates_pass(tmp_path: Path) -> None:
    """Harness reports pass when both scenarios satisfy every metric."""
    mock_results = [
        _make_result("likely_allowed", 0.88, citations=[_synthville_citation()]),
        _make_result("unknown", 0.30, status="low_confidence"),
    ]
    scorecard = run_eval(
        _SYNTHVILLE_SCENARIOS,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=_synthville_store(tmp_path),
        output_dir=tmp_path / "reports",
    )

    assert scorecard.gates_passed, scorecard.gate_failures
    assert scorecard.gate_failures == []
    assert scorecard.decision_accuracy == 1.0
    assert scorecard.citation_validity_rate == 1.0
    assert scorecard.hallucinated_section_rate == 0.0
    assert scorecard.required_citation_recall == 1.0
    assert scorecard.abstention_correctness == 1.0
    assert scorecard.scenario_count == 2

    # Scorecard JSON should have been written
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert data["jurisdiction_id"] == _SYNTHVILLE_JURISDICTION
    assert data["gates_passed"] is True


# ---------------------------------------------------------------------------
# Tests: individual metric calculations
# ---------------------------------------------------------------------------


def test_decision_accuracy_metric(tmp_path: Path) -> None:
    """Scenario with wrong decision → decision_accuracy < 1.0."""
    scenarios = [_SYNTHVILLE_SCENARIOS[0]]
    mock_results = [_make_result("restricted", 0.7)]  # not in decision_in
    scorecard = run_eval(
        scenarios,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=_synthville_store(tmp_path),
        output_dir=tmp_path / "reports",
    )
    assert scorecard.decision_accuracy == 0.0
    assert not scorecard.gates_passed
    assert any("decision_accuracy" in f for f in scorecard.gate_failures)


def test_citation_validity_metric(tmp_path: Path) -> None:
    """Citation with an ID not in the source store → citation_validity_rate < 1.0."""
    bad_citation = SourceCitation(
        source_id="ghost-id-does-not-exist",
        title="Ghost",
        excerpt="Ghost excerpt.",
        section_ref="Sec. 99",
        effective_date="2026-01-01",
    )
    scenarios = [_SYNTHVILLE_SCENARIOS[0]]
    mock_results = [_make_result("likely_allowed", 0.8, citations=[bad_citation])]
    scorecard = run_eval(
        scenarios,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=_synthville_store(tmp_path),
        output_dir=tmp_path / "reports",
    )
    assert scorecard.citation_validity_rate < 1.0
    assert not scorecard.gates_passed
    assert any("citation_validity" in f for f in scorecard.gate_failures)


def test_hallucinated_section_metric(tmp_path: Path) -> None:
    """Citation with a section_ref not in the corpus → hallucinated_section_rate > 0."""
    hallucinated_citation = SourceCitation(
        source_id="syn-ordinance-bakery",
        title="Bakery Use Standard",
        excerpt="Some text.",
        section_ref="Sec. 999.FAKE",  # not in corpus
        effective_date="2026-01-01",
    )
    scenarios = [_SYNTHVILLE_SCENARIOS[0]]
    mock_results = [_make_result("likely_allowed", 0.8, citations=[hallucinated_citation])]
    scorecard = run_eval(
        scenarios,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=_synthville_store(tmp_path),
        output_dir=tmp_path / "reports",
    )
    assert scorecard.hallucinated_section_rate > 0.0
    assert not scorecard.gates_passed
    assert any("hallucinated" in f for f in scorecard.gate_failures)


def test_chunk_section_ref_not_flagged_hallucinated(tmp_path: Path) -> None:
    """A citation carrying a chunk-level heading section_ref (absent from the parent
    registry entry) must NOT be flagged as hallucinated.

    Regression guard: ingestion.build_source_chunks assigns markdown headings as the
    chunk section_ref, so legitimate citations routinely reference a section_ref that
    only exists on a chunk, not on any list_sources() entry. The corpus check must
    include chunk section_refs, otherwise the =0.0 hallucination gate falsely fails
    every markdown-imported city.
    """
    heading_ref = "Sec. 14-201. Permitted Uses"  # a chunk heading, not on the source entry

    store = SQLiteStore(tmp_path / "synth.sqlite3")
    store.upsert_source(_SYNTHVILLE_SOURCE)  # registry entry has section_ref "Sec. 1.1"
    store.replace_source_chunks(
        [
            SourceChunk(
                chunk_id="syn-ordinance-bakery:chunk:0:abc123abc123:deadbeef",
                source_id="syn-ordinance-bakery",
                title="Bakery Use Standard",
                chunk_text="Bakeries are permitted in commercial zones with a site plan review.",
                chunk_index=0,
                source_text_hash="0" * 64,
                section_ref=heading_ref,
                jurisdiction_id=_SYNTHVILLE_JURISDICTION,
                effective_date="2026-01-01",
            )
        ]
    )

    citation = SourceCitation(
        source_id="syn-ordinance-bakery",
        title="Bakery Use Standard",
        excerpt="Bakeries are permitted in commercial zones.",
        section_ref=heading_ref,
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        effective_date="2026-01-01",
    )
    scenario = EvalScenario(
        id="synthville-heading-citation",
        address="123 Main St, Synthville, SY 00001",
        project_description="Open a small retail bakery in a commercial storefront.",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        expect=ScenarioExpect(decision_in=["likely_allowed"], should_abstain=False),
    )
    mock_results = [_make_result("likely_allowed", 0.85, citations=[citation])]
    scorecard = run_eval(
        [scenario],
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=store,
        output_dir=tmp_path / "reports",
    )
    assert scorecard.hallucinated_section_rate == 0.0, scorecard.outcomes
    assert scorecard.gates_passed, scorecard.gate_failures


def test_required_citation_recall_metric(tmp_path: Path) -> None:
    """Required section_ref not in returned citations → required_citation_recall < 1.0."""
    scenarios = [_SYNTHVILLE_SCENARIOS[0]]  # must_cite_section_refs=["Sec. 1.1"]
    mock_results = [_make_result("likely_allowed", 0.8, citations=[])]  # no citations
    scorecard = run_eval(
        scenarios,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=_synthville_store(tmp_path),
        output_dir=tmp_path / "reports",
    )
    assert scorecard.required_citation_recall == 0.0
    assert not scorecard.gates_passed
    assert any("required_citation_recall" in f for f in scorecard.gate_failures)


def test_abstention_correctness_metric(tmp_path: Path) -> None:
    """should_abstain=True but pipeline returns fabricated high-conf decision → gate fails."""
    scenarios = [_SYNTHVILLE_SCENARIOS[1]]  # should_abstain=True
    mock_results = [_make_result("likely_allowed", 0.92)]  # fabricated conclusion
    scorecard = run_eval(
        scenarios,
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=None,
        output_dir=tmp_path / "reports",
    )
    assert scorecard.abstention_correctness == 0.0
    assert not scorecard.gates_passed
    assert any("abstention_correctness" in f for f in scorecard.gate_failures)


# ---------------------------------------------------------------------------
# Test: intentional gate failure → non-zero exit code
# ---------------------------------------------------------------------------


def test_gate_failure_causes_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When any gate fails, main() must return a non-zero exit code.

    This test patches ZoningOrchestrator inside the runner module so the CLI
    path (main()) is exercised with a mocked orchestrator — no real services needed.
    """
    failing_scenario = EvalScenario(
        id="synthville-abstain-fail",
        address="789 Fail St, Synthville, SY 00001",
        project_description="A project that should trigger abstention but won't.",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        expect=ScenarioExpect(
            decision_in=["unknown"],
            should_abstain=True,
        ),
    )
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    (dataset_dir / f"{_SYNTHVILLE_JURISDICTION}.json").write_text(
        json.dumps([failing_scenario.model_dump()]),
        encoding="utf-8",
    )

    # Patch ZoningOrchestrator in the runner module so main() gets our mock.
    import tests.eval.runner as _runner

    monkeypatch.setattr(
        _runner,
        "ZoningOrchestrator",
        lambda: _MockOrchestrator([_make_result("likely_allowed", 0.95)]),
    )

    exit_code = main(
        [
            "--jurisdiction", _SYNTHVILLE_JURISDICTION,
            "--dataset-dir", str(dataset_dir),
            "--output-dir", str(tmp_path / "reports"),
        ]
    )
    assert exit_code == 1, "main() must return 1 when any gate fails"

    # Scorecard file should still be written even on failure
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert data["gates_passed"] is False


# ---------------------------------------------------------------------------
# Test: load_dataset raises on missing file
# ---------------------------------------------------------------------------


def test_load_dataset_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset("nonexistent-jurisdiction", dataset_dir=tmp_path)


# ---------------------------------------------------------------------------
# Test: abstention passes when result is low-confidence (confidence < 0.6)
# ---------------------------------------------------------------------------


def test_abstention_passes_on_low_confidence(tmp_path: Path) -> None:
    # decision_in includes "conditional" so decision_accuracy doesn't interfere;
    # the point of this test is that confidence < 0.6 satisfies should_abstain=True.
    scenario = EvalScenario(
        id="synthville-abstain-low-conf",
        address="999 Low Conf Ave, Synthville, SY 00001",
        project_description="Borderline project with insufficient evidence.",
        jurisdiction_id=_SYNTHVILLE_JURISDICTION,
        expect=ScenarioExpect(
            decision_in=["conditional", "unknown"],
            should_abstain=True,
        ),
    )
    mock_results = [_make_result("conditional", 0.4)]  # low confidence → abstained correctly
    scorecard = run_eval(
        [scenario],
        _SYNTHVILLE_JURISDICTION,
        orchestrator=_MockOrchestrator(mock_results),
        source_store=None,
        output_dir=tmp_path / "reports",
    )
    assert scorecard.abstention_correctness == 1.0
    assert scorecard.gates_passed
