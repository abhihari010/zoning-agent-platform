"""Municipal Code Online fetcher.

Montgomery County, VA (and many other small jurisdictions) publish their code of
ordinances on **Municipal Code Online** (``municipalcodeonline.com``) — a
different vendor from Municode (``library.municode.com``).  The Montgomery code
is NOT on Municode (that product is an empty stub), so this fetcher targets the
Municipal Code Online SPA's backing endpoints, discovered by inspecting the
page's Kendo TreeView traffic (see ``../README.md`` for the investigation log).

Endpoints (all under ``https://{slug}.municipalcodeonline.com``):

1. ``GET /book/expand?type=ordinances`` -> the top-level chapter list as JSON
   ``[{"id": "10_ZONING", "name": "10 ZONING", "hasChildren": true}, ...]``.
2. ``GET /book/expand?type=ordinances&id={nodeId}`` -> the children of a tree
   node (walked recursively: Chapter -> Article -> Division -> Section).
3. ``GET /book/content?type=ordinances&name={nodeId}&highlightTerm=&editing=false
   &printing=false&bookDataId=&_={epoch_ms}`` -> ``{"Text": "<html>", "Success":
   true}``.  For a *leaf* (a ``Sec ...`` node) ``Text`` is that section's body
   HTML; for a chapter/article node ``Text`` is a table-of-contents stub.

**The auth guard (the hard part).**  A plain ``httpx.get`` of ``/book/content``
returns HTTP 500 with an ``Unauthorized Access`` ASP.NET error page, even with a
full browser User-Agent, ``Referer``, ``X-Requested-With``, ``Accept``, HTTP/2,
and a warmed cookie jar.  A bare in-page ``XMLHttpRequest`` (same origin, same
session) *also* 500s, yet the site's own jQuery ``$.ajax`` succeeds.  The vendor
installs a global ``$.ajaxSetup`` that adds a custom header **``x-csrf: 1``**;
the server requires **both** ``x-csrf: 1`` *and* ``X-Requested-With:
XMLHttpRequest`` to be present (neither alone is sufficient).  Sending those two
headers makes pure ``httpx`` return 200 — no browser or cookie needed.

Design: we emit **one SectionRecord per leaf ``Sec ...`` node**, mirroring the
Municode fetcher.  The zoning chapter is found data-drivenly by heading text
(``"zoning"``), never by a hard-coded id.  Reserved placeholder sections are
skipped.  Tables in the body flatten to text (acceptable; noted in metadata).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

# Default subdomain slug for a jurisdiction is ``{first_word_of_city_lower}``.
# Montgomery County -> "montgomery".  Override via ``host_slug`` if needed.
TYPE = "ordinances"

# Headings that identify the zoning chapter, case-insensitive.
_ZONING_HEADING_HINTS = ("zoning",)
# Never treat these as the zoning chapter even if they contain a hint.
_ZONING_HEADING_EXCLUDE = ("subdivision",)

# Leaf section heading: "Sec 10-24 R-1 Residential District" -> "Sec. 10-24".
# Also matches "Sec. 10-32.1 ..." and reserved ranges "Secs 10-9 - 10-20 ...".
_SECTION_REF_RE = re.compile(
    r"^\s*(Secs?\.?\s*[0-9][0-9A-Za-z.\-]*)", re.IGNORECASE
)
_RESERVED_RE = re.compile(r"\[?\s*reserved\s*\]?", re.IGNORECASE)

# Amendment/adoption dates embedded in HISTORY notes, e.g. "on 9/28/2020" or
# "adopted Dec. 13, 1999" or "12-13-99".
_HISTORY_MDY_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_HISTORY_LONG_RE = re.compile(
    r"\b([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(\d{4})\b"
)


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_expand(expand_json: str | list) -> list[dict[str, Any]]:
    """Normalize a ``/book/expand`` JSON array into ``{id, name, has_children}``."""
    payload = json.loads(expand_json) if isinstance(expand_json, str) else expand_json
    if not isinstance(payload, list):
        raise ValueError("Municipal Code Online expand response must be a JSON array.")
    out: list[dict[str, Any]] = []
    for node in payload:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        name = str(node.get("name") or "")
        if not node_id:
            continue
        out.append(
            {
                "id": node_id,
                "name": name,
                "has_children": bool(node.get("hasChildren")),
            }
        )
    return out


def find_zoning_node(root_expand_json: str | list) -> dict[str, Any]:
    """Return ``{id, name, has_children}`` for the zoning chapter node."""
    nodes = parse_expand(root_expand_json)
    candidates = []
    for node in nodes:
        lowered = node["name"].lower()
        if any(bad in lowered for bad in _ZONING_HEADING_EXCLUDE):
            continue
        if any(hint in lowered for hint in _ZONING_HEADING_HINTS):
            candidates.append(node)
    if not candidates:
        raise ValueError("Could not locate a zoning chapter in the Municipal Code Online tree.")
    # Prefer a node whose id starts with a chapter number + ZONING.
    candidates.sort(key=lambda n: (("zoning" not in n["id"].lower()), n["name"]))
    return candidates[0]


def parse_content_payload(content_json: str | dict) -> str:
    """Return the inner ``Text`` HTML from a ``/book/content`` JSON response."""
    payload = json.loads(content_json) if isinstance(content_json, str) else content_json
    if not isinstance(payload, dict):
        raise ValueError("Municipal Code Online content response must be a JSON object.")
    if not payload.get("Success", True):
        return ""
    return str(payload.get("Text") or "")


def section_ref_from_name(name: str) -> str | None:
    """``"Sec 10-24 R-1 Residential District"`` -> ``"Sec. 10-24"`` (None if no ref)."""
    match = _SECTION_REF_RE.match(name)
    if not match:
        return None
    ref = re.sub(r"\s+", " ", match.group(1)).strip()
    # Normalize "Sec 10-24" -> "Sec. 10-24"; "Secs 10-9" -> "Secs. 10-9".
    ref = re.sub(r"^Sec(s?)(?!\.)", r"Sec\1.", ref, flags=re.IGNORECASE)
    return ref


def _strip_heading_div(html: str) -> str:
    """Remove the leading ``phx-name`` heading anchor div from a section body so
    the heading text is not duplicated inside ``full_text``."""
    # The body starts with <div><div class='phx-name '><a ...>Heading</a></div></div>.
    return re.sub(
        r"^\s*<div>\s*<div class='phx-name[^>]*'>.*?</div>\s*</div>",
        "",
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def effective_date_from_history(html: str) -> str | None:
    """Pull the most recent amendment/adoption date from a section's HISTORY note.

    Returns an ISO date string (``YYYY-MM-DD``) or ``None``.  Scans for both
    ``M/D/YYYY`` and ``Mon D, YYYY`` style dates and returns the latest.
    """
    dates: list[str] = []
    for mo, da, yr in _HISTORY_MDY_RE.findall(html):
        iso = _safe_iso(int(yr), int(mo), int(da))
        if iso:
            dates.append(iso)
    for mon, da, yr in _HISTORY_LONG_RE.findall(html):
        month = _month_number(mon)
        if month:
            iso = _safe_iso(int(yr), month, int(da))
            if iso:
                dates.append(iso)
    return max(dates) if dates else None


def parse_section(
    *,
    node: dict[str, Any],
    content_html: str,
    deep_link: "DeepLinker",
    breadcrumb: list[str],
    chapter_name: str,
    fallback_effective_date: str | None = None,
) -> SectionRecord | None:
    """Build one SectionRecord from a leaf node + its content HTML.

    Returns ``None`` for reserved/structural/empty sections.
    """
    name = node["name"].strip()
    section_ref = section_ref_from_name(name)
    if not section_ref:
        return None
    if _RESERVED_RE.search(name):
        return None

    body_html = _strip_heading_div(content_html)
    text = clean_html(body_html)
    if not text.strip():
        return None

    effective = effective_date_from_history(content_html) or fallback_effective_date

    return SectionRecord(
        section_ref=section_ref,
        heading=name,
        text=text,
        url=deep_link(node["id"]),
        source_type="zoning_ordinance",
        node_id=node["id"],
        effective_date=effective,
        breadcrumb=list(breadcrumb),
        metadata={
            "scraper": "municipalcodeonline",
            "mco_node_id": node["id"],
            "mco_chapter": chapter_name,
            "tables_flattened": "<table" in content_html.lower(),
        },
    )


# ---------------------------------------------------------------------------
# Deep-link builder
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepLinker:
    host_slug: str
    book_type: str = TYPE

    @property
    def base(self) -> str:
        return f"https://{self.host_slug}.municipalcodeonline.com"

    @property
    def home_url(self) -> str:
        return f"{self.base}/book?type={self.book_type}"

    def __call__(self, node_id: str) -> str:
        # The SPA addresses each node by URL fragment: ``#name=<id>``.
        return f"{self.home_url}#name={node_id}"


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


def _default_host_slug(city: str) -> str:
    # "Montgomery County" -> "montgomery".  Use the first word, lowercased.
    first = re.split(r"[^A-Za-z0-9]+", city.strip())[0]
    return first.lower()


class MunicipalCodeOnlineFetcher:
    """Fetch zoning ordinance sections from a Municipal Code Online book."""

    name = "municipalcodeonline"

    # The two headers that crack the vendor's anti-automation guard.
    _GUARD_HEADERS = {
        "x-csrf": "1",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        max_sections: int | None = None,
        host_slug: str | None = None,
        chapters: list[str] | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.max_sections = max_sections
        self.host_slug = host_slug
        # Optional explicit chapter node ids to fetch (e.g. ["10_ZONING"]).
        # When None, the zoning chapter is found data-drivenly by heading.
        self.chapters = chapters

    def fetch(self, *, city: str, state: str) -> FetchResult:
        host_slug = self.host_slug or _default_host_slug(city)
        deep_link = DeepLinker(host_slug=host_slug)
        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
        )

        with PoliteHttpClient(config) as client:
            self._client = client
            self._base = deep_link.base

            root = self._expand(node_id=None)
            chapter_nodes = self._resolve_chapters(root)

            sections: list[SectionRecord] = []
            chapter_names: list[str] = []
            for chapter in chapter_nodes:
                chapter_names.append(chapter["name"])
                sections.extend(
                    self._collect_chapter(chapter=chapter, deep_link=deep_link)
                )
                if self.max_sections is not None and len(sections) >= self.max_sections:
                    sections = sections[: self.max_sections]
                    break

        return FetchResult(
            sections=sections,
            source_home_url=deep_link.home_url,
            effective_date=None,
            provenance={
                "fetcher": self.name,
                "host_slug": host_slug,
                "book_type": TYPE,
                "chapters": chapter_names,
                "retrieved_at": datetime.utcnow().date().isoformat(),
                "auth_guard": "headers x-csrf:1 + X-Requested-With:XMLHttpRequest",
            },
        )

    # -- tree walking -----------------------------------------------------

    def _resolve_chapters(self, root: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.chapters:
            by_id = {n["id"]: n for n in root}
            resolved = []
            for wanted in self.chapters:
                node = by_id.get(wanted)
                if node is None:
                    # Allow specifying an id not present at root (still fetchable).
                    node = {"id": wanted, "name": wanted, "has_children": True}
                resolved.append(node)
            return resolved
        return [find_zoning_node(root)]

    def _expand(self, *, node_id: str | None) -> list[dict[str, Any]]:
        params = f"type={TYPE}&_={int(time.time() * 1000)}"
        if node_id is not None:
            params += f"&id={node_id}"
        raw = self._guarded_get(
            f"{self._base}/book/expand?{params}",
            cache_suffix=f".expand_{node_id or 'root'}.json",
        )
        return parse_expand(raw)

    def _content(self, node_id: str) -> str:
        url = (
            f"{self._base}/book/content?type={TYPE}&name={node_id}"
            f"&highlightTerm=&editing=false&printing=false&bookDataId="
            f"&_={int(time.time() * 1000)}"
        )
        raw = self._guarded_get(url, cache_suffix=f".content_{node_id}.json")
        return parse_content_payload(raw)

    def _collect_chapter(
        self, *, chapter: dict[str, Any], deep_link: DeepLinker
    ) -> list[SectionRecord]:
        records: list[SectionRecord] = []
        seen: set[str] = set()

        def walk(node: dict[str, Any], breadcrumb: list[str]) -> None:
            if self.max_sections is not None and len(records) >= self.max_sections:
                return
            if node["has_children"]:
                for child in self._expand(node_id=node["id"]):
                    walk(child, [*breadcrumb, node["name"]])
                return
            # Leaf node: candidate section.
            if node["id"] in seen:
                return
            seen.add(node["id"])
            content_html = self._content(node["id"])
            record = parse_section(
                node=node,
                content_html=content_html,
                deep_link=deep_link,
                breadcrumb=breadcrumb,
                chapter_name=chapter["name"],
            )
            if record is not None:
                records.append(record)

        walk(chapter, [])
        return records

    # -- guarded fetch ----------------------------------------------------

    def _guarded_get(self, url: str, *, cache_suffix: str) -> str:
        """``client.get_text`` but injecting the anti-automation guard headers.

        The shared :class:`PoliteHttpClient` sets a fixed default ``Accept`` and
        no ``x-csrf``; without those exact headers this vendor returns HTTP 500
        ``Unauthorized Access``.  We patch the underlying httpx client's default
        headers for the duration of this fetch so caching/rate-limit/backoff all
        still apply.
        """
        client = self._client
        # Merge guard headers into the httpx client's defaults (idempotent).
        for key, value in self._GUARD_HEADERS.items():
            client._client.headers[key] = value  # noqa: SLF001 - intentional
        return client.get_text(url, cache_suffix=cache_suffix)


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _month_number(name: str) -> int | None:
    return _MONTHS.get(name.lower().strip("."))


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None
