"""Offline retrieval-regression gate for CI (Stage 5).

Runs the REAL pipeline (ZoningOrchestrator + hybrid_local retrieval) over every
labeled dataset in ``tests/eval/datasets/`` against a throwaway SQLite corpus
built from the committed source packs — no network, no API keys, no cost.
A chunking/ingestion/retrieval regression fails the build.

What this gates (and what it deliberately does not):

- With ``EMBEDDING_PROVIDER=none`` / ``VECTOR_PROVIDER=none``, hybrid_local
  falls back to deterministic SQL keyword retrieval. That path exercises the
  full ingestion surface (pack parsing, chunking, section_ref extraction,
  district/jurisdiction filtering, citation resolution), so the retrieval
  gates below are meaningful and stable in CI.
- ``decision_accuracy`` is NOT gated here: it measures the live analysis LLM
  (Groq in prod), and CI runs ``AI_PROVIDER=deterministic``. The full
  five-gate run against real providers remains the manual pre-promotion step
  (``python -m tests.eval.runner --jurisdiction <id>`` with prod-like env; see
  docs/handoff-pilot-city-eval-gate.md).
- ``required_citation_recall`` is gated against a PER-CITY FLOOR calibrated to
  the offline keyword-retrieval baseline (see ``CI_RECALL_FLOORS``), not the
  0.80 live-pipeline threshold. Keyword retrieval is weaker than the prod
  vector path, so the floor is a regression tripwire, not a quality claim.
  Datasets without an entry get the universal gates only, with recall
  reported but not enforced — add a floor once its offline baseline is known.

Usage (CI sets this env; the guard below refuses anything else):

    APP_ENV=local DATABASE_URL= ZONING_DB_PATH=<temp>.sqlite3 \
    AI_PROVIDER=deterministic RAG_PROVIDER=hybrid_local \
    EMBEDDING_PROVIDER=none VECTOR_PROVIDER=none \
    python -m tests.eval.ci_gate

Exit codes: 0 all gates pass; 1 a gate failed; 2 unsafe/misconfigured env.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Universal retrieval gates (every dataset, every run).
GATE_CITATION_VALIDITY: float = 1.0
GATE_HALLUCINATED_SECTION: float = 0.0
GATE_ABSTENTION_CORRECTNESS: float = 1.0

# Per-city required-citation-recall floors under OFFLINE keyword retrieval.
# Baselines measured 2026-07-03: montgomery-county-va 1.000, franklin-tn 0.692;
# 2026-07-04: richmond-va 0.500 (fine-grained Sec. 30-xxx.y subsection refs are
# hard for keyword retrieval; live vector recall is the quality signal).
# 2026-07-14: chesapeake-va 0.200 (ground-truth refs are the giant SIC use
# tables § 6-2102/§ 7-602/§ 8-602/§ 10-602, which keyword scoring rarely
# surfaces; live vector recall is the quality signal).
CI_RECALL_FLOORS: dict[str, float] = {
    "montgomery-county-va": 0.80,
    "franklin-tn": 0.65,
    "richmond-va": 0.45,
    "chesapeake-va": 0.15,
    # 2026-07-14: loudoun-county-va 0.400 (Chapter 3 use-table refs; same
    # keyword-vs-table caveat as chesapeake).
    "loudoun-county-va": 0.35,
    # 2026-07-14: prince-william-county-va 0.700 (prose per-district
    # "Uses permitted by right" lists — keyword-friendly).
    "prince-william-county-va": 0.60,
    # 2026-07-17: albemarle-county-va 0.900 (prose per-district "By right"
    # lists; only the R-1 home-occupation ref is keyword-hard).
    "albemarle-county-va": 0.80,
    # 2026-07-17: winchester-va 0.700 (prose per-article use regulations;
    # zoning/subdivision packs share bare N-N section numbering, which
    # dilutes keyword scoring for the shortest refs).
    "winchester-va": 0.60,
    # 2026-07-17: virginia-beach-va 1.000 (each article has ONE use chart,
    # so the per-district use vocabulary concentrates in the target section).
    "virginia-beach-va": 0.85,
    # 2026-07-17: newport-news-va 0.455 (the "Summary of uses by district" use
    # table at Sec. 45-402 is shared across 20 districts with no per-district
    # column delimiter in scraped text, so table-derived refs are keyword-hard;
    # the per-district dimensional/general sections are keyword-friendly and
    # carry most of the recall — live vector recall is the quality signal).
    "newport-news-va": 0.35,
    # 2026-07-17: hampton-va 0.200 (most conditional/restricted refs point at
    # Sec. 3-3 "Additional standards on uses", a single very long section
    # covering dozens of unrelated use types — its keyword vocabulary is
    # diluted the same way chesapeake's SIC use tables are; the per-district
    # dimensional sections (Sec. 4-44, 5-16, 6-3, 7-4, ...) are keyword-
    # friendly; live vector recall is the quality signal).
    "hampton-va": 0.15,
    # 2026-07-17: henrico-county-va 0.400 (weak-label pack: only ~35 of 442
    # sources classify to a real district after the rules fix, so most refs
    # point at Article 4 accessory-use sections whose district is "unknown" —
    # they resolve fine by keyword since each section covers one narrow use,
    # but the district-scoped base-district refs are a minority of the
    # dataset; live vector recall is the quality signal).
    "henrico-county-va": 0.35,
    # 2026-07-18: fredericksburg-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own dimensional/purpose section from the "Zoning Districts"
    # article — human-authored title-level rules per district, so the refs
    # are the same short, keyword-dense sections the retriever ranks first).
    "fredericksburg-va": 0.85,
    # 2026-07-18: lynchburg-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own use-standards/development-standards section from the
    # "BASE ZONING DISTRICTS" article — human-authored numeric-prefix rules
    # per district, so the refs are the same short, keyword-dense sections
    # the retriever ranks first).
    "lynchburg-va": 0.85,
}


def _require_offline_env() -> None:
    """Refuse to run unless settings are the safe offline CI configuration.

    This is the guard against the local footgun where a prod-pointing .env
    (real DATABASE_URL / Qdrant / Gemini) leaks into an eval run.
    """
    from app.settings import get_settings

    s = get_settings()
    problems: list[str] = []
    if s.ai_provider != "deterministic":
        problems.append(f"AI_PROVIDER must be 'deterministic' (got {s.ai_provider!r})")
    if s.rag_provider != "hybrid_local":
        problems.append(f"RAG_PROVIDER must be 'hybrid_local' (got {s.rag_provider!r})")
    if s.embedding_provider != "none":
        problems.append(f"EMBEDDING_PROVIDER must be 'none' (got {s.embedding_provider!r})")
    if s.vector_provider != "none":
        problems.append(f"VECTOR_PROVIDER must be 'none' (got {s.vector_provider!r})")
    if s.database_url:
        problems.append("DATABASE_URL must be unset/empty (gate runs on throwaway SQLite only)")
    if problems:
        print("[ci_gate] REFUSING to run — unsafe or misconfigured environment:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(2)


def _bootstrap_corpus() -> None:
    """Load the committed source packs + jurisdictions into the (SQLite) store.

    Mirrors the import phase of scripts/reindex_prod.py, minus embedding.
    """
    from app.ingestion import build_source_chunks, import_source_packs
    from app.jurisdictions import jurisdiction_payloads
    from app.models import JurisdictionRecord
    from app.storage import store

    for payload in jurisdiction_payloads():
        store.upsert_jurisdiction(JurisdictionRecord.model_validate(payload))
    entries = import_source_packs()
    for entry in entries:
        store.upsert_source(entry)
    chunks = build_source_chunks(store.list_sources())
    store.replace_source_chunks(chunks)
    print(f"[ci_gate] corpus bootstrapped: {len(entries)} sources -> {len(chunks)} chunks")


def main() -> int:
    _require_offline_env()
    _bootstrap_corpus()

    from tests.eval.runner import DATASETS_DIR, load_dataset, run_eval

    dataset_paths = sorted(DATASETS_DIR.glob("*.json"))
    if not dataset_paths:
        print("[ci_gate] no datasets found — nothing to gate.")
        return 1

    all_failures: list[str] = []
    for path in dataset_paths:
        jid = path.stem
        scenarios = load_dataset(jid)
        # Scorecards go to a temp dir: the CI gate must not dirty the tree.
        with tempfile.TemporaryDirectory() as tmp:
            card = run_eval(scenarios, jid, output_dir=Path(tmp))

        failures: list[str] = []
        if card.citation_validity_rate < GATE_CITATION_VALIDITY:
            failures.append(
                f"citation_validity {card.citation_validity_rate:.3f} < {GATE_CITATION_VALIDITY}"
            )
        if card.hallucinated_section_rate > GATE_HALLUCINATED_SECTION:
            failures.append(
                f"hallucinated_section_rate {card.hallucinated_section_rate:.3f} > {GATE_HALLUCINATED_SECTION}"
            )
        if card.abstention_correctness < GATE_ABSTENTION_CORRECTNESS:
            failures.append(
                f"abstention_correctness {card.abstention_correctness:.3f} < {GATE_ABSTENTION_CORRECTNESS}"
            )
        floor = CI_RECALL_FLOORS.get(jid)
        recall_note = f"required_citation_recall={card.required_citation_recall:.3f}"
        if floor is None:
            recall_note += " (no CI floor set — reported only)"
        elif card.required_citation_recall < floor:
            failures.append(
                f"required_citation_recall {card.required_citation_recall:.3f} < CI floor {floor}"
            )

        status = "PASS" if not failures else "FAIL"
        print(
            f"[ci_gate] {jid}: {status}  n={card.scenario_count}  "
            f"citation_validity={card.citation_validity_rate:.3f}  "
            f"hallucinated={card.hallucinated_section_rate:.3f}  "
            f"abstention={card.abstention_correctness:.3f}  {recall_note}  "
            f"(decision_accuracy={card.decision_accuracy:.3f} — not gated offline)"
        )
        all_failures.extend(f"{jid}: {f}" for f in failures)

    if all_failures:
        print("[ci_gate] GATE FAILED:")
        for f in all_failures:
            print(f"  - {f}")
        return 1
    print(f"[ci_gate] all retrieval gates passed across {len(dataset_paths)} dataset(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
