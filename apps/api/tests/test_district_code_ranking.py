"""The parcel's own district code outranks its coarse-family siblings.

The five-value vocabulary lumps every R district together, so an R-1 question
scores R-2 through R-73 exactly as highly and the right section has to win on
wording alone. Sections now carry their own code alongside the family, and a
request carries the code the GIS resolved.
"""

from __future__ import annotations

import pytest

from app.ai.hybrid_local_retriever import _score_chunk, _tokens
from app.ai.interfaces import RetrievalProviderRequest
from app.models import SourceChunk
from app.source_classifier import classify_source


def _chunk(section_ref: str, districts: list[str], text: str = "minimum lot area") -> SourceChunk:
    return SourceChunk(
        chunk_id=f"c-{section_ref}",
        source_id=f"s-{section_ref}",
        title=f"Sec. {section_ref}",
        chunk_text=text,
        chunk_index=0,
        source_text_hash="0" * 64,
        section_ref=section_ref,
        jurisdiction_id="richmond-va",
        districts=districts,
    )


def _request(district: str, district_code: str | None) -> RetrievalProviderRequest:
    return RetrievalProviderRequest(
        district=district,
        inferred_use="general",
        project_description="minimum lot area",
        jurisdiction_id="richmond-va",
        district_code=district_code,
    )


def test_the_parcels_own_district_outranks_a_same_family_sibling():
    request = _request("residential-low-density", "R-1")
    tokens = _tokens(request.query)

    mine = _chunk("30-402.4", ["residential-low-density", "R-1"])
    sibling = _chunk("30-412.4", ["residential-low-density", "R-53"])

    assert _score_chunk(mine, request, tokens) > _score_chunk(sibling, request, tokens)


def test_a_family_sibling_still_outranks_an_unclassified_section():
    # The code is a refinement, not a replacement: everything that ranked above
    # "unknown" before must still do so.
    request = _request("residential-low-density", "R-1")
    tokens = _tokens(request.query)

    sibling = _chunk("30-412.4", ["residential-low-density", "R-53"])
    unclassified = _chunk("30-999.1", ["unknown"])

    assert _score_chunk(sibling, request, tokens) > _score_chunk(unclassified, request, tokens)


def test_an_unresolved_code_changes_nothing():
    tokens = _tokens("minimum lot area")
    chunk = _chunk("30-402.4", ["residential-low-density", "R-1"])

    without = _score_chunk(chunk, _request("residential-low-density", None), tokens)
    unknown_code = _score_chunk(chunk, _request("residential-low-density", "ZZ-9"), tokens)

    assert without == unknown_code


def test_separator_differences_between_gis_and_ordinance_still_match():
    # The layer records "R1"; richmond's ordinance division reads "R-1".
    request = _request("residential-low-density", "R1")
    tokens = _tokens(request.query)

    mine = _chunk("30-402.4", ["residential-low-density", "R-1"])
    sibling = _chunk("30-412.4", ["residential-low-density", "R-53"])

    assert _score_chunk(mine, request, tokens) > _score_chunk(sibling, request, tokens)


@pytest.mark.parametrize(
    ("division", "expected"),
    [
        ("DIVISION 10. - R-53 MULTIFAMILY RESIDENTIAL DISTRICT", "R-53"),
        ("ARTICLE 8 - HIGHWAY COMMERCIAL DISTRICT�B-2", "B-2"),
        ("ARTICLE 3.F: - A-R, ATTACHED RESIDENTIAL DISTRICT", "A-R"),
        # No code in the heading, and no invented one.
        ("ARTICLE IV. - DISTRICT REGULATIONS", None),
        ("ARTICLE 6. - RESIDENTIAL DISTRICTS", None),
    ],
)
def test_classification_reads_the_code_out_of_the_heading(division, expected):
    from app.models import SourceRegistryEntry

    source = SourceRegistryEntry(
        source_id="s1",
        title="Sec. 30-402.4. - Lot area.",
        excerpt="Minimum lot area shall be 6,000 square feet.",
        section_ref="Sec. 30-402.4.",
        metadata={"breadcrumb": ["Chapter 30 - ZONING", "ARTICLE IV. - DISTRICT REGULATIONS", division]},
    )
    rules = {
        "rules": [
            {
                "article_contains": "ARTICLE IV. - DISTRICT REGULATIONS",
                "districts": ["residential-low-density"],
                "uses": ["general"],
            }
        ]
    }
    districts, _ = classify_source(source, rules)

    assert districts[0] == "residential-low-density", "the family must never be dropped"
    assert (districts[1] if len(districts) > 1 else None) == expected
