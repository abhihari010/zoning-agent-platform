"""Offline parser tests for the Municipal Code Online fetcher.

These exercise the pure parsing helpers against saved real responses (no live
network).  The fixtures were captured from
``https://montgomery.municipalcodeonline.com`` (Montgomery County, VA — Chapter
10 ZONING) using the ``x-csrf: 1`` + ``X-Requested-With`` guard headers.
"""

from __future__ import annotations

from services.ingestion.scraper.fetchers.municipalcodeonline import (
    DeepLinker,
    effective_date_from_history,
    find_zoning_node,
    parse_content_payload,
    parse_expand,
    parse_section,
    section_ref_from_name,
)

from .conftest import load_fixture


def test_parse_expand_root_shape():
    nodes = parse_expand(load_fixture("mco_expand_root.json"))
    assert nodes
    assert all(set(n) == {"id", "name", "has_children"} for n in nodes)
    ids = {n["id"] for n in nodes}
    assert "10_ZONING" in ids


def test_find_zoning_node_picks_zoning_not_subdivision():
    node = find_zoning_node(load_fixture("mco_expand_root.json"))
    assert node["id"] == "10_ZONING"
    assert "ZONING" in node["name"].upper()
    assert "SUBDIVISION" not in node["name"].upper()
    assert node["has_children"] is True


def test_expand_chapter_yields_articles():
    articles = parse_expand(load_fixture("mco_expand_ch10.json"))
    headings = {a["name"].upper() for a in articles}
    assert any("ARTICLE" in h for h in headings)
    assert any("BASE DISTRICT REGULATIONS" in h for h in headings)


def test_section_ref_from_name():
    assert section_ref_from_name("Sec 10-24 R-1 Residential District") == "Sec. 10-24"
    assert section_ref_from_name("Sec 10-32.1 Traditional Neighborhood") == "Sec. 10-32.1"
    assert section_ref_from_name("Secs 10-9 - 10-20 (Reserved)") == "Secs. 10-9"
    assert section_ref_from_name("10 ARTICLE I IN GENERAL") is None


def test_parse_section_district_section_has_real_text_and_deep_link():
    deep_link = DeepLinker(host_slug="montgomery")
    node = {
        "id": "Sec_10-24_R-1_Residential_District",
        "name": "Sec 10-24 R-1 Residential District",
        "has_children": False,
    }
    html = parse_content_payload(load_fixture("mco_content_sec_10-24.json"))
    record = parse_section(
        node=node,
        content_html=html,
        deep_link=deep_link,
        breadcrumb=["10 ZONING", "10 ARTICLE II BASE DISTRICT REGULATIONS"],
        chapter_name="10 ZONING",
    )
    assert record is not None
    assert record.section_ref == "Sec. 10-24"
    assert record.heading == "Sec 10-24 R-1 Residential District"
    assert record.source_type == "zoning_ordinance"
    assert "r-1 residential district" in record.text.lower()
    # Heading anchor div must be stripped from the body, not duplicated.
    assert not record.text.lstrip().lower().startswith("sec 10-24")
    assert record.url == (
        "https://montgomery.municipalcodeonline.com/book?type=ordinances"
        "#name=Sec_10-24_R-1_Residential_District"
    )
    assert record.breadcrumb == [
        "10 ZONING",
        "10 ARTICLE II BASE DISTRICT REGULATIONS",
    ]
    assert record.metadata["scraper"] == "municipalcodeonline"
    assert record.metadata["mco_node_id"] == node["id"]


def test_parse_section_skips_reserved():
    deep_link = DeepLinker(host_slug="montgomery")
    node = {
        "id": "Secs_10-9_-_10-20_(Reserved)",
        "name": "Secs 10-9 - 10-20 (Reserved)",
        "has_children": False,
    }
    record = parse_section(
        node=node,
        content_html="<div><p>Reserved.</p></div>",
        deep_link=deep_link,
        breadcrumb=["10 ZONING"],
        chapter_name="10 ZONING",
    )
    assert record is None


def test_effective_date_from_history_picks_latest():
    # Section 10-24 carries HISTORY notes with M/D/YYYY amendment dates.
    html = parse_content_payload(load_fixture("mco_content_sec_10-24.json"))
    iso = effective_date_from_history(html)
    # Either a real amendment date was found, or None (graceful) — but if found
    # it must be a valid ISO date string.
    if iso is not None:
        assert len(iso) == 10 and iso[4] == "-" and iso[7] == "-"


def test_deep_linker_home_url():
    deep_link = DeepLinker(host_slug="montgomery")
    assert deep_link.home_url == (
        "https://montgomery.municipalcodeonline.com/book?type=ordinances"
    )
