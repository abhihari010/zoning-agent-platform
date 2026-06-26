"""Offline parser tests for the eCode360 / General Code fetcher.

These exercise the pure parsing helpers against saved real responses (no live
network).  The fixtures were captured from ``https://ecode360.com`` for the
Borough of Millersville, PA (custId ``MI2395``, Chapter 380 ZONING).  The
reserved-section fixture is captured from Township of Horsham, PA (Chapter 230).
"""

from __future__ import annotations

from services.ingestion.scraper.fetchers.ecode360 import (
    DeepLinker,
    collect_leaf_sections,
    effective_date_from_history,
    find_zoning_node,
    parse_article_page,
    parse_code_info,
    parse_section,
    parse_toc,
)

from .conftest import load_fixture


def test_parse_code_info_returns_customer_id():
    cust_id = parse_code_info(load_fixture("ecode360_ajax_code_info.json"))
    assert cust_id == "MI2395"


def test_parse_toc_root_shape():
    root = parse_toc(load_fixture("ecode360_toc_root.json"))
    assert root["guid"] == "MI2395"
    assert root["type"] == "code"
    assert root["children"]
    # Every normalised node carries the canonical key set.
    expected_keys = {"guid", "title", "number", "type", "label", "href", "children"}
    assert set(root.keys()) == expected_keys
    for child in root["children"]:
        assert set(child.keys()) == expected_keys


def test_parse_toc_art1_shape():
    art = parse_toc(load_fixture("ecode360_toc_art1.json"))
    assert art["guid"] == "9655590"
    assert art["type"] == "article"
    assert art["title"] == "Administration"
    section_refs = {c["number"] for c in art["children"]}
    assert "§ 380-1" in section_refs


def test_find_zoning_node_picks_zoning_chapter_not_map():
    node = find_zoning_node(load_fixture("ecode360_toc_root.json"))
    assert node["title"] == "Zoning"
    assert node["type"] == "chapter"
    assert node["guid"] == "9655589"
    # The "Zoning Map." section must NOT be selected as the zoning chapter.
    assert "map" not in node["title"].lower()


def test_collect_leaf_sections_pairs_section_with_article():
    root = parse_toc(load_fixture("ecode360_toc_root.json"))
    zoning = find_zoning_node(root)
    pairs = collect_leaf_sections(zoning)
    # Zoning chapter has Art I (3) + Art II (2) + Art III (7) + Art VIII (1) = 13.
    assert len(pairs) == 13
    # Every collected node is a leaf section paired with its article parent guid.
    for section_node, article_guid in pairs:
        assert section_node["type"] == "section"
        assert article_guid
    # § 380-1 lives under Art I (guid 9655590).
    first_section, first_article = pairs[0]
    assert first_section["guid"] == "9655591"
    assert first_article == "9655590"


def test_parse_article_page_art1_yields_real_section_records():
    deep_link = DeepLinker(customer_id="MI2395")
    records = parse_article_page(
        load_fixture("ecode360_html_art1.html"),
        deep_link=deep_link,
        zoning_chapter_title="Zoning",
        breadcrumb=["Zoning", "Administration"],
    )
    assert len(records) == 3
    refs = {r.section_ref for r in records}
    assert {"§ 380-1", "§ 380-2", "§ 380-3"} == refs

    rec = next(r for r in records if r.section_ref == "§ 380-1")
    assert rec.node_id == "9655591"
    assert rec.url == "https://ecode360.com/9655591"
    assert rec.heading == "§ 380-1: Title; enactment; repealer."
    assert "Zoning Ordinance of the Borough of Millersville" in rec.text
    # The leading <div class="history"> note is stripped from the body text.
    assert "[Adopted" not in rec.text
    assert "Ord. No. 437" not in rec.text
    # Effective date comes from the most recent HISTORY hisdate span.
    assert rec.effective_date == "2006-11-13"
    assert rec.breadcrumb == ["Zoning", "Administration"]
    assert rec.metadata["scraper"] == "ecode360"
    assert rec.metadata["ecode360_guid"] == "9655591"
    assert rec.metadata["ecode360_chapter"] == "Zoning"
    assert rec.source_type == "zoning_ordinance"


def test_parse_article_page_art3_flags_dimensional_table():
    deep_link = DeepLinker(customer_id="MI2395")
    records = parse_article_page(
        load_fixture("ecode360_html_art3.html"),
        deep_link=deep_link,
        zoning_chapter_title="Zoning",
        breadcrumb=["Zoning", "Districts"],
    )
    refs = {r.section_ref for r in records}
    assert "§ 380-22" in refs
    assert "§ 380-28" in refs

    dim = next(r for r in records if r.section_ref == "§ 380-28")
    assert dim.metadata["tables_flattened"] is True
    assert dim.effective_date == "2023-09-25"
    # The dimensional table's cell values survive HTML flattening.
    assert "7,500" in dim.text


def test_parse_article_page_skips_reserved_section():
    deep_link = DeepLinker(customer_id="HO1764")
    records = parse_article_page(
        load_fixture("ecode360_html_art_reserved.html"),
        deep_link=deep_link,
        zoning_chapter_title="Zoning",
        breadcrumb=["Zoning", "VC Village Commercial District"],
    )
    # Only the substantive § 230-176 section survives; the
    # "§ 230-180: through § 230-190. (Reserved)" placeholder is dropped.
    assert len(records) == 1
    assert records[0].section_ref == "§ 230-176"
    assert all("reserved" not in r.heading.lower() for r in records)


def test_parse_section_returns_none_for_reserved_block():
    deep_link = DeepLinker(customer_id="HO1764")
    block = (
        '<header><div data-guid="50445573" '
        'data-full-title="§ 230-180: through § 230-190. (Reserved)">'
        '<span class="titleNumber">§ 230-180</span></div></header>'
        '<div class="section_content content" id="50445573_content">'
        '<div class="para">[Reserved]</div></div>'
    )
    record = parse_section(
        article_block=block,
        deep_link=deep_link,
        zoning_chapter_title="Zoning",
        breadcrumb=["Zoning"],
    )
    assert record is None


def test_effective_date_from_history_picks_latest():
    html = load_fixture("ecode360_html_art1.html")
    iso = effective_date_from_history(html)
    assert iso is not None
    assert len(iso) == 10 and iso[4] == "-" and iso[7] == "-"
    # 6-2-1997 and 11-13-2006 are present; the latest wins.
    assert iso == "2006-11-13"


def test_effective_date_from_history_none_when_absent():
    assert effective_date_from_history("<div class='para'>No dates here.</div>") is None


def test_deep_linker_urls():
    deep_link = DeepLinker(customer_id="MI2395")
    assert deep_link.home_url == "https://ecode360.com/MI2395"
    assert deep_link("9655591") == "https://ecode360.com/9655591"
    # When an article parent guid is supplied, the link uses an anchor.
    assert deep_link("9655591", "9655590") == "https://ecode360.com/9655590#9655591"
