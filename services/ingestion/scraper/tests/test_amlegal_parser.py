"""Offline parser tests for the American Legal Publishing fetcher.

These exercise the pure parsing helpers against saved real responses (no live
network).  The fixtures were captured from ``https://codelibrary.amlegal.com``
for Plain City, OH (client ``plaincity``, code ``plaincity_oh``, PART ELEVEN -
PLANNING AND ZONING CODE).
"""

from __future__ import annotations

from services.ingestion.scraper.fetchers.amlegal import (
    DeepLinker,
    currency_to_iso,
    effective_date_from_html,
    extract_code_ref,
    find_zoning_node,
    is_excluded_branch,
    parse_client_search,
    parse_code_toc,
    parse_render_section,
    parse_section_toc,
    section_ref_from_title,
)

from .conftest import load_fixture


def test_parse_client_search_picks_city_in_correct_state():
    slug = parse_client_search(
        load_fixture("amlegal_clients_search.json"), city="Plain City", state="OH"
    )
    assert slug == "plaincity"


def test_parse_client_search_disambiguates_by_state():
    # There is also a Plain City, UT in the fixture — state must disambiguate.
    slug = parse_client_search(
        load_fixture("amlegal_clients_search.json"), city="Plain City", state="UT"
    )
    assert slug == "plaincityut"


def test_extract_code_ref_from_landing():
    code_uuid, code_slug = extract_code_ref(load_fixture("amlegal_landing.html"))
    assert code_uuid == "7989f740-69ad-4c65-b2bf-e47f1b8ae98a"
    assert code_slug == "plaincity_oh"


def test_parse_code_toc_shape():
    toc = parse_code_toc(load_fixture("amlegal_code_toc.json"))
    assert toc["uuid"] == "7989f740-69ad-4c65-b2bf-e47f1b8ae98a"
    assert toc["slug"] == "plaincity_oh"
    assert toc["sections"]
    for s in toc["sections"]:
        assert set(s.keys()) == {
            "id", "doc_id", "orig_doc_id", "orig_doc_idx", "title", "type", "has_children"
        }


def test_find_zoning_node_picks_planning_and_zoning_part():
    toc = parse_code_toc(load_fixture("amlegal_code_toc.json"))
    node = find_zoning_node(toc["sections"])
    assert "ZONING" in node["title"].upper()
    assert "SUBDIVISION" not in node["title"].upper()
    assert node["doc_id"] == "0-0-0-9760"
    assert node["id"]  # numeric id used for section-toc expansion


def test_is_excluded_branch_skips_subdivision():
    zoning = parse_section_toc(load_fixture("amlegal_section_toc_zoning.json"))
    titles = [c["title"] for c in zoning["children"]]
    assert any("Subdivision" in t for t in titles)
    excluded = [t for t in titles if is_excluded_branch(t)]
    kept = [t for t in titles if not is_excluded_branch(t)]
    assert any("Subdivision" in t for t in excluded)
    assert all("Subdivision" not in t for t in kept)
    assert any("Zoning" in t for t in kept)


def test_parse_section_toc_children():
    chapter = parse_section_toc(load_fixture("amlegal_section_toc_chapter.json"))
    assert chapter["title"].startswith("CHAPTER 1141")
    refs = {c["doc_id"] for c in chapter["children"]}
    assert "0-0-0-12382" in refs
    leaf = next(c for c in chapter["children"] if c["doc_id"] == "0-0-0-12382")
    assert leaf["orig_doc_id"] == "0-0-0-12369"
    assert leaf["orig_doc_idx"] == 1
    assert leaf["has_children"] is False


def test_section_ref_from_title():
    assert section_ref_from_title("1141.01 ZONING DISTRICT MAP ADOPTED.") == "1141.01"
    assert section_ref_from_title("1182.05 RESERVED.") == "1182.05"
    assert section_ref_from_title("17-1-0501 Establishment of districts") == "17-1-0501"
    assert section_ref_from_title("CHAPTER 1141 Zoning District Map") is None
    assert section_ref_from_title("TITLE FIVE - Zoning Districts") is None


def test_parse_render_section_real_section():
    deep_link = DeepLinker(client_slug="plaincity", code_slug="plaincity_oh")
    record = parse_render_section(
        load_fixture("amlegal_render_section.json"),
        deep_link=deep_link,
        breadcrumb=["PART ELEVEN - PLANNING AND ZONING CODE", "TITLE FIVE - Zoning Districts and Regulations"],
        chapter_title="CHAPTER 1141 Zoning District Map",
    )
    assert record is not None
    assert record.section_ref == "1141.01"
    assert record.heading == "1141.01 ZONING DISTRICT MAP ADOPTED."
    assert record.node_id == "0-0-0-12382"
    assert record.url == (
        "https://codelibrary.amlegal.com/codes/plaincity/latest/plaincity_oh/0-0-0-12382"
    )
    # Body text is present; the duplicated <h4> heading is stripped.
    assert "All land in the Municipality is placed into a zoning district" in record.text
    assert "ZONING DISTRICT MAP ADOPTED." not in record.text
    # Effective date parsed from the "(Ord. 05-08.  Passed 2-25-08.)" history note.
    assert record.effective_date == "2008-02-25"
    assert record.breadcrumb[0] == "PART ELEVEN - PLANNING AND ZONING CODE"
    assert record.metadata["scraper"] == "amlegal"
    assert record.metadata["amlegal_doc_id"] == "0-0-0-12382"
    assert record.metadata["amlegal_chapter"] == "CHAPTER 1141 Zoning District Map"
    assert record.source_type == "zoning_ordinance"


def test_parse_render_section_skips_reserved():
    deep_link = DeepLinker(client_slug="plaincity", code_slug="plaincity_oh")
    record = parse_render_section(
        load_fixture("amlegal_render_reserved.json"),
        deep_link=deep_link,
        breadcrumb=["PART ELEVEN - PLANNING AND ZONING CODE"],
    )
    assert record is None


def test_effective_date_from_html_picks_passed_date():
    render = parse_render_section_raw("amlegal_render_section.json")
    iso = effective_date_from_html(render["html"])
    assert iso == "2008-02-25"


def test_effective_date_from_html_none_when_absent():
    assert effective_date_from_html("<div>No history here.</div>") is None


def test_currency_to_iso():
    client = parse_render_section_raw("amlegal_client.json")
    info = client["versions"][0]["currency_info"]
    assert currency_to_iso(info) == "2026-03-31"
    assert currency_to_iso("no date in here") is None


def test_deep_linker_urls():
    deep_link = DeepLinker(client_slug="plaincity", code_slug="plaincity_oh")
    assert deep_link.home_url == (
        "https://codelibrary.amlegal.com/codes/plaincity/latest/plaincity_oh"
    )
    assert deep_link("0-0-0-12382") == (
        "https://codelibrary.amlegal.com/codes/plaincity/latest/plaincity_oh/0-0-0-12382"
    )


# -- helpers -----------------------------------------------------------------


def parse_render_section_raw(fixture: str) -> dict:
    import json

    return json.loads(load_fixture(fixture))
