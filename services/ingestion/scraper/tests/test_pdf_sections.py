"""The pdf fetcher's table-of-contents split (pure; needs no PDF or pdfplumber)."""

from services.ingestion.scraper.fetchers.pdf import effective_date, split_sections

TOC = (
    "CONTENTS\n"
    "§5.1. Residential (R) Districts Use Tables ...................... 5-1\n"
    "§5.6. R-6, One-Family Dwelling District ......................... 5-12\n"
)


def test_one_record_per_toc_entry_linked_to_its_page():
    pages = [
        TOC,
        "§5.1. Residential (R) Districts Use Tables\n| Use | R-6 |\n| One-family detached | P |",
        "§5.6. R-6, One-Family Dwelling District\nUses shall be as specified in §5.1.",
    ]

    records = split_sections(pages, url="https://example.gov/aczo.pdf")

    assert [r.section_ref for r in records] == ["§5.1", "§5.6"]
    assert records[1].heading == "§5.6. R-6, One-Family Dwelling District"
    assert records[1].url == "https://example.gov/aczo.pdf#page=3"
    assert "| One-family detached | P |" in records[0].text


def test_wrapped_cross_reference_is_not_a_heading():
    # A sentence can wrap so a line opens with "§5.6." -- only the heading carries
    # the TOC's own title after the number.
    pages = [
        TOC,
        "§5.1. Residential (R) Districts Use Tables\nas modified under\n§5.6. A sign as permitted by this section",
        "§5.6. R-6, One-Family Dwelling District\nbody",
    ]

    records = split_sections(pages, url="u")

    assert [r.section_ref for r in records] == ["§5.1", "§5.6"]
    assert "A sign as permitted" in records[0].text


def test_effective_date_from_cover():
    assert effective_date("Zoning Ordinance\n2026\nEffective June 13, 2026") == "2026-06-13"
    assert effective_date("no date here") is None
