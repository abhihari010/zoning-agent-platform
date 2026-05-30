from __future__ import annotations

from services.ingestion.scraper.fetchers.generic_html import split_into_sections
from services.ingestion.scraper.html_cleaner import clean_html

from .conftest import load_fixture


def test_split_into_sections_from_cleaned_page():
    cleaned = clean_html(load_fixture("generic_zoning_page.html"))
    records = split_into_sections(
        cleaned, base_url="https://example.org/zoning", source_type="zoning_ordinance"
    )
    refs = {r.section_ref for r in records}
    assert "Sec. 100" in refs
    assert "Sec. 101" in refs
    home_occ = next(r for r in records if r.section_ref == "Sec. 101")
    assert "home occupation" in home_occ.text.lower()
    assert home_occ.url == "https://example.org/zoning"
    # boilerplate stripped
    assert all("tracking" not in r.text for r in records)


def test_split_falls_back_to_single_section_without_headings():
    records = split_into_sections(
        "Just a paragraph of zoning text with no headings.",
        base_url="https://example.org/z",
        source_type="planning_page",
    )
    assert len(records) == 1
    assert records[0].section_ref == "Zoning page excerpt"
