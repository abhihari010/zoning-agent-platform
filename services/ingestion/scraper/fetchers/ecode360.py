"""eCode360 / General Code fetcher.

General Code's eCode360 platform (``ecode360.com``) hosts zoning codes for
roughly 3,000 municipalities, primarily in the northeastern US (NY, NJ, PA, CT,
MA).  The platform is a React SPA backed by server-rendered HTML pages and a
public (unauthenticated) JSON TOC endpoint.  Endpoints were discovered by
inspecting the SPA's JavaScript bundle and network traffic; see
``../README.md`` for the full investigation log.

Endpoints used (all under ``https://ecode360.com``):

1. **Resolve city → customer code**
   ``GET /ajax/code/info?name={city}&state={ST}`` → JSON array
   ``[{"custId": "MI2395", "name": "Borough of Millersville, PA", ...}]``.
   Returns all matching customers; we pick the best match by name similarity.

2. **Full nested TOC**
   ``GET /toc/{custId}`` → JSON tree with ``{guid, title, number, type, label,
   prefix, href, children[]}``.  The response recurses to leaf sections
   (``type == "section"``), so a single call returns the entire ordinance
   structure.  The same endpoint works for any node guid (chapter, article, etc.)
   and returns the subtree rooted at that node.

3. **Section/article content page**
   ``GET /{article_guid}`` → server-rendered HTML.  For an article-level guid
   the page contains every section in that article as a ``<article>`` element.
   Each ``<article>`` has:
     - ``data-guid="{section_guid}"`` on the header ``<div>``
     - ``data-full-title="§ NNN: Heading."``
     - ``<span class="titleNumber">§ NNN</span>``
     - ``<div class="section_content content" id="{guid}_content">`` — body HTML
       (may include ``<div class="history">`` with amendment dates)

**Deep-link URL** for a section:
``https://ecode360.com/{parent_article_guid}#{section_guid}``

**Cloudflare bot protection.**  ecode360.com is behind Cloudflare Turnstile.
Plain ``httpx`` (TLS fingerprint from Python) is blocked immediately.  Bun
``fetch()`` passes intermittently but is rate-limited to roughly one request per
30 seconds per IP before challenges resume.  The ``PoliteHttpClient`` wraps
``httpx`` and will raise ``FetchBlockedError`` on 401/403.  Callers should
handle this and either retry with increased delay or record the block for later
re-scraping.  The on-disk cache means a successful run is never repeated.

Design: one ``SectionRecord`` per leaf section, mirroring the Municode fetcher.
The zoning chapter is found data-drivenly by heading text (``"zoning"``),
excluding ``"subdivision"``.  Reserved/placeholder sections are skipped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import FetchBlockedError, HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

SITE_BASE = "https://ecode360.com"

# Headings that identify the zoning ordinance chapter, case-insensitive.
_ZONING_HEADING_HINTS = ("zoning ordinance", "zoning")
# Never treat these as the zoning chapter even if they contain a hint.
_ZONING_HEADING_EXCLUDE = ("subdivision", "map", "application for zoning")

# eCode360 section numbers use § prefix: "§ 380-1", "§ 230-50", "§ 69.69".
# The number lives in <span class="titleNumber">§ 380-1</span>.
# data-full-title includes it as "§ 380-1: Title text." — we parse either form.
_SECTION_NUM_RE = re.compile(
    r"^(§\s*[\d][\w.\-]*)(?:\s*(?:through|[-–]\s*§\s*[\w.]+))?",
    re.IGNORECASE,
)
_RESERVED_RE = re.compile(r"\(?\s*reserved\s*\)?", re.IGNORECASE)

# Amendment/adoption dates embedded in HISTORY notes:
# <span class="hisdate">3-10-2008</span>  (M-D-YYYY or MM-DD-YYYY)
# <span class="hisdate">2-14-1996</span>
_HISDATE_RE = re.compile(
    r'class="hisdate">(\d{1,2})-(\d{1,2})-(\d{4})<',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_toc(toc_json: str | dict) -> dict[str, Any]:
    """Normalise a ``/toc/{guid}`` response into a canonical node dict.

    Each node has: ``guid``, ``title``, ``number``, ``type``, ``label``,
    ``href``, ``children`` (list of child nodes, same shape).
    """
    payload = json.loads(toc_json) if isinstance(toc_json, str) else toc_json
    if not isinstance(payload, dict):
        raise ValueError("eCode360 /toc response must be a JSON object.")

    def normalise(node: dict) -> dict[str, Any]:
        return {
            "guid": str(node.get("guid") or ""),
            "title": str(node.get("title") or ""),
            "number": str(node.get("number") or ""),
            "type": str(node.get("type") or ""),
            "label": str(node.get("label") or ""),
            "href": str(node.get("href") or ""),
            "children": [normalise(c) for c in (node.get("children") or [])],
        }

    return normalise(payload)


def find_zoning_node(toc_root: str | dict) -> dict[str, Any]:
    """Return the zoning chapter node from a root TOC, found by heading text.

    Searches breadth-first; prefers an exact "Zoning" chapter match over
    a partial match in a deeper node.  Never picks a node whose title
    contains ``"subdivision"`` or ``"map"``.
    """
    root = parse_toc(toc_root) if isinstance(toc_root, (str, dict)) else toc_root

    candidates: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        lowered = node["title"].lower()
        if any(bad in lowered for bad in _ZONING_HEADING_EXCLUDE):
            return
        if any(hint in lowered for hint in _ZONING_HEADING_HINTS):
            if node["type"] in ("chapter", "division", "article"):
                candidates.append(node)
        for child in node["children"]:
            walk(child)

    walk(root)
    if not candidates:
        raise ValueError(
            "Could not locate a zoning chapter in the eCode360 TOC. "
            "Try passing an explicit --code-id."
        )
    # Prefer nodes whose type is "chapter" and title is exactly "Zoning"
    # (not e.g. "Zoning Permit" article buried inside another chapter).
    def score(n: dict) -> tuple:
        exact = n["title"].strip().lower() == "zoning"
        is_chapter = n["type"] == "chapter"
        return (not exact, not is_chapter, n["title"])

    candidates.sort(key=score)
    return candidates[0]


def collect_leaf_sections(
    node: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    """Walk a TOC subtree and collect (section_node, parent_article_guid) pairs.

    eCode360 sections are ``type == "section"`` nodes.  Their content is served
    by fetching the parent article page (``/{parent_guid}``), which returns all
    sibling sections together.  We group by parent to minimise fetches.
    """
    result: list[tuple[dict[str, Any], str]] = []

    def walk(n: dict[str, Any], article_guid: str) -> None:
        if n["type"] == "section":
            result.append((n, article_guid))
            return
        # Track the article-level parent guid for content fetching.
        new_article = n["guid"] if n["type"] == "article" else article_guid
        for child in n["children"]:
            walk(child, new_article)

    walk(node, node["guid"])
    return result


def parse_article_page(
    html: str,
    *,
    deep_link: "DeepLinker",
    zoning_chapter_title: str,
    breadcrumb: list[str],
    fallback_effective_date: str | None = None,
) -> list[SectionRecord]:
    """Parse all ``<article>`` elements on an eCode360 article HTML page.

    Returns one ``SectionRecord`` per substantive section.  Reserved/empty
    sections return ``None`` from ``parse_section`` and are filtered out.
    """
    # Each section lives in its own <article>...</article> block.
    article_blocks = re.findall(
        r"<article>([\s\S]+?)</article>",
        html,
        re.IGNORECASE,
    )
    records: list[SectionRecord] = []
    seen_guids: set[str] = set()

    for block in article_blocks:
        record = parse_section(
            article_block=block,
            deep_link=deep_link,
            zoning_chapter_title=zoning_chapter_title,
            breadcrumb=breadcrumb,
            fallback_effective_date=fallback_effective_date,
        )
        if record is not None and record.node_id not in seen_guids:
            seen_guids.add(record.node_id)
            records.append(record)

    return records


def parse_section(
    *,
    article_block: str,
    deep_link: "DeepLinker",
    zoning_chapter_title: str,
    breadcrumb: list[str],
    fallback_effective_date: str | None = None,
) -> SectionRecord | None:
    """Build one SectionRecord from a single ``<article>`` HTML block.

    Returns ``None`` for reserved/empty/structural blocks.
    """
    # Extract section guid from data-guid attribute on the header div.
    guid_match = re.search(r'data-guid="(\d+)"', article_block)
    if not guid_match:
        return None
    section_guid = guid_match.group(1)

    # Extract full title from data-full-title attribute.
    full_title_match = re.search(r'data-full-title="([^"]+)"', article_block)
    if not full_title_match:
        return None
    full_title = full_title_match.group(1)

    # Extract the section number (§ NNN) from <span class="titleNumber">.
    # Capture up to the closing tag so we never cross the </span> boundary.
    num_match = re.search(
        r'class="titleNumber">\s*([^<]+?)\s*<', article_block
    )
    raw_number = num_match.group(1).strip() if num_match else ""

    # Derive section_ref from the number or from the full title.
    section_ref = _section_ref_from_number(raw_number) or _section_ref_from_title(full_title)
    if not section_ref:
        return None

    # Skip reserved/placeholder sections.
    if _RESERVED_RE.search(full_title):
        return None

    # Extract body HTML from the section_content div.
    content_match = re.search(
        r'class="section_content content"[^>]*>([\s\S]+)',
        article_block,
        re.IGNORECASE,
    )
    if not content_match:
        return None

    body_html = _strip_history_div(content_match.group(1))
    text = clean_html(body_html)
    if not text.strip():
        return None

    # Parse effective date from history notes in the full block.
    effective = effective_date_from_history(article_block) or fallback_effective_date

    # Deep-link: section anchor within its parent article page.
    url = deep_link(section_guid)

    # Heading: use full_title (already has "§ NNN: Title text." form).
    heading = full_title

    return SectionRecord(
        section_ref=section_ref,
        heading=heading,
        text=text,
        url=url,
        source_type="zoning_ordinance",
        node_id=section_guid,
        effective_date=effective,
        breadcrumb=list(breadcrumb),
        metadata={
            "scraper": "ecode360",
            "ecode360_guid": section_guid,
            "ecode360_chapter": zoning_chapter_title,
            "tables_flattened": "<table" in article_block.lower(),
        },
    )


def _section_ref_from_number(raw: str) -> str | None:
    """``"§ 380-1"`` -> ``"§ 380-1"`` ; ``"§ 230-176"`` -> ``"§ 230-176"``."""
    if not raw:
        return None
    # Normalise § symbol and collapse whitespace.
    ref = re.sub(r"\s+", " ", raw).strip()
    if not ref.startswith("§"):
        return None
    # Confirm there's a numeric part after the §.
    if not re.search(r"§\s*\d", ref):
        return None
    return ref


def _section_ref_from_title(full_title: str) -> str | None:
    """Fall back: parse ``"§ 380-1: Title text."`` -> ``"§ 380-1"``."""
    m = _SECTION_NUM_RE.match(full_title.strip())
    if not m:
        return None
    return m.group(1).strip()


def _strip_history_div(html: str) -> str:
    """Remove the leading ``<div class="history">...</div>`` from section body.

    The history note duplicates amendment metadata we parse separately.
    """
    return re.sub(
        r'^\s*<div class="history"[^>]*>[\s\S]*?</div>\s*',
        "",
        html,
        count=1,
        flags=re.IGNORECASE,
    )


def effective_date_from_history(html: str) -> str | None:
    """Extract the most recent adoption/amendment date from HISTORY spans.

    eCode360 marks history dates as:
    ``<span class="hisdate">M-D-YYYY</span>``

    Returns an ISO date string (``YYYY-MM-DD``) or ``None``.
    """
    dates: list[str] = []
    for mo, da, yr in _HISDATE_RE.findall(html):
        iso = _safe_iso(int(yr), int(mo), int(da))
        if iso:
            dates.append(iso)
    return max(dates) if dates else None


def parse_code_info(info_json: str | list) -> str:
    """Return the ``custId`` from an ``/ajax/code/info`` response.

    The endpoint returns a JSON array of matching municipalities.  We take
    the first result (highest-ranked by the server).
    """
    payload = json.loads(info_json) if isinstance(info_json, str) else info_json
    if not isinstance(payload, list) or not payload:
        raise ValueError(
            "eCode360 /ajax/code/info returned no results. "
            "Check city name and state."
        )
    first = payload[0]
    cust_id = str(first.get("custId") or "").strip()
    if not cust_id:
        raise ValueError("eCode360 /ajax/code/info result missing custId.")
    return cust_id


# ---------------------------------------------------------------------------
# Deep-link builder
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepLinker:
    """Builds eCode360 deep-link URLs.

    Deep-link to a section: ``https://ecode360.com/{article_guid}#{section_guid}``

    The ``article_guid`` is the immediate parent article of the section; this
    is the page that serves the section's HTML content.
    """

    customer_id: str

    @property
    def home_url(self) -> str:
        return f"{SITE_BASE}/{self.customer_id}"

    def __call__(self, section_guid: str, article_guid: str | None = None) -> str:
        if article_guid and article_guid != section_guid:
            return f"{SITE_BASE}/{article_guid}#{section_guid}"
        return f"{SITE_BASE}/{section_guid}"


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


def _default_customer_id(city: str) -> str | None:
    """No reliable default — must resolve via /ajax/code/info."""
    return None


class ECode360Fetcher:
    """Fetch zoning ordinance sections from an eCode360 / General Code host."""

    name = "ecode360"

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 2.0,
        max_sections: int | None = None,
        code_id: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        # eCode360 is behind Cloudflare; a polite 2-second delay is the minimum.
        self.request_delay = request_delay
        self.max_sections = max_sections
        # Optional explicit customer code (e.g. "MI2395"), bypassing /ajax/code/info.
        self.code_id = code_id

    def fetch(self, *, city: str, state: str) -> FetchResult:
        state = state.upper()
        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
        )

        with PoliteHttpClient(config) as client:
            # 1. Resolve city → customer code.
            customer_id = self.code_id or self._resolve_customer_id(
                client, city=city, state=state
            )
            deep_link = DeepLinker(customer_id=customer_id)

            # 2. Fetch full nested TOC.
            toc_raw = client.get_text(
                f"{SITE_BASE}/toc/{customer_id}",
                cache_suffix=f".toc_{customer_id}.json",
            )
            toc_root = parse_toc(toc_raw)

            # 3. Locate zoning chapter data-drivenly.
            zoning_node = find_zoning_node(toc_root)
            zoning_chapter_title = zoning_node["title"]

            # 4. Collect all leaf section nodes + their article parents.
            leaf_pairs = collect_leaf_sections(zoning_node)

            # 5. Group sections by article guid to minimise HTTP fetches.
            article_to_sections: dict[str, list[dict[str, Any]]] = {}
            for sec_node, art_guid in leaf_pairs:
                article_to_sections.setdefault(art_guid, []).append(sec_node)

            # 6. Fetch each article page and parse its sections.
            sections: list[SectionRecord] = []
            for art_guid, sec_nodes in article_to_sections.items():
                if self.max_sections is not None and len(sections) >= self.max_sections:
                    break

                # Build breadcrumb from the section nodes' ancestors.
                breadcrumb = self._build_breadcrumb(zoning_node, art_guid)

                try:
                    art_html = client.get_text(
                        f"{SITE_BASE}/{art_guid}",
                        cache_suffix=f".art_{art_guid}.html",
                    )
                except FetchBlockedError:
                    raise
                except Exception:
                    # Network hiccup on a single article — skip and continue.
                    continue

                records = parse_article_page(
                    art_html,
                    deep_link=deep_link,
                    zoning_chapter_title=zoning_chapter_title,
                    breadcrumb=breadcrumb,
                )
                # Filter to only the sections in our TOC (de-dup with seen set).
                sec_guids = {s["guid"] for s in sec_nodes}
                for rec in records:
                    if rec.node_id in sec_guids:
                        sections.append(rec)
                    if self.max_sections is not None and len(sections) >= self.max_sections:
                        break

        return FetchResult(
            sections=sections,
            source_home_url=deep_link.home_url,
            effective_date=None,
            provenance={
                "fetcher": self.name,
                "customer_id": customer_id,
                "zoning_chapter": zoning_chapter_title,
                "retrieved_at": datetime.utcnow().date().isoformat(),
                "auth_guard": (
                    "Cloudflare Turnstile — httpx blocked; "
                    "use request_delay >= 2.0 and on-disk cache"
                ),
            },
        )

    # -- helpers ------------------------------------------------------------

    def _resolve_customer_id(
        self, client: PoliteHttpClient, *, city: str, state: str
    ) -> str:
        raw = client.get_text(
            f"{SITE_BASE}/ajax/code/info?name={city}&state={state}",
            cache_suffix=f".code_info_{city}_{state}.json",
        )
        return parse_code_info(raw)

    def _build_breadcrumb(
        self, zoning_node: dict[str, Any], article_guid: str
    ) -> list[str]:
        """Return ordered ancestor titles from zoning chapter down to article."""
        breadcrumb: list[str] = []

        def walk(node: dict[str, Any], path: list[str]) -> bool:
            if node["guid"] == article_guid:
                breadcrumb.extend(path)
                return True
            for child in node["children"]:
                if walk(child, [*path, node["title"]]):
                    return True
            return False

        walk(zoning_node, [])
        return breadcrumb


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None
