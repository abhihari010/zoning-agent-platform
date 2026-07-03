"""Offline tests for the MadCap Flare (TriPane export) fetcher.

Parsing helpers run against saved real responses (no live network).  The
fixtures were captured from ``https://www.norfolkva.gov/norfolkzoningordinance/``
(the official online Norfolk, VA Zoning Ordinance):

- ``madcapflare_helpsystem.xml`` — ``Data/HelpSystem.xml`` manifest.
- ``madcapflare_toc.js`` — the TOC tree file.
- ``madcapflare_tocchunk0.js`` — the TOC chunk (entry index -> title/anchor).
- ``madcapflare_topic_authority.htm`` — the ``1.2 Authority`` topic page.

The fetch-flow test drives ``MadCapFlareFetcher.fetch`` end to end against a
fake HTTP client serving a synthetic mini export.
"""

from __future__ import annotations

import pytest

from services.ingestion.scraper.fetchers import madcapflare
from services.ingestion.scraper.fetchers.madcapflare import (
    MadCapFlareFetcher,
    parse_help_system,
    parse_toc_chunk,
    parse_toc_meta,
    parse_toc_parents,
    section_num_from_title,
    split_topic_sections,
)

from .conftest import load_fixture


# ---------------------------------------------------------------------------
# TOC parsing
# ---------------------------------------------------------------------------


def test_parse_help_system_returns_toc_path():
    toc = parse_help_system(load_fixture("madcapflare_helpsystem.xml"))
    assert toc == "Data/Tocs/MASTER___Norfolk_Public_Hearing_Draft___REV_1_3_18.js"


def test_parse_help_system_rejects_non_flare_page():
    with pytest.raises(ValueError, match="Toc"):
        parse_help_system("<html><body>not a flare site</body></html>")


def test_parse_toc_meta():
    numchunks, prefix = parse_toc_meta(load_fixture("madcapflare_toc.js"))
    assert numchunks == 1
    assert prefix == "MASTER___Norfolk_Public_Hearing_Draft___REV_1_3_18_Chunk"


def test_parse_toc_parents_nesting():
    parents = parse_toc_parents(load_fixture("madcapflare_toc.js"))
    # 1.2 Authority (i=4) sits under Article 1 (i=2); its subsections under it.
    assert parents[4] == 2
    assert parents[5] == 4
    assert parents[6] == 4
    assert len(parents) > 300


def test_parse_toc_parents_is_best_effort():
    assert parse_toc_parents("define({numchunks:1});") == {}


def test_parse_toc_chunk_maps_entries_to_topics():
    entries = parse_toc_chunk(load_fixture("madcapflare_tocchunk0.js"))
    assert len(entries) == 403
    by_index = {entry.index: entry for entry in entries}
    authority = by_index[4]
    assert authority.title == "1.2 Authority"
    assert authority.href == "/Content/Norfolk-ZO/1_2_Authority.htm"
    assert authority.anchor == "#_Toc502655566"
    # Subsections of the same topic share the href but carry their own anchors.
    sub = by_index[5]
    assert sub.title.startswith("1.2.1.")
    assert sub.href == authority.href
    assert sub.anchor != authority.anchor


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("1.2 Authority", "1.2"),
        ("1.2.1. General Authority to Adopt Zoning Ordinance", "1.2.1"),
        ("5.10.12. Some Standard", "5.10.12"),
        ("Article 1. General Provisions", None),
        ("Commercial Uses", None),
        ("Printing_Instructions", None),
        ("", None),
    ],
)
def test_section_num_from_title(title, expected):
    assert section_num_from_title(title) == expected


# ---------------------------------------------------------------------------
# Topic splitting
# ---------------------------------------------------------------------------


def test_split_topic_sections_real_topic():
    entries = [
        e
        for e in parse_toc_chunk(load_fixture("madcapflare_tocchunk0.js"))
        if e.href == "/Content/Norfolk-ZO/1_2_Authority.htm"
    ]
    bodies = split_topic_sections(load_fixture("madcapflare_topic_authority.htm"), entries)
    assert set(bodies) == {4, 5, 6}
    # The 1.2.1 slice holds its own text, not its siblings'.
    assert "Code of Virginia" in bodies[5]
    assert "1.2.2" not in bodies[5]
    # Slices cover distinct, ordered regions.
    assert len(bodies[5]) > len(bodies[4])


def test_split_topic_sections_skips_missing_anchor():
    entries = parse_toc_chunk(load_fixture("madcapflare_tocchunk0.js"))
    authority = [e for e in entries if e.href == "/Content/Norfolk-ZO/1_2_Authority.htm"]
    bodies = split_topic_sections("<html><body><p>rebuilt page</p></body></html>", authority)
    assert bodies == {}


# ---------------------------------------------------------------------------
# Fetch flow with a mocked HTTP layer
# ---------------------------------------------------------------------------

_FAKE_HELPSYSTEM = '<WebHelpSystem Toc="Data/Tocs/Fake.js" />'
_FAKE_TOC = (
    "define({numchunks:1,prefix:'Fake_Chunk',chunkstart:['/Content/1_1.htm'],"
    "tree:{n:[{i:0,c:0,n:[{i:1,c:0,n:[{i:2,c:0}]}]}]}});"
)
_FAKE_CHUNK = (
    "define({'/Content/Article_1.htm':{i:[0],t:['Article 1. General Provisions'],b:['']},"
    "'/Content/1_1.htm':{i:[1,2],t:['1.1 Title','1.1.1. Short Title'],"
    "b:['#a1','#a2']}});"
)
_FAKE_TOPIC = (
    "<html><body>"
    '<p><MadCap:xref href="1_1.htm" class="H1_H2_Ref">Article 1</MadCap:xref></p>'
    "<h2><a name='a1'></a>Title</h2><p>This ordinance is titled the Fake Zoning Ordinance.</p>"
    '<p><MadCap:xref href="1_1.htm" class="H1_H2_Ref">Article 1</MadCap:xref> &gt; Short Title</p>'
    "<h3><a name='a2'></a>Short Title</h3><p>Cite it as the FZO.</p>"
    "</body></html>"
)


class _FakeClient:
    def __init__(self, config):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_text(self, url: str, cache_suffix: str = "") -> str:
        if url.endswith("Data/HelpSystem.xml"):
            return _FAKE_HELPSYSTEM
        if url.endswith("Data/Tocs/Fake.js"):
            return _FAKE_TOC
        if url.endswith("Data/Tocs/Fake_Chunk0.js"):
            return _FAKE_CHUNK
        if url.endswith("Content/1_1.htm"):
            return _FAKE_TOPIC
        raise AssertionError(f"unexpected URL fetched: {url}")


def test_fetch_builds_records_from_toc_titles(monkeypatch):
    monkeypatch.setattr(madcapflare, "PoliteHttpClient", _FakeClient)
    fetcher = MadCapFlareFetcher(site_url="https://example.gov/zo/")
    result = fetcher.fetch(city="Fake", state="VA")

    assert [r.section_ref for r in result.sections] == ["1.1", "1.1.1"]
    title, short_title = result.sections
    assert title.heading == "1.1 Title"
    assert title.url == "https://example.gov/zo/Content/1_1.htm#a1"
    assert "Fake Zoning Ordinance" in title.text
    # Body slices end where the next entry starts.
    assert "FZO" not in title.text
    assert "FZO" in short_title.text
    # In-page breadcrumb chrome (stale-numbered xref paragraphs) is stripped.
    assert "Article 1" not in title.text
    # Breadcrumbs come from the TOC tree; the subsection sits under 1.1.
    assert short_title.breadcrumb == ["Article 1. General Provisions", "1.1 Title"]
    assert result.provenance["fetcher"] == "madcapflare"
    assert result.source_home_url == "https://example.gov/zo/"


def test_fetch_respects_max_sections(monkeypatch):
    monkeypatch.setattr(madcapflare, "PoliteHttpClient", _FakeClient)
    fetcher = MadCapFlareFetcher(site_url="https://example.gov/zo/", max_sections=1)
    result = fetcher.fetch(city="Fake", state="VA")
    assert [r.section_ref for r in result.sections] == ["1.1"]


def test_fetch_without_site_url_raises():
    with pytest.raises(ValueError, match="site_url"):
        MadCapFlareFetcher().fetch(city="Norfolk", state="VA")


def test_fetch_with_empty_toc_raises(monkeypatch):
    class _EmptyClient(_FakeClient):
        def get_text(self, url: str, cache_suffix: str = "") -> str:
            if url.endswith("Data/HelpSystem.xml"):
                return _FAKE_HELPSYSTEM
            if url.endswith("Data/Tocs/Fake.js"):
                return _FAKE_TOC
            return "define({});"

    monkeypatch.setattr(madcapflare, "PoliteHttpClient", _EmptyClient)
    fetcher = MadCapFlareFetcher(site_url="https://example.gov/zo/")
    with pytest.raises(ValueError, match="TOC entries"):
        fetcher.fetch(city="Fake", state="VA")
