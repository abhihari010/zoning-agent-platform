from __future__ import annotations

from services.ingestion.scraper.fetchers.municode import (
    DeepLinker,
    _section_ref_from_title,
    _slugify_product,
    find_zoning_node,
    parse_client_id,
    parse_code_product_id,
    parse_content_sections,
    parse_job,
    parse_toc_children,
    select_zoning_product,
)

from .conftest import load_fixture


def test_parse_client_id():
    assert parse_client_id(load_fixture("municode_client.json")) == 8130


def test_parse_code_product_id():
    assert parse_code_product_id(load_fixture("municode_clientcontent.json")) == 10159


def test_select_zoning_product_prefers_dedicated_zoning_code():
    # Chesapeake-style: separate "Code of Ordinances" + "Zoning" products.
    product_id, name, is_dedicated = select_zoning_product(
        load_fixture("municode_clientcontent_dual.json")
    )
    assert product_id == 12653
    assert name == "Zoning"
    assert is_dedicated is True


def test_select_zoning_product_falls_back_to_combined_code():
    # Blacksburg-style: a single combined Code of Ordinances product (zoning
    # lives inside it as an appendix).
    product_id, name, is_dedicated = select_zoning_product(
        load_fixture("municode_clientcontent.json")
    )
    assert product_id == 10159
    assert is_dedicated is False


def test_slugify_product_matches_municode_url_convention():
    assert _slugify_product("Zoning") == "zoning"
    assert _slugify_product("Code of Ordinances") == "code_of_ordinances"
    assert (
        _slugify_product("Unified Development Ordinance")
        == "unified_development_ordinance"
    )
    assert _slugify_product("") == "code_of_ordinances"


def test_section_ref_from_title_handles_both_numbering_styles():
    # Blacksburg-style "Sec." numbering.
    assert _section_ref_from_title("Sec. 4211 - Home occupations.") == "Sec. 4211"
    assert _section_ref_from_title("Sec 4211 - Home occupations.") == "Sec. 4211"
    # Chesapeake-style "§" numbering (dedicated Zoning product); trailing
    # punctuation from "§ 6-100. - Intent." is dropped.
    assert _section_ref_from_title("§ 6-100. - Intent.") == "§ 6-100"
    assert _section_ref_from_title("§ 6-301. - Description.") == "§ 6-301"
    # Alexandria-style bare numbering (no "Sec."/"§" prefix).
    assert _section_ref_from_title("3-101 - Purpose.") == "3-101"
    assert _section_ref_from_title("3-102.1 - Administrative special uses.") == "3-102.1"
    assert _section_ref_from_title("40.2-100 - Title.") == "40.2-100"
    # Structural / non-section headings parse to None.
    assert _section_ref_from_title("ARTICLE 6. - RESIDENTIAL DISTRICTS") is None
    assert _section_ref_from_title("ARTICLE III. - RESIDENTIAL ZONE REGULATIONS") is None


def test_deep_linker_uses_dedicated_code_slug():
    deep_link = DeepLinker(state="VA", city_slug="chesapeake", code_slug="zoning")
    assert deep_link.home_url == "https://library.municode.com/va/chesapeake/codes/zoning"
    assert deep_link("ZO_ART6REDI") == (
        "https://library.municode.com/va/chesapeake/codes/zoning?nodeId=ZO_ART6REDI"
    )


def test_parse_job_extracts_effective_date_from_banner():
    job_id, effective = parse_job(load_fixture("municode_job.json"))
    assert job_id == 485152
    # Banner: "...Ordinance No. 2104, enacted December 9, 2025."
    assert effective == "2025-12-09"


def test_find_zoning_node_picks_zoning_not_subdivision():
    node_id, heading = find_zoning_node(load_fixture("municode_toc_root.json"))
    assert node_id == "CO_APXAORNO1137BLZOOR"
    assert "ZONING" in heading.upper()
    assert "SUBDIVISION" not in heading.upper()


def test_parse_toc_children_shape():
    children = parse_toc_children(load_fixture("municode_toc_zoning_children.json"))
    assert children
    headings = {c["heading"] for c in children}
    assert any("ARTICLE" in h.upper() for h in headings)
    assert all(set(c) == {"id", "heading", "has_children"} for c in children)


def test_parse_content_sections_emits_one_per_section_with_real_text():
    deep_link = DeepLinker(state="VA", city_slug="blacksburg")
    records = parse_content_sections(
        load_fixture("municode_content_homeocc.json"),
        deep_link=deep_link,
        breadcrumb=["ARTICLE IV. - USE AND DESIGN STANDARDS"],
        effective_date="2025-12-09",
    )
    # Reserved + structural docs are skipped; substantive sections remain.
    assert len(records) >= 6
    by_ref = {r.section_ref: r for r in records}

    # Home occupations section is present, citable, with deep link and real text.
    assert "Sec. 4211" in by_ref
    home_occ = by_ref["Sec. 4211"]
    assert home_occ.heading.startswith("Sec. 4211")
    assert "nodeId=CO_APXAORNO1137BLZOOR_ARTIVUSDEST_DIV2REUS_S4211HOOC" in home_occ.url
    assert "home occupation" in home_occ.text.lower()
    assert home_occ.source_type == "zoning_ordinance"
    assert home_occ.effective_date == "2025-12-09"
    assert home_occ.breadcrumb == ["ARTICLE IV. - USE AND DESIGN STANDARDS"]

    # Reserved placeholder sections must be excluded.
    assert all("reserved" not in r.heading.lower() for r in records)
    # No empty text records.
    assert all(r.text.strip() for r in records)


def test_deep_linker_home_url():
    deep_link = DeepLinker(state="VA", city_slug="blacksburg")
    assert deep_link.home_url == (
        "https://library.municode.com/va/blacksburg/codes/code_of_ordinances"
    )


def test_parse_content_sections_letter_outline_qualified_by_article():
    # Danville, VA (Ch. 41) organizes Article -> lettered sections ("A. -
    # Purpose and Intent.") with no "Sec. N" numbering.  The letters must be
    # emitted as sections with refs qualified by the article number.
    deep_link = DeepLinker(state="VA", city_slug="danville", code_slug="zoning")
    records = parse_content_sections(
        load_fixture("municode_content_danville_art7.json"),
        deep_link=deep_link,
        breadcrumb=["Chapter 41 - ZONING ORDINANCE"],
        effective_date="2025-06-03",
    )
    by_ref = {r.section_ref: r for r in records}
    assert "7.A" in by_ref
    purpose = by_ref["7.A"]
    assert purpose.heading == "A. - Purpose and Intent."
    assert "nodeId=CH41ZOOR_ART7NOUS_APUIN" in purpose.url
    assert purpose.text.strip()
    # The structural article doc itself must not become a record.
    assert not any(r.heading.startswith("ARTICLE") for r in records)


def test_parse_content_sections_letter_outline_article_from_breadcrumb():
    # A chunk that starts mid-article carries no article doc; the enclosing
    # article number is seeded from the breadcrumb.  Letter-suffixed article
    # numbers ("ARTICLE 3.N:") qualify as "3.N.C".
    deep_link = DeepLinker(state="VA", city_slug="danville", code_slug="zoning")
    payload = {
        "Docs": [
            {
                "Id": "CH41ZOOR_ART3.NPLSHCECOPLSHCEDI._C",
                "Title": "C. - Uses Permitted by Special Use Permit.",
                "Content": "<p>Uses permitted by special use permit.</p>",
            }
        ]
    }
    records = parse_content_sections(
        payload,
        deep_link=deep_link,
        breadcrumb=[
            "Chapter 41 - ZONING ORDINANCE",
            "ARTICLE 3.N: - PS-C, PLANNED SHOPPING CENTER COMMERCIAL",
        ],
    )
    assert [r.section_ref for r in records] == ["3.N.C"]


def test_parse_content_sections_letter_outline_without_article_is_skipped():
    # A bare letter heading with no article context anywhere is not citable.
    deep_link = DeepLinker(state="VA", city_slug="danville", code_slug="zoning")
    payload = {
        "Docs": [
            {
                "Id": "SOME_NODE",
                "Title": "A. - Orphan.",
                "Content": "<p>text</p>",
            }
        ]
    }
    assert parse_content_sections(payload, deep_link=deep_link) == []
