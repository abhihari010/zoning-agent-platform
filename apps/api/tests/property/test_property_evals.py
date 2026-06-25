"""City-agnostic property-eval suite (Stage 1.2).

Replaces per-city labeled golden sets for the **breadth tier**. Instead of
asserting the specific correct answer for each city (which requires months of
per-city hand-labeling), this suite asserts safety/grounding *properties* that
must hold for **every** jurisdiction with an indexed corpus — discovered
automatically from the seeded source registry, with zero per-city authoring. A
new ``source_indexed`` city is covered the moment its corpus is seeded; nothing
here needs editing.

Properties (see ``docs/jurisdiction-expansion/expansion-plan.md`` §1.2):

* **Grounding** — every returned citation resolves to a real source/chunk in
  *that city's* corpus (or a statewide ``*`` source); no hallucinated
  ``section_ref``.
* **Scoping** — every citation's ``jurisdiction_id`` is the queried city, its
  parent, or a statewide ``*`` source; never another concrete jurisdiction.
* **Served + caveat** — a servable city returns ``jurisdiction_supported=True``;
  ``source_indexed`` carries a "Preliminary coverage" caveat, ``public_supported``
  does not.
* **Abstention** — when retrieval surfaces no evidence the orchestrator yields
  ``unknown`` / 0 citations and never synthesizes a conclusion. This global
  invariant is what makes a breadth-first ``source_indexed`` launch safe.

These verify the answer is *grounded and safe* (the bar for ``source_indexed``)
without asserting the correct answer. Runs in the deterministic default provider
mode — the same clean no-``.env`` baseline as ``tests/golden``.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import services
from app.ai.source_registry_retriever import _load_seed_source_registry
from app.jurisdictions import get_jurisdiction_scope, load_jurisdictions
from app.models import AnalyzeResult
from app.orchestrator.zoning_orchestrator import ZoningOrchestrator
from app.storage import store
from tests.eval.runner import _normalize_section_ref

# A common small-business change-of-use probe. Every indexed VA corpus tags its
# chunks under food/general uses (or leaves them unclassified, which the use
# filter also admits) and the statewide VDH food-establishment source applies, so
# this single query reaches retrieval for every city without per-city tuning.
PROBE_DESCRIPTION = (
    "Open a small bakery with two employees, posted operating hours, and interior "
    "renovation plans."
)

# A statewide ("*") source legitimately grounds and scopes a citation for any
# in-state jurisdiction; it is never a cross-jurisdiction leak.
WILDCARD_JURISDICTION = "*"


def _corpus_jurisdiction_ids() -> list[str]:
    """Concrete jurisdictions with at least one seeded source (excludes ``*``)."""
    ids = {
        entry.get("jurisdiction_id")
        for entry in _load_seed_source_registry()
        if entry.get("jurisdiction_id")
        and entry.get("jurisdiction_id") != WILDCARD_JURISDICTION
    }
    return sorted(ids)


CORPUS_JURISDICTIONS = _corpus_jurisdiction_ids()
_JURISDICTION_BY_ID = {j.jurisdiction_id: j for j in load_jurisdictions()}

pytestmark = pytest.mark.skipif(
    not CORPUS_JURISDICTIONS,
    reason="No jurisdictions with a seeded corpus in the source registry.",
)


def _allowed_citation_jurisdictions(jurisdiction_id: str) -> set[str | None]:
    """Jurisdiction ids a citation for ``jurisdiction_id`` may legitimately carry."""
    allowed: set[str | None] = {jurisdiction_id, WILDCARD_JURISDICTION, None}
    scope = get_jurisdiction_scope(jurisdiction_id)
    if scope and scope.parent_jurisdiction_id:
        allowed.add(scope.parent_jurisdiction_id)
    return allowed


def _corpus_section_refs(jurisdiction_id: str) -> set[str]:
    """Every ``section_ref`` that may legitimately appear in a citation for this city.

    Unions sources and chunks (markdown-imported headings live only on chunks,
    not the parent registry entry) and includes statewide ``*`` sources, matching
    the orchestrator's retrieval scope.
    """
    scope = {None, jurisdiction_id, WILDCARD_JURISDICTION}
    refs: set[str] = set()
    for src in store.list_sources():
        if src.section_ref and src.jurisdiction_id in scope:
            refs.add(_normalize_section_ref(src.section_ref))
    for chunk in store.list_source_chunks():
        if chunk.section_ref and chunk.jurisdiction_id in scope:
            refs.add(_normalize_section_ref(chunk.section_ref))
    refs.discard("")
    return refs


@dataclass(frozen=True)
class _CityProbe:
    jurisdiction_id: str
    coverage_status: str
    result: AnalyzeResult
    corpus_section_refs: set[str]
    corpus_source_ids: set[str]


@pytest.fixture(scope="module")
def city_probes() -> dict[str, _CityProbe]:
    """Run the probe once per corpus jurisdiction and capture grounding context.

    Resets and re-seeds the store for each city (auto-seed populates the full
    registry), so the run is independent of any prior test's store state.
    """
    probes: dict[str, _CityProbe] = {}
    for jid in CORPUS_JURISDICTIONS:
        store.reset()
        jurisdiction = _JURISDICTION_BY_ID.get(jid)
        result = services.analyze_project(
            project_description=PROBE_DESCRIPTION,
            district="unknown",
            jurisdiction_id=jid,
            jurisdiction_name=jurisdiction.name if jurisdiction else jid,
            normalized_address=None,
            project_id=f"property-{jid}",
        )
        probes[jid] = _CityProbe(
            jurisdiction_id=jid,
            coverage_status=jurisdiction.coverage_status if jurisdiction else "unknown",
            result=result,
            corpus_section_refs=_corpus_section_refs(jid),
            corpus_source_ids={src.source_id for src in store.list_sources()},
        )
    return probes


@pytest.mark.parametrize("jid", CORPUS_JURISDICTIONS)
def test_probe_citations_are_grounded(city_probes: dict[str, _CityProbe], jid: str) -> None:
    """Every returned citation resolves to a real source/chunk in this city's corpus."""
    probe = city_probes[jid]
    citations = probe.result.citations
    assert citations, f"{jid}: probe returned no citations — corpus is not reachable."
    for citation in citations:
        assert citation.source_id in probe.corpus_source_ids, (
            f"{jid}: citation source_id {citation.source_id!r} is not a real "
            "registry source (hallucinated grounding)."
        )
        if citation.section_ref:
            assert (
                _normalize_section_ref(citation.section_ref) in probe.corpus_section_refs
            ), f"{jid}: citation section_ref {citation.section_ref!r} is not in the corpus."


@pytest.mark.parametrize("jid", CORPUS_JURISDICTIONS)
def test_probe_citations_are_scoped(city_probes: dict[str, _CityProbe], jid: str) -> None:
    """Citations never leak from another concrete jurisdiction."""
    probe = city_probes[jid]
    allowed = _allowed_citation_jurisdictions(jid)
    leaked = {citation.jurisdiction_id for citation in probe.result.citations} - allowed
    assert not leaked, f"{jid}: citations leaked from other jurisdictions: {sorted(leaked)}"
    # The orchestrator's own citation validation must concur — no invalid or
    # cross-jurisdiction source ids when citations are present.
    if probe.result.citations:
        validation = probe.result.citation_validation
        assert validation is not None
        assert not validation.invalid_citation_ids, (
            f"{jid}: citation validation flagged invalid ids: {validation.invalid_citation_ids}"
        )


@pytest.mark.parametrize("jid", CORPUS_JURISDICTIONS)
def test_servable_city_served_with_correct_caveat(
    city_probes: dict[str, _CityProbe], jid: str
) -> None:
    """A servable city reports supported=True; only ``source_indexed`` carries a caveat."""
    probe = city_probes[jid]
    indicators = probe.result.trust_indicators
    assert indicators is not None
    assert indicators.jurisdiction_supported is True, (
        f"{jid}: a servable jurisdiction must report jurisdiction_supported=True."
    )
    has_caveat = any("Preliminary coverage" in warning for warning in probe.result.warnings)
    if probe.coverage_status == "source_indexed":
        assert has_caveat, (
            f"{jid}: source_indexed must carry a 'Preliminary coverage' caveat; "
            f"warnings={probe.result.warnings}"
        )
    elif probe.coverage_status == "public_supported":
        assert not has_caveat, (
            f"{jid}: public_supported must not carry a coverage caveat; "
            f"warnings={probe.result.warnings}"
        )


@pytest.mark.parametrize("jid", CORPUS_JURISDICTIONS)
def test_abstention_invariant_never_synthesizes(
    city_probes: dict[str, _CityProbe], jid: str
) -> None:
    """If the probe ever surfaces zero citations, the result must abstain."""
    probe = city_probes[jid]
    if not probe.result.citations:
        assert probe.result.feasibility.decision == "unknown"
        assert probe.result.feasibility.confidence < 0.6


def test_jurisdiction_with_no_corpus_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    """A servable city whose corpus is empty must abstain — never synthesize.

    Disables auto-seed and clears the store so retrieval has nothing to return,
    then drives a real servable city through the full pipeline. The orchestrator
    must yield ``unknown`` / 0 citations and surface the no-evidence warning — the
    safety net that makes a breadth-first ``source_indexed`` launch safe.
    """
    monkeypatch.setenv("AUTO_SEED_SOURCES", "false")
    store.reset()

    result = ZoningOrchestrator().analyze_project(
        project_description=PROBE_DESCRIPTION,
        district="unknown",
        jurisdiction_id="christiansburg-va",
        jurisdiction_name="Christiansburg, VA",
    )

    assert result.citations == []
    assert result.feasibility.decision == "unknown"
    assert result.feasibility.confidence < 0.6
    assert any("No relevant ordinances" in warning for warning in result.warnings), (
        f"Expected a no-evidence warning; got: {result.warnings}"
    )
