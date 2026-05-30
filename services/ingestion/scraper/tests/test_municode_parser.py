from __future__ import annotations

from services.ingestion.scraper.fetchers.municode import (
    DeepLinker,
    find_zoning_node,
    parse_client_id,
    parse_code_product_id,
    parse_content_sections,
    parse_job,
    parse_toc_children,
)

from .conftest import load_fixture


def test_parse_client_id():
    assert parse_client_id(load_fixture("municode_client.json")) == 8130


def test_parse_code_product_id():
    assert parse_code_product_id(load_fixture("municode_clientcontent.json")) == 10159


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
