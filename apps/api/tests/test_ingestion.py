"""Tests for section-aware markdown chunking in ingestion.py."""
from __future__ import annotations

import pytest

from app.ingestion import (
    MIN_CHUNK_CHARS,
    _apply_header_stamp,
    _split_markdown_by_sections,
    build_source_chunks,
)
from app.models import SourceRegistryEntry


# ---------------------------------------------------------------------------
# _split_markdown_by_sections
# ---------------------------------------------------------------------------


def test_split_markdown_no_headings_returns_single_section() -> None:
    text = "This is a plain paragraph with no headings."
    sections = _split_markdown_by_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert sections[0][1] == text


def test_split_markdown_h2_headings() -> None:
    text = "## Section One\nContent one.\n## Section Two\nContent two."
    sections = _split_markdown_by_sections(text)
    assert len(sections) == 2
    assert sections[0][0] == "Section One"
    assert "Content one" in sections[0][1]
    assert sections[1][0] == "Section Two"
    assert "Content two" in sections[1][1]


def test_split_markdown_h3_headings_included() -> None:
    text = "## Parking\n### Subsection A\nDetails here.\n### Subsection B\nMore details."
    sections = _split_markdown_by_sections(text)
    # Parking is the H2; then two H3s
    headings = [h for h, _ in sections]
    assert "Parking" in headings
    assert "Subsection A" in headings
    assert "Subsection B" in headings


def test_split_markdown_h4_headings_not_split() -> None:
    """Only ## and ### should cause splits; #### should stay in the body."""
    text = "## Main\n#### Sub-sub ignored\nBody text here."
    sections = _split_markdown_by_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "Main"
    assert "Sub-sub ignored" in sections[0][1]


def test_split_markdown_preamble_preserved() -> None:
    text = "Intro text before any heading.\n## Section\nSection body."
    sections = _split_markdown_by_sections(text)
    # Preamble should appear as the first section with empty heading
    assert sections[0][0] == ""
    assert "Intro text" in sections[0][1]
    assert sections[1][0] == "Section"


# ---------------------------------------------------------------------------
# build_source_chunks: markdown section awareness
# ---------------------------------------------------------------------------


def _make_md_source(full_text: str, source_id: str = "test-src") -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id=source_id,
        title="Test Document",
        excerpt=full_text[:200],
        full_text=full_text,
        section_ref="Document excerpt",
        jurisdiction_id="blacksburg-va",
        districts=["R-1"],
        uses=["residential"],
        source_type="zoning_ordinance",
        metadata={"imported_from": "test.md"},
    )


def test_markdown_source_splits_by_heading() -> None:
    md = (
        "## Parking Requirements\n"
        "Parking must have two spaces per unit for this residential conversion and "
        "the applicant must show the spaces on the submitted site plan.\n"
        "## Setbacks\n"
        "Front setback is twenty feet minimum for new structures and additions in this district."
    )
    source = _make_md_source(md)
    chunks = build_source_chunks([source])

    section_refs = {chunk.section_ref for chunk in chunks}
    assert "Parking Requirements" in section_refs
    assert "Setbacks" in section_refs


def test_markdown_chunks_drop_short_text() -> None:
    md = (
        "## Section A\n"
        "OK content here with enough text to exceed the useful chunk threshold for indexing.\n"
        "## Section B\n"
        "Tiny."
    )
    source = _make_md_source(md)
    chunks = build_source_chunks([source])

    # "Tiny." is shorter than MIN_CHUNK_CHARS and should be dropped.
    assert all(len(chunk.chunk_text.strip()) >= MIN_CHUNK_CHARS for chunk in chunks)
    # Section A's content should be present
    assert any("OK content" in chunk.chunk_text for chunk in chunks)


def test_non_markdown_source_still_works() -> None:
    source = SourceRegistryEntry(
        source_id="json-source",
        title="JSON Source",
        excerpt="This is a JSON-imported source with no headings.",
        full_text="This is a JSON-imported source with no headings and has enough content to pass the minimum chunk size threshold.",
        section_ref="Sec 1",
        source_type="zoning_ordinance",
        # No "imported_from" in metadata, so this is not treated as markdown.
    )
    chunks = build_source_chunks([source])
    assert len(chunks) >= 1
    assert all(len(chunk.chunk_text.strip()) >= MIN_CHUNK_CHARS for chunk in chunks)


def test_source_chunks_include_jurisdiction_metadata_contract() -> None:
    source = SourceRegistryEntry(
        source_id="metadata-contract-rule",
        title="Metadata Contract Rule",
        excerpt="Food service uses require zoning review with sufficient text for chunking.",
        section_ref="Sec 1",
        jurisdiction_id="blacksburg-va",
        url="https://www.blacksburg.gov/departments/departments-l-z/planning-and-building/zoning",
        effective_date="2026-05-25",
        districts=["mixed-use-core"],
        uses=["food-service"],
        source_type="zoning_ordinance",
    )

    chunk = build_source_chunks([source])[0]

    assert chunk.metadata["jurisdiction_scope"] == "local"
    assert chunk.metadata["state"] == "VA"
    assert chunk.metadata["municipality"] == "Blacksburg"
    assert chunk.metadata["coverage_status"] == "public_supported"
    assert chunk.metadata["content_hash"] == chunk.source_text_hash
    assert chunk.metadata["source_version"] == chunk.source_version


def test_chunk_ids_are_deterministic() -> None:
    md = "## Section\nContent that is long enough to be a useful chunk."
    source = _make_md_source(md)
    chunks1 = build_source_chunks([source])
    chunks2 = build_source_chunks([source])
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]


def test_chunk_ids_change_when_source_text_changes() -> None:
    source_a = _make_md_source("## Section\nContent A has enough text to exceed the minimum threshold.")
    source_b = _make_md_source("## Section\nContent B is different text and changes the hash and IDs.")
    chunks_a = build_source_chunks([source_a])
    chunks_b = build_source_chunks([source_b])
    assert [c.chunk_id for c in chunks_a] != [c.chunk_id for c in chunks_b]


def test_long_markdown_body_is_further_chunked() -> None:
    """A section body longer than DEFAULT_CHUNK_MAX_CHARS must produce multiple chunks."""
    long_body = " ".join([f"word{i}" for i in range(300)])
    md = f"## Long Section\n{long_body}"
    source = _make_md_source(md)
    chunks = build_source_chunks([source])
    # Long body should result in more than one chunk
    assert len(chunks) > 1
    # All should have the section heading as section_ref
    assert all(chunk.section_ref == "Long Section" for chunk in chunks)


# ---------------------------------------------------------------------------
# _apply_header_stamp
# ---------------------------------------------------------------------------


def test_header_stamp_prepends_title_to_normal_chunk() -> None:
    title = "Sec. 10-24 - R-1 Residential District"
    text = "Minimum lot area. 20,000 square feet."
    stamped = _apply_header_stamp(title, text)
    assert stamped == f"[{title}] {text}"
    # The district label now co-occurs with the measurement in the same chunk.
    assert "R-1" in stamped
    assert "20,000 square feet" in stamped


def test_header_stamp_does_not_double_stamp_when_chunk_starts_with_title() -> None:
    title = "Sec. 10-24 - R-1 Residential District"
    # First chunk of a section-led source already opens with the title text.
    text = f"{title}. Minimum lot area shall be 20,000 square feet."
    stamped = _apply_header_stamp(title, text)
    assert stamped == text
    # No leading "[...]" wrapper was added.
    assert not stamped.startswith("[")


def test_header_stamp_ignores_leading_whitespace_when_detecting_double_stamp() -> None:
    title = "Sec. 10-24 - R-1 Residential District"
    text = f"   {title} continues here with the rest of the section body."
    stamped = _apply_header_stamp(title, text)
    # lstrip() comparison means the already-titled chunk is left untouched.
    assert stamped == text


@pytest.mark.parametrize("title", [None, "", "   "])
def test_header_stamp_returns_text_unchanged_for_empty_title(title: str | None) -> None:
    text = "Some chunk text that should pass through untouched."
    assert _apply_header_stamp(title, text) == text


def test_header_stamp_token_count_computed_from_stamped_text() -> None:
    """build_source_chunks must compute token_count from the post-stamp text."""
    full_text = (
        "Minimum lot area in this district shall be twenty thousand square feet "
        "and the front yard setback shall be forty feet from the property line."
    )
    source = SourceRegistryEntry(
        source_id="stamp-token-src",
        title="Sec. 10-24 - R-1 Residential District",
        excerpt=full_text[:200],
        full_text=full_text,
        section_ref="Sec. 10-24",
        jurisdiction_id="blacksburg-va",
        districts=["R-1"],
        uses=["residential"],
        source_type="zoning_ordinance",
        metadata={},  # not a .md import: stays as a single plain-text chunk
    )
    chunks = build_source_chunks([source])
    assert chunks, "expected at least one chunk"
    chunk = chunks[0]
    # The stamp was applied (title not already at the chunk start).
    assert chunk.chunk_text.startswith(f"[{source.title}] ")
    # token_count reflects the stamped text, not the pre-stamp body.
    assert chunk.token_count == len(chunk.chunk_text.split())
    assert chunk.token_count > len(full_text.split())
