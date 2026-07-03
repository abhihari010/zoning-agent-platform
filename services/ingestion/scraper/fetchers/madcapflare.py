"""MadCap Flare (TriPane HTML5 export) fetcher.

Some jurisdictions publish their zoning ordinance as a MadCap Flare "TriPane"
static HTML5 export on their own domain rather than on a codification platform.
Norfolk, VA is the motivating example: Municode's Code of Ordinances zoning
node (``COCI_ZOOR``) is a stub — Appendix A was repealed by Ord. 47,116
(eff. 3/1/2018) — pointing at ``https://www.norfolkva.gov/norfolkzoningordinance/``.

Layout of a TriPane export (all static files under the site root):

1. **Manifest** — ``GET Data/HelpSystem.xml``; its ``Toc`` attribute names the
   TOC file (``Data/Tocs/{name}.js``).
2. **TOC tree** — the TOC file is ``define({numchunks:N, prefix:'{name}_Chunk',
   chunkstart:[...], tree:{n:[{i,c,n}, ...]}})``.  ``i`` is the TOC entry index;
   the nesting gives each entry's ancestor chain (used for breadcrumbs).
3. **TOC chunks** — ``GET Data/Tocs/{prefix}{k}.js`` for k in 0..N-1, each
   ``define({'/Content/...htm': {i:[...], t:[...], b:[...]}})`` mapping one
   topic file to the TOC entry indexes, display titles, and in-page anchors it
   contains.
4. **Topics** — plain ``GET`` of each ``.htm``; every TOC entry's anchor is an
   ``<a name="...">`` inside the entry's ``<hN>`` heading tag.

**Numbering gotcha**: the in-page ``MadCap:autonum`` values can be stale (the
Norfolk export labels ``1_2_Authority.htm`` as "1.1"); the TOC titles carry the
authoritative section numbers, so refs and headings are always taken from the
TOC, never from the page.

Design: one ``SectionRecord`` per numbered TOC entry ("1.2 Authority",
"1.2.1. General Authority ...").  Entries whose titles carry no leading section
number (cover page, "Article 1. General Provisions" folders, printing
instructions) are structural: they contribute breadcrumbs but never records.

The export lives wherever the city uploads it, so the site root must be given
explicitly (``--site-url``), like eCode360's ``--code-id``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

_TOC_ATTR_RE = re.compile(r'\bToc="([^"]+)"')
_NUMCHUNKS_RE = re.compile(r"\bnumchunks\s*:\s*(\d+)")
_PREFIX_RE = re.compile(r"\bprefix\s*:\s*'([^']*)'")

# One chunk entry: '/Content/....htm':{i:[..],t:[..],b:[..]}
_CHUNK_ENTRY_RE = re.compile(
    r"'(?P<href>[^']+\.html?)'\s*:\s*\{"
    r"i:\[(?P<i>[^\]]*)\],"
    r"t:\[(?P<t>(?:[^\]']|'(?:[^'\\]|\\.)*')*)\],"
    r"b:\[(?P<b>(?:[^\]']|'(?:[^'\\]|\\.)*')*)\]",
    re.DOTALL,
)
_JS_STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")

# Leading section number in a TOC title: "1.2 Authority" -> "1.2",
# "1.2.1. General Authority ..." -> "1.2.1".
_SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")

_HEADING_OPEN_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
_HEADING_TAG_RE = re.compile(r"<h([1-6])[^>]*>.*?</h\1>", re.DOTALL | re.IGNORECASE)

# Every heading is preceded by an in-page breadcrumb paragraph of
# ``<MadCap:xref class="H1_H2_Ref">`` links (whose numbering is the stale
# autonum, not the TOC's) — navigation chrome, not ordinance text.
_P_TAG_RE = re.compile(r"<p\b[^>]*>.*?</p>", re.DOTALL | re.IGNORECASE)


def _strip_breadcrumb_paragraphs(html: str) -> str:
    return _P_TAG_RE.sub(
        lambda match: "" if "H1_H2_Ref" in match.group(0) else match.group(0), html
    )


# ---------------------------------------------------------------------------
# TOC value objects
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TocEntry:
    """One TOC entry: a (possibly anchored) position inside a topic file."""

    index: int
    href: str
    title: str
    anchor: str  # "#_Toc..." or "" when the entry is the topic top


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_help_system(xml: str) -> str:
    """Return the TOC path (e.g. ``Data/Tocs/Name.js``) from HelpSystem.xml."""
    match = _TOC_ATTR_RE.search(xml)
    if not match:
        raise ValueError("HelpSystem.xml has no Toc attribute; not a Flare TriPane export?")
    return match.group(1).lstrip("/")


def parse_toc_meta(toc_js: str) -> tuple[int, str]:
    """Return ``(numchunks, chunk_prefix)`` from the TOC tree file."""
    num_match = _NUMCHUNKS_RE.search(toc_js)
    prefix_match = _PREFIX_RE.search(toc_js)
    if not num_match or not prefix_match:
        raise ValueError("Flare TOC file missing numchunks/prefix.")
    return int(num_match.group(1)), prefix_match.group(1)


def parse_toc_parents(toc_js: str) -> dict[int, int]:
    """Return ``{entry index -> parent entry index}`` from the TOC tree.

    The tree is a JS object literal with bare keys (``tree:{n:[{i:0,c:0,...``);
    quoting the keys makes it JSON.  Breadcrumbs are best-effort: an empty map
    is returned when the tree cannot be parsed.
    """
    start = toc_js.find("tree:")
    if start == -1:
        return {}
    blob = toc_js[start + len("tree:") :]
    # Trim to the balanced {...} object.
    depth = 0
    end = None
    for pos, char in enumerate(blob):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                break
    if end is None:
        return {}
    try:
        tree = json.loads(re.sub(r"([{,])([a-z]+):", r'\1"\2":', blob[:end]))
    except ValueError:
        return {}

    parents: dict[int, int] = {}

    def walk(nodes: list[dict], parent: int | None) -> None:
        for node in nodes:
            index = node.get("i")
            if not isinstance(index, int):
                continue
            if parent is not None:
                parents[index] = parent
            walk(node.get("n") or [], index)

    walk(tree.get("n") or [], None)
    return parents


def parse_toc_chunk(chunk_js: str) -> list[TocEntry]:
    """Flatten a TOC chunk into ordered :class:`TocEntry` items."""
    entries: list[TocEntry] = []
    for match in _CHUNK_ENTRY_RE.finditer(chunk_js):
        href = match.group("href")
        indexes = [int(n) for n in re.findall(r"-?\d+", match.group("i"))]
        titles = [t.replace("\\'", "'") for t in _JS_STRING_RE.findall(match.group("t"))]
        anchors = [a for a in _JS_STRING_RE.findall(match.group("b"))]
        for pos, index in enumerate(indexes):
            title = titles[pos] if pos < len(titles) else ""
            anchor = anchors[pos] if pos < len(anchors) else ""
            entries.append(TocEntry(index=index, href=href, title=title.strip(), anchor=anchor))
    entries.sort(key=lambda entry: entry.index)
    return entries


def section_num_from_title(title: str) -> str | None:
    """``"1.2.1. General Authority ..."`` -> ``"1.2.1"``; ``None`` if unnumbered."""
    match = _SECTION_NUM_RE.match(title or "")
    return match.group(1) if match else None


def split_topic_sections(html: str, entries: list[TocEntry]) -> dict[int, str]:
    """Split one topic page into per-TOC-entry body HTML.

    Each entry's slice runs from its heading (the ``<hN>`` containing its
    ``<a name>`` anchor, or the top of the body for anchorless entries) to the
    next entry's heading.  Returns ``{entry index -> body html}``; entries whose
    anchor is missing from the page are omitted.
    """
    body_start = html.lower().find("<body")
    base = html[body_start:] if body_start != -1 else html

    positions: list[tuple[int, int]] = []  # (char pos, entry index)
    for entry in entries:
        name = entry.anchor.lstrip("#")
        if not name:
            positions.append((0, entry.index))
            continue
        anchor_match = re.search(
            rf"""<a\s+name=["']{re.escape(name)}["']""", base, re.IGNORECASE
        )
        if not anchor_match:
            continue
        # The anchor sits inside its heading tag; back up to the heading open.
        heading_opens = [m.start() for m in _HEADING_OPEN_RE.finditer(base, 0, anchor_match.start())]
        positions.append((heading_opens[-1] if heading_opens else anchor_match.start(), entry.index))

    positions.sort()
    sections: dict[int, str] = {}
    for pos, (start, index) in enumerate(positions):
        end = positions[pos + 1][0] if pos + 1 < len(positions) else len(base)
        sections[index] = base[start:end]
    return sections


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


class MadCapFlareFetcher:
    """Fetch zoning ordinance sections from a MadCap Flare TriPane export."""

    name = "madcapflare"

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        max_sections: int | None = None,
        site_url: str | None = None,
        impersonate: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.max_sections = max_sections
        # The export lives on the city's own domain; there is no search API.
        self.site_url = site_url
        self.impersonate = impersonate

    def fetch(self, *, city: str, state: str) -> FetchResult:
        if not self.site_url:
            raise ValueError(
                "MadCapFlareFetcher requires an explicit site_url "
                "(e.g. 'https://www.norfolkva.gov/norfolkzoningordinance/')."
            )
        base = self.site_url.rstrip("/") + "/"

        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
            impersonate=self.impersonate,
        )

        with PoliteHttpClient(config) as client:
            help_xml = client.get_text(f"{base}Data/HelpSystem.xml", cache_suffix=".helpsystem.xml")
            toc_path = parse_help_system(help_xml)
            toc_js = client.get_text(f"{base}{toc_path}", cache_suffix=".toc.js")
            numchunks, prefix = parse_toc_meta(toc_js)
            parents = parse_toc_parents(toc_js)

            entries: list[TocEntry] = []
            toc_dir = toc_path.rsplit("/", 1)[0]
            for chunk_index in range(numchunks):
                chunk_js = client.get_text(
                    f"{base}{toc_dir}/{prefix}{chunk_index}.js",
                    cache_suffix=f".tocchunk_{chunk_index}.js",
                )
                entries.extend(parse_toc_chunk(chunk_js))
            if not entries:
                raise ValueError(
                    f"Could not parse any TOC entries from the Flare export at {base!r}."
                )

            titles = {entry.index: entry.title for entry in entries}
            by_href: dict[str, list[TocEntry]] = {}
            for entry in entries:
                by_href.setdefault(entry.href, []).append(entry)

            sections: list[SectionRecord] = []
            for href, topic_entries in by_href.items():
                if not any(section_num_from_title(e.title) for e in topic_entries):
                    continue  # cover pages, printing instructions, bare folders
                if self.max_sections is not None and len(sections) >= self.max_sections:
                    break
                topic_url = f"{base}{href.lstrip('/')}"
                page = client.get_text(topic_url, cache_suffix=".topic.html")
                bodies = split_topic_sections(page, topic_entries)
                for entry in topic_entries:
                    if self.max_sections is not None and len(sections) >= self.max_sections:
                        break
                    section_ref = section_num_from_title(entry.title)
                    if not section_ref:
                        continue
                    body_html = _strip_breadcrumb_paragraphs(bodies.get(entry.index, ""))
                    text = clean_html(_HEADING_TAG_RE.sub("", body_html, count=1))
                    if not text.strip():
                        continue
                    breadcrumb: list[str] = []
                    parent = parents.get(entry.index)
                    while parent is not None:
                        crumb = titles.get(parent, "")
                        if crumb:
                            breadcrumb.insert(0, crumb)
                        parent = parents.get(parent)
                    sections.append(
                        SectionRecord(
                            section_ref=section_ref,
                            heading=entry.title,
                            text=text,
                            url=topic_url + entry.anchor,
                            source_type="zoning_ordinance",
                            node_id=f"{entry.href}{entry.anchor}",
                            effective_date=None,
                            breadcrumb=breadcrumb,
                            metadata={
                                "scraper": "madcapflare",
                                "flare_topic": entry.href,
                                "tables_flattened": "<table" in body_html.lower(),
                            },
                        )
                    )

        return FetchResult(
            sections=sections,
            source_home_url=base,
            effective_date=None,
            provenance={
                "fetcher": self.name,
                "site_url": base,
                "retrieved_at": datetime.utcnow().date().isoformat(),
            },
        )
