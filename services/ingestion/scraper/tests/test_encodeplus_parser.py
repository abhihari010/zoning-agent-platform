"""Offline tests for the enCodePlus fetcher.

The parsing helpers are exercised against saved real responses (no live
network).  The fixtures were captured from ``https://online.encodeplus.com``
for the Loudoun County, VA Zoning Ordinance (regs slug ``loudouncounty-va-zo``):

- ``encodeplus_landing.html`` — ``doc-viewer.aspx?secid=1`` (bootstrap TOC).
- ``encodeplus_toc_root.html`` — root ``toc-view.aspx`` expand (chapter folders).
- ``encodeplus_toc_expand_mixed.html`` — Chapter 2 expand (folders + a leaf).
- ``encodeplus_toc_expand_leaves.html`` — a use-category expand (all leaves).
- ``encodeplus_section.html`` — ``doc-view.aspx?ajax=0&secid=4`` (§ 1.01).

The fetch-flow test drives ``EncodePlusFetcher.fetch`` end to end against a
fake HTTP client serving a synthetic three-page mini site.
"""

from __future__ import annotations

import pytest

from services.ingestion.scraper.fetchers import encodeplus
from services.ingestion.scraper.fetchers.encodeplus import (
    DeepLinker,
    EncodePlusFetcher,
    effective_date_from_html,
    parse_section_page,
    parse_toc_children,
    section_ref_from_title,
)

from .conftest import load_fixture

_DEEP_LINK = DeepLinker(regs_slug="loudouncounty-va-zo")


# ---------------------------------------------------------------------------
# TOC parsing
# ---------------------------------------------------------------------------


def test_parse_toc_children_landing_page():
    nodes = parse_toc_children(load_fixture("encodeplus_landing.html"))
    assert len(nodes) == 15
    # First child is the Table of Contents leaf.
    toc = nodes[0]
    assert toc.secid == "1770"
    assert toc.title == "Table of Contents"
    assert toc.is_leaf
    assert toc.expand_key is None
    # Chapters are folders carrying opaque expand keys.
    ch1 = nodes[1]
    assert ch1.secid == "2"
    assert ch1.title == "Chapter 1: Introduction"
    assert not ch1.is_leaf
    assert ch1.expand_key == "001.002"


def test_parse_toc_children_root_expand_matches_landing():
    landing = parse_toc_children(load_fixture("encodeplus_landing.html"))
    root = parse_toc_children(load_fixture("encodeplus_toc_root.html"))
    assert [n.secid for n in root] == [n.secid for n in landing]


def test_parse_toc_children_mixed_expand():
    nodes = parse_toc_children(load_fixture("encodeplus_toc_expand_mixed.html"))
    assert len(nodes) == 7
    folders = [n for n in nodes if not n.is_leaf]
    leaves = [n for n in nodes if n.is_leaf]
    assert len(folders) == 6
    assert len(leaves) == 1
    assert folders[0].title == "2.01 Urban Zoning Districts"
    assert folders[0].expand_key == "001.003.001"
    assert all(n.expand_key is None for n in leaves)


def test_parse_toc_children_leaf_expand():
    nodes = parse_toc_children(load_fixture("encodeplus_toc_expand_leaves.html"))
    assert len(nodes) == 17
    assert all(n.is_leaf for n in nodes)
    assert nodes[0].title == "Telecommunications Facility"


def test_parse_toc_children_without_selected_node_returns_empty():
    assert parse_toc_children("<div id='toc-list'><ul></ul></div>") == []


# ---------------------------------------------------------------------------
# Heading / date helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("7.01.07 Transitions", "7.01.07"),
        ("1.01 Title, Purpose, and Intent", "1.01"),
        ("Appendix C: Airport Impact Overlay District", "Appendix C"),
        ("Article II General Provisions", "Article II"),
        ("Definitions: General Terms", "Definitions"),
        ("", None),
        ("   ", None),
    ],
)
def test_section_ref_from_title(title, expected):
    assert section_ref_from_title(title) == expected


def test_effective_date_ignores_1901_placeholder():
    assert effective_date_from_html("<p>Effective on: 1/1/1901</p>") is None


def test_effective_date_returns_newest_real_date():
    html = "<p>Effective on: 12/13/2023</p><p>Effective on: 6/1/2024</p>"
    assert effective_date_from_html(html) == "2024-06-01"


# ---------------------------------------------------------------------------
# Section page parsing
# ---------------------------------------------------------------------------


def test_parse_section_page_real_fixture():
    record = parse_section_page(
        load_fixture("encodeplus_section.html"),
        deep_link=_DEEP_LINK,
        breadcrumb=["Chapter 1: Introduction"],
        chapter_title="Chapter 1: Introduction",
    )
    assert record is not None
    assert record.section_ref == "1.01"
    assert record.heading == "1.01 Title, Purpose, and Intent"
    assert record.node_id == "4"
    assert record.url == (
        "https://online.encodeplus.com/regs/loudouncounty-va-zo/"
        "doc-viewer.aspx?secid=4"
    )
    assert record.breadcrumb == ["Chapter 1: Introduction"]
    assert record.source_type == "zoning_ordinance"
    # The 1/1/1901 archive-notice placeholder must not become a date.
    assert record.effective_date is None
    assert "Loudoun County Zoning Ordinance" in record.text
    # The heading must not be duplicated into the body text.
    assert not record.text.startswith("1.01")
    assert record.metadata["scraper"] == "encodeplus"
    assert record.metadata["encodeplus_secid"] == "4"
    assert record.metadata["encodeplus_chapter"] == "Chapter 1: Introduction"


def test_parse_section_page_uses_fallback_effective_date():
    record = parse_section_page(
        load_fixture("encodeplus_section.html"),
        deep_link=_DEEP_LINK,
        breadcrumb=[],
        fallback_effective_date="2023-12-13",
    )
    assert record is not None
    assert record.effective_date == "2023-12-13"


def test_parse_section_page_returns_none_without_section_markup():
    assert (
        parse_section_page(
            "<html><body><p>404</p></body></html>",
            deep_link=_DEEP_LINK,
            breadcrumb=[],
        )
        is None
    )


def test_parse_section_page_definition_leaf_uses_fallback_title():
    # Glossary/definition leaves (e.g. Loudoun's defined terms) have no heading
    # tag — just a def paragraph; the TOC leaf title supplies the heading.
    html = (
        "<section class='doc-section' data-secid='565'>"
        "<p><strong class=\"def\">Sign:</strong> Any visual display that "
        "comprises letters, words, or symbols.</p></section>"
    )
    record = parse_section_page(
        html,
        deep_link=_DEEP_LINK,
        breadcrumb=["Chapter 9: Definitions"],
        fallback_title="Sign",
    )
    assert record is not None
    assert record.section_ref == "Sign"
    assert record.heading == "Sign"
    assert record.node_id == "565"
    assert "visual display" in record.text


def test_parse_section_page_without_heading_or_fallback_returns_none():
    html = "<section data-secid='1'><p>orphan text</p></section>"
    assert parse_section_page(html, deep_link=_DEEP_LINK, breadcrumb=[]) is None


def test_parse_section_page_skips_table_of_contents_leaf():
    html = (
        "<section data-secid='1770'><h3>Table of Contents</h3>"
        "<p>scaffolding</p></section>"
    )
    assert parse_section_page(html, deep_link=_DEEP_LINK, breadcrumb=[]) is None


def test_deep_linker_urls():
    assert _DEEP_LINK.home_url == (
        "https://online.encodeplus.com/regs/loudouncounty-va-zo/doc-viewer.aspx"
    )
    assert _DEEP_LINK("42").endswith("doc-viewer.aspx?secid=42")


# ---------------------------------------------------------------------------
# Fetch flow with a mocked HTTP layer
# ---------------------------------------------------------------------------

_FAKE_LANDING = """
<div id="toc-list">
<li id="secid-x1" class="tocLink selected"><span class="toc-item">Fake Ordinance</span></li>
<li><ul class='toc-level1' >
<li id="secid-x10"><i class="fa fa-file-text-o isLeaf"></i>
  <span class="toc-item">Table of Contents</span></li>
<li id="secid-x20"><a href="#" onclick="ZP.TOCView.Expand('001.002'); return false;"></a>
  <span class="toc-item">Chapter 1: General</span></li>
</ul></li>
</div>
"""

_FAKE_EXPAND = """
<div id="toc-list">
<li id="secid-x20" class="tocLink selected"><span class="toc-item">Chapter 1: General</span></li>
<li><ul class='toc-level2' >
<li id="secid-x21"><i class="fa fa-file-text-o isLeaf"></i>
  <span class="toc-item">1.01 Purpose</span></li>
<li id="secid-x22"><i class="fa fa-file-text-o isLeaf"></i>
  <span class="toc-item">1.02 Applicability</span></li>
</ul></li>
</div>
"""


def _fake_section(secid: str, title: str) -> str:
    return (
        f"<section class='doc-section' data-secid='{secid}'>"
        f"<h3>{title}</h3><p>Body text for {title}.</p>"
        "<p class='archiveNotice nullValue'>Effective on: 1/1/1901</p>"
        "</section>"
    )


class _FakeClient:
    """Stands in for PoliteHttpClient; serves canned pages by URL."""

    calls: list[str] = []

    def __init__(self, config):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_text(self, url: str, cache_suffix: str = "") -> str:
        type(self).calls.append(url)
        if "doc-viewer.aspx?secid=1" in url:
            return _FAKE_LANDING
        if "toc-view.aspx?tocid=001.002" in url:
            return _FAKE_EXPAND
        if "doc-view.aspx?ajax=0&secid=21" in url:
            return _fake_section("21", "1.01 Purpose")
        if "doc-view.aspx?ajax=0&secid=22" in url:
            return _fake_section("22", "1.02 Applicability")
        raise AssertionError(f"unexpected URL fetched: {url}")


def test_fetch_walks_tree_and_skips_scaffolding(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr(encodeplus, "PoliteHttpClient", _FakeClient)
    fetcher = EncodePlusFetcher(regs_slug="fake-va-zo")
    result = fetcher.fetch(city="Fake", state="VA")

    assert [s.section_ref for s in result.sections] == ["1.01", "1.02"]
    assert [s.node_id for s in result.sections] == ["21", "22"]
    assert result.sections[0].breadcrumb == ["Chapter 1: General"]
    assert result.sections[0].metadata["encodeplus_chapter"] == "Chapter 1: General"
    assert result.source_home_url == (
        "https://online.encodeplus.com/regs/fake-va-zo/doc-viewer.aspx"
    )
    assert result.provenance["fetcher"] == "encodeplus"
    assert result.provenance["regs_slug"] == "fake-va-zo"
    # The Table of Contents leaf (secid 10) must never be fetched.
    assert not any("secid=10" in url for url in _FakeClient.calls)


def test_fetch_respects_max_sections(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr(encodeplus, "PoliteHttpClient", _FakeClient)
    fetcher = EncodePlusFetcher(regs_slug="fake-va-zo", max_sections=1)
    result = fetcher.fetch(city="Fake", state="VA")
    assert [s.section_ref for s in result.sections] == ["1.01"]


def test_fetch_without_regs_slug_raises():
    with pytest.raises(ValueError, match="regs_slug"):
        EncodePlusFetcher().fetch(city="Loudoun County", state="VA")


def test_fetch_with_unparseable_toc_raises(monkeypatch):
    class _EmptyClient(_FakeClient):
        def get_text(self, url: str, cache_suffix: str = "") -> str:
            return "<html><body>maintenance page</body></html>"

    monkeypatch.setattr(encodeplus, "PoliteHttpClient", _EmptyClient)
    fetcher = EncodePlusFetcher(regs_slug="fake-va-zo")
    with pytest.raises(ValueError, match="table of contents"):
        fetcher.fetch(city="Fake", state="VA")
