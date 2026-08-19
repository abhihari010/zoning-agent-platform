"""The SQL keyword path must reserve the permitted-use table, like Qdrant does.

``_sql_keyword_retrieve`` is not a test-only branch: it serves deployments with
no vector store and every ``_fallback_to_sql`` degradation in production. It
previously applied only ``_diversify_ranked``, so the permitted-use table --
the primary evidence for a use decision -- was dropped by the top_n cutoff
exactly when retrieval was already degraded.

Pure fixtures, no Qdrant/Groq/Postgres.
"""
from __future__ import annotations

from app.ai.hybrid_local_retriever import HybridLocalRetrievalProvider
from app.ai.interfaces import RetrievalProviderRequest
from app.models import SourceChunk

_TOP_N = 8  # _diversify_ranked default


def _chunk(chunk_id: str, text: str, section_ref: str, uses: list[str]) -> SourceChunk:
    return SourceChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        title=section_ref,
        chunk_text=text,
        chunk_index=0,
        source_text_hash="0" * 64,
        section_ref=section_ref,
        jurisdiction_id="testville",
        districts=["commercial-employment"],
        uses=uses,
    )


def _corpus() -> list[SourceChunk]:
    """One use table that loses the cutoff to a crowd of chattier prose chunks.

    The table row carries the answer but little vocabulary (a use matrix is
    mostly repeated ``P``/``C`` symbols), so plain token-overlap scoring ranks
    it below prose that echoes more of the query.
    """
    query_words = "restaurant seating patio parking sign hours employees kitchen"
    prose = [
        _chunk(
            f"prose-{i}",
            f"Sec. 7-{i}. General standards for {query_words} in business districts.",
            f"Sec. 7-{i}",
            ["general"],
        )
        for i in range(_TOP_N + 4)
    ]
    table = _chunk(
        "use-table",
        "Restaurant | P | P | C | P",
        "Sec. 7-602",
        ["general", "principal_uses"],
    )
    return [*prose, table]


def _request() -> RetrievalProviderRequest:
    return RetrievalProviderRequest(
        district="commercial-employment",
        inferred_use="general",
        project_description=(
            "Open a restaurant with patio seating, parking, a sign, "
            "extended hours, employees, and a kitchen."
        ),
        jurisdiction_id="testville",
    )


def test_sql_path_reserves_the_permitted_use_table() -> None:
    chunks = _corpus()
    result = HybridLocalRetrievalProvider(source_store=None)._sql_keyword_retrieve(
        _request(), chunks, start=0.0
    )
    refs = [c.section_ref for c in result.citations]

    # The guard: without the reserve the table is outranked and never cited.
    assert "Sec. 7-602" in refs, f"permitted-use table dropped from SQL retrieval: {refs}"


def test_use_table_would_not_survive_ranking_alone() -> None:
    """Keep the fixture honest: the table must genuinely lose on score.

    If chattier prose ever stops outranking it, the test above would pass for
    the wrong reason and stop guarding the reserve.
    """
    from app.ai.hybrid_local_retriever import _diversify_ranked, _score_chunk, _tokens

    request = _request()
    query_tokens = _tokens(request.query)
    ranked = sorted(
        ((_score_chunk(c, request, query_tokens), c) for c in _corpus()),
        key=lambda item: item[0],
        reverse=True,
    )
    survivors = {chunk.section_ref for _, chunk in _diversify_ranked(ranked)}
    assert "Sec. 7-602" not in survivors


def test_shipped_packs_never_tag_principal_uses_without_general() -> None:
    """A ``principal_uses`` marker is inert unless the chunk also carries ``general``.

    ``list_source_chunks_filtered`` keeps a chunk only when its ``uses_csv``
    matches the inferred use *or* the ``general`` wildcard, so a marker-only tag
    drops the use table from the candidate set before ``_score_chunk`` -- and so
    before ``_ensure_use_table_rows`` can reserve a slot for it. Measured on
    chesapeake-va at 0.350, below its 0.400 untagged baseline. Same reasoning for
    ``districts``: a table tagged only with raw zone codes fails the district
    filter, which passes ``unknown``/``*`` or the requested category.
    """
    from app.ingestion import import_source_packs

    offenders = [
        (entry.jurisdiction_id, entry.section_ref, entry.uses, entry.districts)
        for entry in import_source_packs()
        if "principal_uses" in entry.uses
        and (
            "general" not in entry.uses
            or not {"unknown", "*"}.intersection(entry.districts)
            and not _DISTRICT_CATEGORIES.intersection(entry.districts)
        )
    ]
    assert offenders == []


# The coarse district vocabulary a request can carry (app/district_mapping.py).
_DISTRICT_CATEGORIES = {
    "residential-low-density",
    "commercial-employment",
    "industrial-zone",
    "agricultural",
    "mixed-use-core",
}
