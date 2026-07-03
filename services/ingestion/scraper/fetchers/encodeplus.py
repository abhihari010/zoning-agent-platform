"""enCodePlus fetcher.

enCodePlus (``online.encodeplus.com``) hosts interactive zoning ordinances for a
number of US jurisdictions (Loudoun County, VA is the motivating example).  A
regulation is served under ``/regs/{regs_slug}/`` — e.g.
``online.encodeplus.com/regs/loudouncounty-va-zo/`` — as a server-rendered
ASP.NET "document viewer" (no JSON API; the client is jQuery + partial-HTML
endpoints).  The endpoints were discovered by inspecting the viewer's JS
(``js/toc-view.js`` / ``js/doc-view.js``) and the live traffic.

Endpoints used (all relative to ``https://online.encodeplus.com/regs/{regs_slug}/``):

1. **Landing / bootstrap TOC**
   ``GET doc-viewer.aspx`` (or ``?secid=1``) — the full viewer page.  Its
   ``#toc-list`` embeds the top-level table of contents: the root ordinance node
   (``class="tocLink selected"``) followed by a ``<ul class='toc-level1'>`` of its
   direct children (chapters / appendices).  Each ``<li>`` carries the section id
   (``id="secid-x{N}"``), the display title (``<span class="toc-item">``), whether
   it is a leaf (``isLeaf`` on the file icon), and — for folders — an opaque
   expand key in ``onclick="ZP.TOCView.Expand('{key}')"``.

2. **Expand a folder**
   ``GET toc-view.aspx?tocid={key}&task=expand`` — returns the same ``#toc-list``
   markup re-rooted so the requested folder is ``selected`` and its direct
   children follow in a ``<ul class='toc-levelN'>``.  Walked recursively to the
   leaf sections.

3. **Section content**
   ``GET doc-view.aspx?ajax=0&secid={secid}`` — server-rendered HTML for one
   section: a ``<section ... data-secid='{secid}'>`` whose ``<h4>`` is the heading
   (with category-icon spans we strip) and whose remaining body is the ordinance
   text.  A trailing ``<p class='archiveNotice nullValue'>Effective on: …</p>``
   placeholder is ignored.

**Deep-link URL** for a section on the public site::

    https://online.encodeplus.com/regs/{regs_slug}/doc-viewer.aspx?secid={secid}

enCodePlus does NOT expose a city→slug search endpoint, so the regs slug must be
supplied explicitly (``--regs-slug``), mirroring eCode360's ``--code-id``.

Design: one ``SectionRecord`` per leaf section, mirroring the other fetchers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

SITE_BASE = "https://online.encodeplus.com"

# Leaf titles that are navigation/scaffolding rather than ordinance content.
_SKIP_TITLES = {"table of contents"}

# Leading section reference in a heading: "7.01.07", "1.01", "2.02.05.01",
# or an "Appendix C" / "Article II" style label.
_SECTION_REF_RE = re.compile(
    r"^\s*((?:appendix|article|chapter)\s+[0-9a-z]+|[0-9]+(?:\.[0-9]+)*)",
    re.IGNORECASE,
)

# A real "Effective on: M/D/YYYY" note (the viewer emits a 1/1/1901 placeholder
# with a nullValue class, which we ignore).
_EFFECTIVE_RE = re.compile(
    r"Effective on:\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE
)

# One TOC list item.  We split the list on these and parse each part.
_LI_ID_RE = re.compile(r'<li id="secid-x(-?\d+)"')
_TOC_ITEM_RE = re.compile(r'<span class="toc-item">(.*?)</span>', re.DOTALL)
_EXPAND_KEY_RE = re.compile(r"ZP\.TOCView\.Expand\('([\d.]+)'\)")

# A single content section block.
_SECTION_RE = re.compile(
    r"<section\b[^>]*\bdata-secid='(\d+)'[^>]*>(.*?)</section>",
    re.DOTALL | re.IGNORECASE,
)
# Section heading: the first heading tag in the section body.  The viewer JS
# renders <h4>, but the server-rendered ajax=0 pages emit <h3>.
_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
# Category-icon container inside the heading — strip it before reading text.
_CATICON_RE = re.compile(
    r"<span\s+class='caticon-ctnr'.*?</span>\s*</span>",
    re.DOTALL | re.IGNORECASE,
)
_ARCHIVE_NOTICE_RE = re.compile(
    r"<p[^>]*class=['\"][^'\"]*archiveNotice[^'\"]*['\"][^>]*>.*?</p>",
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# TOC node value object
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TocNode:
    secid: str
    title: str
    is_leaf: bool
    expand_key: str | None = None


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_toc_children(toc_html: str) -> list[TocNode]:
    """Return the direct children of the ``selected`` node in a TOC fragment.

    Works on both the full landing page and a ``toc-view.aspx`` expand fragment:
    each embeds the selected node followed by a ``<ul class='toc-levelN'>`` of its
    immediate children.
    """
    sel_idx = toc_html.find('class="tocLink selected"')
    if sel_idx == -1:
        return []
    tail = toc_html[sel_idx:]
    ul_match = re.search(r"<li><ul class='toc-level\d+' >(.*?)</ul>", tail, re.DOTALL)
    if not ul_match:
        return []
    block = ul_match.group(1)

    nodes: list[TocNode] = []
    parts = re.split(r'(?=<li id="secid-x)', block)
    for part in parts:
        id_match = _LI_ID_RE.match(part)
        if not id_match:
            continue
        secid = id_match.group(1)
        # Anything before the first </li> is this node's own markup (its children,
        # if any, live in a following sibling <ul> that we skip here).
        head = part.split("</li>", 1)[0]
        is_leaf = "isLeaf" in head
        title_match = _TOC_ITEM_RE.search(part)
        title = _clean_text(title_match.group(1)) if title_match else ""
        expand_match = _EXPAND_KEY_RE.search(head)
        expand_key = expand_match.group(1) if expand_match else None
        nodes.append(
            TocNode(
                secid=secid,
                title=title,
                is_leaf=is_leaf,
                expand_key=expand_key,
            )
        )
    return nodes


def section_ref_from_title(title: str) -> str | None:
    """``"7.01.07 Transitions"`` -> ``"7.01.07"``; ``"Appendix C: …"`` -> ``"Appendix C"``.

    Falls back to the title up to the first colon (trimmed) when no structured
    reference is present, so every substantive section still gets a non-empty ref.
    """
    title = (title or "").strip()
    if not title:
        return None
    match = _SECTION_REF_RE.match(title)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    fallback = title.split(":", 1)[0].strip()
    return fallback[:80] or None


def effective_date_from_html(html: str) -> str | None:
    """Return the newest real ``Effective on: M/D/YYYY`` date, ignoring the
    1901 placeholder the viewer emits for un-dated sections."""
    dates: list[str] = []
    for mo, da, yr in _EFFECTIVE_RE.findall(html):
        year = int(yr)
        if year <= 1901:
            continue
        iso = _safe_iso(year, int(mo), int(da))
        if iso:
            dates.append(iso)
    return max(dates) if dates else None


def parse_section_page(
    html: str,
    *,
    deep_link: "DeepLinker",
    breadcrumb: list[str],
    chapter_title: str = "",
    fallback_effective_date: str | None = None,
) -> SectionRecord | None:
    """Build one SectionRecord from a ``doc-view.aspx`` section page.

    Returns ``None`` for empty/scaffolding sections.
    """
    section_match = _SECTION_RE.search(html)
    if not section_match:
        return None
    secid = section_match.group(1)
    inner = section_match.group(2)

    heading_match = _HEADING_RE.search(inner)
    if not heading_match:
        return None
    heading = _clean_text(_CATICON_RE.sub("", heading_match.group(2)))
    if not heading:
        return None
    if heading.strip().lower() in _SKIP_TITLES:
        return None

    section_ref = section_ref_from_title(heading)
    if not section_ref:
        return None

    # Body = the section minus its heading and the archive-notice footer.
    body_html = _HEADING_RE.sub("", inner, count=1)
    body_html = _ARCHIVE_NOTICE_RE.sub("", body_html)
    text = clean_html(body_html)
    if not text.strip():
        return None

    effective = effective_date_from_html(inner) or fallback_effective_date

    return SectionRecord(
        section_ref=section_ref,
        heading=heading,
        text=text,
        url=deep_link(secid),
        source_type="zoning_ordinance",
        node_id=secid,
        effective_date=effective,
        breadcrumb=list(breadcrumb),
        metadata={
            "scraper": "encodeplus",
            "encodeplus_secid": secid,
            "encodeplus_chapter": chapter_title,
            "tables_flattened": "<table" in inner.lower(),
        },
    )


# ---------------------------------------------------------------------------
# Deep-link builder
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepLinker:
    regs_slug: str

    @property
    def home_url(self) -> str:
        return f"{SITE_BASE}/regs/{self.regs_slug}/doc-viewer.aspx"

    def __call__(self, secid: str) -> str:
        return f"{self.home_url}?secid={secid}"


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


class EncodePlusFetcher:
    """Fetch zoning ordinance sections from an enCodePlus regulation."""

    name = "encodeplus"

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        max_sections: int | None = None,
        regs_slug: str | None = None,
        impersonate: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.max_sections = max_sections
        # enCodePlus has no city->slug search; the regs slug is required.
        self.regs_slug = regs_slug
        self.impersonate = impersonate

    def fetch(self, *, city: str, state: str) -> FetchResult:
        if not self.regs_slug:
            raise ValueError(
                "EncodePlusFetcher requires an explicit regs_slug "
                "(e.g. 'loudouncounty-va-zo'); enCodePlus has no city search API."
            )
        regs_slug = self.regs_slug
        deep_link = DeepLinker(regs_slug=regs_slug)
        base = f"{SITE_BASE}/regs/{regs_slug}/"

        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
            impersonate=self.impersonate,
        )

        with PoliteHttpClient(config) as client:
            self._client = client
            self._base = base

            # 1. Bootstrap the top-level TOC from the landing page.
            landing = client.get_text(
                f"{base}doc-viewer.aspx?secid=1",
                cache_suffix=f".landing_{regs_slug}.html",
            )
            top = parse_toc_children(landing)
            if not top:
                raise ValueError(
                    "Could not parse the enCodePlus table of contents for "
                    f"{regs_slug!r}. Check the regs slug."
                )

            # 2. Walk the tree collecting leaf secids grouped by chapter.
            leaves = self._collect_leaves(top)

            # 3. Fetch + parse each leaf section.
            sections: list[SectionRecord] = []
            for secid, title, breadcrumb, chapter in leaves:
                if self.max_sections is not None and len(sections) >= self.max_sections:
                    break
                if title.strip().lower() in _SKIP_TITLES:
                    continue
                page = client.get_text(
                    f"{base}doc-view.aspx?ajax=0&secid={secid}",
                    cache_suffix=f".sec_{secid}.html",
                )
                record = parse_section_page(
                    page,
                    deep_link=deep_link,
                    breadcrumb=breadcrumb,
                    chapter_title=chapter,
                )
                if record is not None:
                    sections.append(record)

        return FetchResult(
            sections=sections,
            source_home_url=deep_link.home_url,
            effective_date=None,
            provenance={
                "fetcher": self.name,
                "regs_slug": regs_slug,
                "retrieved_at": datetime.utcnow().date().isoformat(),
            },
        )

    # -- tree walk --------------------------------------------------------

    def _expand(self, key: str) -> list[TocNode]:
        html = self._client.get_text(
            f"{self._base}toc-view.aspx?tocid={key}&task=expand",
            cache_suffix=f".toc_{key}.html",
        )
        return parse_toc_children(html)

    def _collect_leaves(
        self, top: list[TocNode]
    ) -> list[tuple[str, str, list[str], str]]:
        """Return ``(secid, title, breadcrumb, chapter_title)`` for every leaf."""
        out: list[tuple[str, str, list[str], str]] = []
        seen_keys: set[str] = set()
        seen_secids: set[str] = set()

        def walk(nodes: list[TocNode], breadcrumb: list[str], chapter: str) -> None:
            for node in nodes:
                if node.is_leaf:
                    if node.secid in seen_secids:
                        continue
                    seen_secids.add(node.secid)
                    out.append((node.secid, node.title, breadcrumb, chapter))
                    continue
                key = node.expand_key
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                children = self._expand(key)
                # The first breadcrumb level is the chapter.
                next_chapter = chapter or node.title
                walk(children, [*breadcrumb, node.title], next_chapter)

        # Top-level children are chapters; each sets the chapter context.
        for node in top:
            if node.is_leaf:
                if node.secid not in seen_secids:
                    seen_secids.add(node.secid)
                    out.append((node.secid, node.title, [], node.title))
                continue
            key = node.expand_key
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            children = self._expand(key)
            walk(children, [node.title], node.title)
        return out


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------


def _clean_text(html: str) -> str:
    """Strip tags + decode entities from a small inline HTML fragment."""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None
