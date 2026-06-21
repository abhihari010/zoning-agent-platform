"""Offline accuracy eval harness for the real ZoningOrchestrator pipeline.

Runs the real pipeline (not the deterministic CI golden harness) against a
per-city labeled dataset and checks five accuracy gates.

Usage:
    # From apps/api/ with venv active:
    python -m tests.eval.runner --jurisdiction franklin-tn

    # Under pytest:
    pytest tests/eval -q
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.models import AnalyzeResult, SourceCitation
from app.orchestrator.zoning_orchestrator import ZoningOrchestrator
from app.tools.citation_tool import CitationTool
from tests.eval.dataset_schema import EvalScenario, ScenarioExpect  # noqa: F401 (re-export)

DATASETS_DIR = Path(__file__).parent / "datasets"
REPORTS_DIR = Path(__file__).parent / "reports"

# Gate thresholds
GATE_DECISION_ACCURACY: float = 0.80
GATE_CITATION_VALIDITY: float = 1.0
GATE_HALLUCINATED_SECTION: float = 0.0
GATE_REQUIRED_CITATION_RECALL: float = 0.80
GATE_ABSTENTION_CORRECTNESS: float = 1.0


class ScenarioOutcome(BaseModel):
    scenario_id: str
    decision_correct: bool
    citations_valid: bool
    has_hallucinated_section: bool
    required_citations_found: list[str] = Field(default_factory=list)
    required_citations_missing: list[str] = Field(default_factory=list)
    abstention_correct: bool
    actual_decision: str
    actual_confidence: float
    actual_citation_count: int
    permit_path_ok: bool = True


class ScorecardResult(BaseModel):
    jurisdiction_id: str
    run_date: str
    scenario_count: int
    decision_accuracy: float
    citation_validity_rate: float
    hallucinated_section_rate: float
    required_citation_recall: float
    abstention_correctness: float
    gates_passed: bool
    gate_failures: list[str] = Field(default_factory=list)
    outcomes: list[ScenarioOutcome] = Field(default_factory=list)


def load_dataset(jurisdiction_id: str, dataset_dir: Path = DATASETS_DIR) -> list[EvalScenario]:
    path = dataset_dir / f"{jurisdiction_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No dataset found for '{jurisdiction_id}' at {path}. "
            "Author a labeled dataset first (see datasets/README.md)."
        )
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(row) for row in raw]


def _is_abstained(result: AnalyzeResult) -> bool:
    return result.feasibility.decision == "unknown" or result.feasibility.confidence < 0.6


def _citations_valid(
    citations: list[SourceCitation],
    jurisdiction_id: str,
    source_store: Any,
) -> bool:
    """True when no citation has an unresolvable source_id."""
    validation = CitationTool(source_store).validate(
        citations=citations,
        jurisdiction_id=jurisdiction_id,
    )
    return not validation.invalid_citation_ids


def _corpus_section_refs(source_store: Any, jurisdiction_id: str) -> set[str]:
    """Every section_ref that can legitimately appear in a citation for this jurisdiction.

    Citations in the hybrid_local path carry the *chunk's* section_ref. For
    markdown-imported sources that section_ref is a heading extracted from inside the
    source body and is NOT present on the parent registry entry (see
    ``ingestion.build_source_chunks``). So the corpus of "real" section_refs must be
    drawn from the chunk store, not just ``list_sources()``; otherwise a perfectly
    legitimate heading-level citation is falsely flagged as hallucinated and the
    =0.0 gate fails. We union sources and chunks so the check is also correct under
    the source_registry retriever, which cites registry entries directly.
    """
    if source_store is None:
        return set()

    def _belongs(obj: Any) -> bool:
        jid = getattr(obj, "jurisdiction_id", None)
        return jid is None or jid == jurisdiction_id

    refs: set[str] = set()
    for src in source_store.list_sources():
        if src.section_ref and _belongs(src):
            refs.add(src.section_ref)

    list_chunks = getattr(source_store, "list_source_chunks", None)
    if callable(list_chunks):
        for chunk in list_chunks():
            if chunk.section_ref and _belongs(chunk):
                refs.add(chunk.section_ref)

    return refs


def _check_permit_path(result: AnalyzeResult, expected_items: list[str]) -> bool:
    if not expected_items:
        return True
    candidates: list[str] = []
    if result.compliance and result.compliance.permit_path:
        candidates.append(result.compliance.permit_path.lower())
    if result.checklist:
        candidates.extend(p.lower() for p in result.checklist.permits)
    return all(any(item.lower() in c for c in candidates) for item in expected_items)


def _evaluate_scenario(
    scenario: EvalScenario,
    result: AnalyzeResult,
    corpus_refs: set[str],
    source_store: Any,
) -> ScenarioOutcome:
    decision_correct = result.feasibility.decision in scenario.expect.decision_in
    valid = _citations_valid(result.citations, scenario.jurisdiction_id, source_store)

    hallucinated = False
    if corpus_refs:
        for c in result.citations:
            if c.section_ref and c.section_ref not in corpus_refs:
                hallucinated = True
                break

    found: list[str] = []
    missing: list[str] = []
    for ref in scenario.expect.must_cite_section_refs:
        if any(c.section_ref == ref for c in result.citations):
            found.append(ref)
        else:
            missing.append(ref)

    if scenario.expect.should_abstain:
        abstention_correct = _is_abstained(result)
    else:
        abstention_correct = True

    permit_ok = _check_permit_path(result, scenario.expect.permit_path_includes)

    return ScenarioOutcome(
        scenario_id=scenario.id,
        decision_correct=decision_correct,
        citations_valid=valid,
        has_hallucinated_section=hallucinated,
        required_citations_found=found,
        required_citations_missing=missing,
        abstention_correct=abstention_correct,
        actual_decision=result.feasibility.decision,
        actual_confidence=round(result.feasibility.confidence, 4),
        actual_citation_count=len(result.citations),
        permit_path_ok=permit_ok,
    )


def run_eval(
    scenarios: list[EvalScenario],
    jurisdiction_id: str,
    *,
    orchestrator: Any = None,
    source_store: Any = None,
    output_dir: Path = REPORTS_DIR,
) -> ScorecardResult:
    """Run the eval harness over a list of labeled scenarios.

    Args:
        scenarios:       Labeled scenarios to evaluate.
        jurisdiction_id: Jurisdiction being evaluated (used in output filename).
        orchestrator:    ZoningOrchestrator instance (or duck-typed mock). When None,
                         creates a default ZoningOrchestrator (requires real services).
        source_store:    Source store used for citation-validity and corpus-section checks.
                         When None, falls back to the retrieval provider's store (if any).
        output_dir:      Directory for the scorecard JSON file.

    Returns:
        ScorecardResult with per-scenario outcomes and aggregate gate results.
    """
    orch: Any = orchestrator
    if orch is None:
        # Lazy import to avoid pulling services at import time in tests that inject an orchestrator.
        import app.services as _svc

        _store = source_store
        if _store is None:
            provider = _svc.get_retrieval_provider()
            _store = getattr(provider, "source_store", None)
        source_store = _store
        orch = ZoningOrchestrator()
    else:
        if source_store is None:
            source_store = None  # explicit: no corpus check

    corpus_refs = _corpus_section_refs(source_store, jurisdiction_id)
    outcomes: list[ScenarioOutcome] = []

    for scenario in scenarios:
        result: AnalyzeResult = orch.analyze_project(
            project_description=scenario.project_description,
            district="unknown",
            district_confidence=0.0,
            district_method="eval",
            jurisdiction_id=scenario.jurisdiction_id,
            normalized_address=scenario.address,
            bypass_support_gate=True,   # eval gate measures pre-promotion cities
        )
        outcomes.append(_evaluate_scenario(scenario, result, corpus_refs, source_store))

    n = len(outcomes)
    if n == 0:
        raise ValueError("No scenarios to evaluate.")

    # Decision accuracy
    decision_accuracy = sum(o.decision_correct for o in outcomes) / n

    # Citation validity (fraction of scenarios with NO invalid citation IDs)
    citation_validity_rate = sum(o.citations_valid for o in outcomes) / n

    # Hallucinated-section rate (fraction of scenarios with ANY hallucination)
    hallucinated_section_rate = sum(o.has_hallucinated_section for o in outcomes) / n

    # Required-citation recall (fraction of required refs that were surfaced)
    total_required = sum(
        len(s.expect.must_cite_section_refs)
        for s in scenarios
        if s.expect.must_cite_section_refs
    )
    total_found = sum(len(o.required_citations_found) for o in outcomes)
    required_citation_recall = total_found / total_required if total_required else 1.0

    # Abstention correctness (only over should_abstain=True scenarios)
    abstain_outcomes = [
        o
        for o, s in zip(outcomes, scenarios)
        if s.expect.should_abstain
    ]
    abstention_correctness = (
        sum(o.abstention_correct for o in abstain_outcomes) / len(abstain_outcomes)
        if abstain_outcomes
        else 1.0
    )

    gate_failures: list[str] = []
    if decision_accuracy < GATE_DECISION_ACCURACY:
        gate_failures.append(
            f"decision_accuracy {decision_accuracy:.3f} < {GATE_DECISION_ACCURACY}"
        )
    if citation_validity_rate < GATE_CITATION_VALIDITY:
        gate_failures.append(
            f"citation_validity_rate {citation_validity_rate:.3f} < {GATE_CITATION_VALIDITY}"
        )
    if hallucinated_section_rate > GATE_HALLUCINATED_SECTION:
        gate_failures.append(
            f"hallucinated_section_rate {hallucinated_section_rate:.3f} > {GATE_HALLUCINATED_SECTION}"
        )
    if required_citation_recall < GATE_REQUIRED_CITATION_RECALL:
        gate_failures.append(
            f"required_citation_recall {required_citation_recall:.3f} < {GATE_REQUIRED_CITATION_RECALL}"
        )
    if abstention_correctness < GATE_ABSTENTION_CORRECTNESS:
        gate_failures.append(
            f"abstention_correctness {abstention_correctness:.3f} < {GATE_ABSTENTION_CORRECTNESS}"
        )

    scorecard = ScorecardResult(
        jurisdiction_id=jurisdiction_id,
        run_date=date.today().isoformat(),
        scenario_count=n,
        decision_accuracy=round(decision_accuracy, 4),
        citation_validity_rate=round(citation_validity_rate, 4),
        hallucinated_section_rate=round(hallucinated_section_rate, 4),
        required_citation_recall=round(required_citation_recall, 4),
        abstention_correctness=round(abstention_correctness, 4),
        gates_passed=not gate_failures,
        gate_failures=gate_failures,
        outcomes=outcomes,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{jurisdiction_id}-{scorecard.run_date}.json"
    out_path.write_text(scorecard.model_dump_json(indent=2), encoding="utf-8")

    return scorecard


def _ensure_console_encoding() -> None:
    """Make stdout resilient to non-encodable glyphs.

    The scorecard summary uses box-drawing/em-dash glyphs. On a Windows console
    (cp1252) printing U+2500 raises UnicodeEncodeError *after* the scorecard JSON
    has already been written, crashing an otherwise-successful run. Switch the
    stream's error handler to ``backslashreplace`` so such glyphs degrade
    gracefully instead of aborting; capable (utf-8) terminals are unaffected.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (ValueError, OSError):  # pragma: no cover - stream may be wrapped
                pass


def _print_summary(scorecard: ScorecardResult) -> None:
    sep = "─" * 60
    print(f"\nEval scorecard: {scorecard.jurisdiction_id}  ({scorecard.run_date})  n={scorecard.scenario_count}")
    print(sep)
    rows = [
        ("Decision accuracy",         scorecard.decision_accuracy,         f">={GATE_DECISION_ACCURACY:.2f}"),
        ("Citation validity",          scorecard.citation_validity_rate,    f"={GATE_CITATION_VALIDITY:.2f}"),
        ("Hallucinated-section rate",  scorecard.hallucinated_section_rate, f"={GATE_HALLUCINATED_SECTION:.2f}"),
        ("Required-citation recall",   scorecard.required_citation_recall,  f">={GATE_REQUIRED_CITATION_RECALL:.2f}"),
        ("Abstention correctness",     scorecard.abstention_correctness,    f"={GATE_ABSTENTION_CORRECTNESS:.2f}"),
    ]
    print(f"{'Metric':<30} {'Value':>6}  {'Gate':>7}  Status")
    print("─" * 58)
    for label, value, gate in rows:
        in_failures = any(label.lower().split()[0] in f for f in scorecard.gate_failures)
        status = "FAIL" if in_failures else "PASS"
        print(f"{label:<30} {value:>6.3f}  {gate:>7}  {status}")
    print(sep)
    if scorecard.gates_passed:
        print("Gates: ALL PASSED\n")
    else:
        print(f"Gates: FAILED — {', '.join(scorecard.gate_failures)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the zoning accuracy eval harness against a labeled city dataset."
    )
    parser.add_argument("--jurisdiction", required=True, help="Jurisdiction ID (e.g. franklin-tn)")
    parser.add_argument(
        "--dataset-dir",
        default=str(DATASETS_DIR),
        help="Directory containing <jurisdiction_id>.json dataset files",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPORTS_DIR),
        help="Directory to write the scorecard JSON",
    )
    args = parser.parse_args(argv)

    _ensure_console_encoding()

    scenarios = load_dataset(args.jurisdiction, dataset_dir=Path(args.dataset_dir))
    print(f"Loaded {len(scenarios)} scenario(s) for '{args.jurisdiction}'.")

    scorecard = run_eval(
        scenarios,
        args.jurisdiction,
        output_dir=Path(args.output_dir),
    )
    _print_summary(scorecard)
    return 0 if scorecard.gates_passed else 1


if __name__ == "__main__":
    sys.exit(main())
