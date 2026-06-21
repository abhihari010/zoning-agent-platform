"""Tests for dimensional-question hardening in hybrid_local_retriever.

Pure function / regex tests — no Groq, Qdrant, or Postgres. SourceChunk
fixtures use realistic ordinance text but do not depend on any city corpus.
"""
from __future__ import annotations

import pytest

from app.ai.hybrid_local_retriever import (
    _DIMENSIONAL_INTENT_PATTERN,
    _DIMENSIONAL_METRIC_PATTERN,
    _DIMENSIONAL_VALUE_PATTERN,
    _diversify_ranked,
    _ensure_dimensional_rows,
)
from app.ai.interfaces import RetrievalProviderRequest
from app.models import SourceChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _chunk(chunk_id: str, text: str, section_ref: str = "Sec. 10-24") -> SourceChunk:
    return SourceChunk(
        chunk_id=chunk_id,
        source_id="r1-district-ordinance",
        title="Sec. 10-24 - R-1 Residential District",
        chunk_text=text,
        chunk_index=0,
        source_text_hash="0" * 64,
        section_ref=section_ref,
        jurisdiction_id="testville",
    )


def _request(query: str) -> RetrievalProviderRequest:
    # ``query`` is a derived property; drive it through project_description so the
    # full natural-language phrasing reaches _DIMENSIONAL_INTENT_PATTERN.
    return RetrievalProviderRequest(
        district="",
        inferred_use="",
        project_description=query,
        jurisdiction_id="testville",
    )


# ---------------------------------------------------------------------------
# Intent pattern truth table (the GATE)
# ---------------------------------------------------------------------------

_USE_QUERIES_MUST_NOT_FIRE = [
    "retail store",
    "single-family home",
    "home occupation",
    "daycare",
    "backyard shed",
    "graveyard business",
    "can I open a restaurant",
    "is multifamily allowed",
]

_DIMENSIONAL_QUERIES_MUST_FIRE = [
    # ordinance vocabulary
    "what is the minimum lot area in R-1",
    "front yard setback requirement",
    "maximum building height",
    "lot width",
    "floor area ratio",
    "what is the F.A.R. here",
    # plain-English phrasings (broadened coverage)
    "how tall can I build in A-1",
    "how big can my lot be",
    "how wide can the building be",
    "how large a structure is allowed",
    "how small can the lot be",
    "how many stories are permitted",
    "how far back must the house sit",
    "size of the lot",
    "lot size",
    "smallest lot allowed",
    "largest permitted lot",
    "minimum size",
    "maximum lot dimensions",
    "how many stories tall",
]


@pytest.mark.parametrize("query", _USE_QUERIES_MUST_NOT_FIRE)
def test_intent_pattern_does_not_fire_on_use_queries(query: str) -> None:
    assert _DIMENSIONAL_INTENT_PATTERN.search(query) is None, query


@pytest.mark.parametrize("query", _DIMENSIONAL_QUERIES_MUST_FIRE)
def test_intent_pattern_fires_on_dimensional_queries(query: str) -> None:
    assert _DIMENSIONAL_INTENT_PATTERN.search(query) is not None, query


@pytest.mark.parametrize(
    "query",
    ["how far is the store", "far away from here", "a far better option", "this is far better"],
)
def test_far_english_word_does_not_trigger_intent(query: str) -> None:
    """The English word 'far' must not match the Floor-Area-Ratio acronym."""
    assert _DIMENSIONAL_INTENT_PATTERN.search(query) is None, query


def test_far_acronym_and_term_do_trigger_intent() -> None:
    assert _DIMENSIONAL_INTENT_PATTERN.search("the FAR is 0.5") is not None
    assert _DIMENSIONAL_INTENT_PATTERN.search("what is the F.A.R.") is not None
    assert _DIMENSIONAL_INTENT_PATTERN.search("floor area ratio limit") is not None


def test_metric_pattern_excludes_plain_english_phrasings() -> None:
    """target_phrases come from the metric pattern; plain-English forms yield none
    so they fall through to the pass-2 fallback rather than mis-targeting pass-1."""
    assert {m.group(0).lower() for m in _DIMENSIONAL_METRIC_PATTERN.finditer("how tall can I build")} == set()
    assert {m.group(0).lower() for m in _DIMENSIONAL_METRIC_PATTERN.finditer("minimum lot area")} == {"lot area"}


# ---------------------------------------------------------------------------
# Value pattern: accepts measurements, rejects junk numbers
# ---------------------------------------------------------------------------

_VALUE_ACCEPT = [
    "20,000 square feet",
    "Twenty thousand (20,000) square feet",
    "40 feet",
    "2,000 sq. ft.",
    "15 acres",
]
_VALUE_REJECT = [
    "10-24",  # section reference
    "Section 10-25",
    "30 days",
    "$250",
    "revised October 2021",
    "effective 2021-01-01",
]


@pytest.mark.parametrize("text", _VALUE_ACCEPT)
def test_value_pattern_accepts_measurements(text: str) -> None:
    assert _DIMENSIONAL_VALUE_PATTERN.search(text) is not None, text


@pytest.mark.parametrize("text", _VALUE_REJECT)
def test_value_pattern_rejects_junk_numbers(text: str) -> None:
    assert _DIMENSIONAL_VALUE_PATTERN.search(text) is None, text


# ---------------------------------------------------------------------------
# _ensure_dimensional_rows
# ---------------------------------------------------------------------------


def test_use_query_returns_top_unchanged() -> None:
    """A use-permissibility query must not perturb the result list at all."""
    a = _chunk("c-a", "Retail stores are a permitted principal use.")
    b = _chunk("c-b", "Minimum lot area shall be 20,000 square feet.")
    ranked = [(0.9, a), (0.8, b)]
    top = [(0.9, a)]
    out = _ensure_dimensional_rows(top, ranked, _request("is a retail store allowed"))
    assert out is top  # same object, untouched


def test_dimensional_query_appends_evicted_number_chunk() -> None:
    """The number-bearing chunk the diversify cap dropped is recovered."""
    # Three siblings share one section_ref; the diversify cap (max 2/section)
    # keeps the two highest and evicts the lot-area sentence.
    narrative_a = _chunk("c-narr-a", "The R-1 district is established to provide for low-density housing.")
    narrative_b = _chunk("c-narr-b", "Accessory structures in the R-1 district shall comply with this article.")
    lot_area = _chunk("c-lotarea", "Minimum lot area. The minimum lot area shall be 20,000 square feet.")
    ranked = [(0.9, narrative_a), (0.85, narrative_b), (0.6, lot_area)]
    top = _diversify_ranked(ranked, top_n=8, max_per_section=2)
    assert lot_area.chunk_id not in {c.chunk_id for _, c in top}  # evicted by the cap

    out = _ensure_dimensional_rows(top, ranked, _request("what is the minimum lot area in R-1"))
    assert lot_area.chunk_id in {c.chunk_id for _, c in out}


def test_two_pass_targeting_recovers_the_specific_metric_chunk() -> None:
    """A 'lot area' question recovers the lot-area chunk, not an adjacent
    width/height chunk that ranks higher."""
    # Sibling number-bearing chunks; the width chunk ranks above the lot-area one.
    width = _chunk("c-width", "Minimum lot width shall be 100 feet at the building line.")
    height = _chunk("c-height", "Maximum building height shall be 40 feet.")
    lot_area = _chunk("c-lotarea", "Minimum lot area shall be 20,000 square feet.")
    # top already holds two non-number narrative chunks for a different section so
    # the diversify slots are spent; reserve must pull the targeted metric.
    narr = _chunk("c-narr", "District purpose statement.", section_ref="Sec. 10-00")
    top = [(0.95, narr)]
    ranked = [(0.9, width), (0.85, height), (0.6, lot_area), (0.95, narr)]

    out = _ensure_dimensional_rows(top, ranked, _request("what is the minimum lot area"), reserve=1)
    recovered = {c.chunk_id for _, c in out} - {narr.chunk_id}
    assert recovered == {lot_area.chunk_id}, recovered


def test_reserve_is_capped() -> None:
    """No more than `reserve` number-bearing chunks are appended."""
    narr = _chunk("c-narr", "District purpose statement.", section_ref="Sec. 10-00")
    n1 = _chunk("c-n1", "Minimum lot area shall be 20,000 square feet.")
    n2 = _chunk("c-n2", "Minimum lot width shall be 100 feet.")
    n3 = _chunk("c-n3", "Maximum height shall be 40 feet.")
    top = [(0.95, narr)]
    ranked = [(0.95, narr), (0.9, n1), (0.85, n2), (0.8, n3)]
    out = _ensure_dimensional_rows(top, ranked, _request("lot dimensional requirements"), reserve=2)
    added = len(out) - len(top)
    assert added == 2


def test_no_number_bearing_chunk_means_no_addition() -> None:
    """If nothing in `ranked` carries a measurement, the list is unchanged."""
    a = _chunk("c-a", "The R-1 district is established for low-density residential purposes.")
    b = _chunk("c-b", "Accessory uses are subject to the standards in this article.")
    top = [(0.9, a)]
    ranked = [(0.9, a), (0.8, b)]
    out = _ensure_dimensional_rows(top, ranked, _request("minimum lot area"))
    assert {c.chunk_id for _, c in out} == {c.chunk_id for _, c in top}
