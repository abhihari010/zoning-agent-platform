"""American Legal Publishing fetcher.

American Legal Publishing hosts municipal codes for thousands of US
jurisdictions at ``codelibrary.amlegal.com`` — a React SPA backed by a JSON API
on the same host (``/api/...``).  The endpoints were discovered by reading the
SPA's JS bundle and confirming the live network traffic (see ``../README.md``
for the full investigation log).

Endpoints used (all under ``https://codelibrary.amlegal.com``):

1. **Resolve city → client slug**
   ``GET /api/clients-search/?s=`` → a JSON array of every client
   ``[{"name": "Plain City", "region": {"slug": "oh"}, "slug": "plaincity"}, ...]``.
   We filter by ``name`` + ``region.slug`` (state).  The query string is ignored
   server-side (it returns the full list), so we filter client-side.

2. **Resolve client → code (uuid + slug)**
   ``GET /codes/{client_slug}/`` (the landing HTML) carries
   ``data-codeuuid="..."`` (the default code's uuid) and a code link
   ``/codes/{client_slug}/latest/{code_slug}/...`` from which we read the slug.

3. **Code table of contents (top level)**
   ``GET /api/code-toc/{code_uuid}/`` → ``{uuid, slug, client_slug,
   sections: [{id, doc_id, title, type, has_children}, ...]}``.  Only the top
   level is returned; children are fetched lazily.

4. **Expand a node**
   ``GET /api/section-toc/{node_id}/`` (numeric ``id``) → that node with a
   ``children`` array (``{id, doc_id, orig_doc_id, orig_doc_idx, title,
   has_children}``).  Walked recursively to the leaf sections.

5. **Section content**
   ``GET /api/render-section/{client_slug}/latest/{code_slug}/{orig_doc_id}/
   {orig_doc_idx}/`` → ``{doc_id, title, html}`` for one leaf section.

**Deep-link URL** for a section on the public site::

    https://codelibrary.amlegal.com/codes/{client_slug}/latest/{code_slug}/{doc_id}

**Cloudflare.**  ``codelibrary.amlegal.com`` is behind Cloudflare and blocks the
plain Python/OpenSSL TLS fingerprint with HTTP 403.  Presenting Chrome's TLS
fingerprint clears it, so this fetcher defaults to ``impersonate="chrome"`` via
the shared :class:`PoliteHttpClient` curl_cffi transport (see ``http_client``).

Design: one ``SectionRecord`` per leaf section, mirroring the other fetchers.
The zoning part/title is found data-drivenly by heading text (``"zoning"``),
excluding ``"subdivision"``.  Reserved/repealed sections are skipped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..html_cleaner import clean_html
from ..http_client import FetchBlockedError, HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

SITE_BASE = "https://codelibrary.amlegal.com"

# Headings that identify a zoning part/title, case-insensitive.
_ZONING_HEADING_HINTS = ("zoning ordinance", "zoning")
# Branches to never treat as zoning content even if they contain a hint.
_ZONING_HEADING_EXCLUDE = ("subdivision", "zoning map")

# Leaf section numbers: "1141.01", "1182.05", Chicago-style "17-1-0501".
_SECTION_REF_RE = re.compile(r"^\s*([0-9][0-9A-Za-z]*(?:[.\-][0-9A-Za-z]+)+)")
_RESERVED_RE = re.compile(r"\b(reserved|repealed)\b", re.IGNORECASE)

# Adoption/amendment dates in history notes, e.g. "(Ord. 05-08.  Passed 2-25-08.)".
_PASSED_RE = re.compile(r"Passed\s+(\d{1,2})-(\d{1,2})-(\d{2,4})", re.IGNORECASE)
# Code currency, e.g. "Local legislation current through March 31, 2026".
_CURRENCY_RE = re.compile(
    r"current through\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_client_search(search_json: str | list, *, city: str, state: str) -> str:
    """Return the client slug for ``city, state`` from a ``/clients-search`` array.

    Matches ``name`` case-insensitively and ``region.slug`` against the
    lowercased state code.  Raises if no unambiguous match is found.
    """
    payload = json.loads(search_json) if isinstance(search_json, str) else search_json
    if not isinstance(payload, list):
        raise ValueError("AmLegal clients-search response must be a JSON array.")
    want_name = _norm(city)
    want_state = state.strip().lower()
    matches = [
        c
        for c in payload
        if isinstance(c, dict)
        and _norm(str(c.get("name", ""))) == want_name
        and str((c.get("region") or {}).get("slug", "")).lower() == want_state
    ]
    if not matches:
        raise ValueError(
            f"No American Legal client found for {city!r}, {state!r}. "
            "Try passing an explicit --client-slug."
        )
    return str(matches[0]["slug"])


def extract_code_ref(landing_html: str) -> tuple[str, str]:
    """Return ``(code_uuid, code_slug)`` from a client landing page's HTML."""
    uuid_match = re.search(r'data-codeuuid="([0-9a-f\-]{36})"', landing_html)
    if not uuid_match:
        raise ValueError("Could not find data-codeuuid on the AmLegal landing page.")
    code_uuid = uuid_match.group(1)
    code_slug = None
    for m in re.finditer(r"/codes/[a-z0-9_]+/latest/([a-z0-9_]+)", landing_html):
        slug = m.group(1)
        if slug not in ("overview", "search"):
            code_slug = slug
            break
    if not code_slug:
        raise ValueError("Could not find a code slug on the AmLegal landing page.")
    return code_uuid, code_slug


def parse_code_toc(toc_json: str | dict) -> dict[str, Any]:
    """Normalise a ``/code-toc`` response into ``{uuid, slug, client_slug, sections}``."""
    payload = json.loads(toc_json) if isinstance(toc_json, str) else toc_json
    if not isinstance(payload, dict):
        raise ValueError("AmLegal code-toc response must be a JSON object.")
    sections = [
        _norm_node(s) for s in (payload.get("sections") or []) if isinstance(s, dict)
    ]
    return {
        "uuid": str(payload.get("uuid") or ""),
        "slug": str(payload.get("slug") or ""),
        "client_slug": str(payload.get("client_slug") or ""),
        "title": str(payload.get("title") or ""),
        "sections": sections,
    }


def parse_section_toc(toc_json: str | dict) -> dict[str, Any]:
    """Normalise a ``/section-toc`` response (a node plus its ``children``)."""
    payload = json.loads(toc_json) if isinstance(toc_json, str) else toc_json
    if not isinstance(payload, dict):
        raise ValueError("AmLegal section-toc response must be a JSON object.")
    node = _norm_node(payload)
    node["children"] = [
        _norm_node(c) for c in (payload.get("children") or []) if isinstance(c, dict)
    ]
    return node


def is_excluded_branch(title: str) -> bool:
    """True for branches to skip while collecting (subdivision, zoning map)."""
    lowered = title.lower()
    return any(bad in lowered for bad in _ZONING_HEADING_EXCLUDE)


def find_zoning_node(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the zoning part/title node from a list of TOC nodes, by heading."""
    candidates = [
        s
        for s in sections
        if not is_excluded_branch(s.get("title", ""))
        and any(hint in s["title"].lower() for hint in _ZONING_HEADING_HINTS)
    ]
    if not candidates:
        raise ValueError(
            "Could not locate a zoning part/title in the American Legal TOC. "
            "Try passing an explicit --code-slug or a different city."
        )
    # Prefer the shortest matching heading (the zoning container, not a
    # deeply-qualified sub-heading) then alphabetical for stability.
    candidates.sort(key=lambda n: (len(n["title"]), n["title"]))
    return candidates[0]


def section_ref_from_title(title: str) -> str | None:
    """``"1141.01 ZONING DISTRICT MAP ADOPTED."`` -> ``"1141.01"`` (None if no ref)."""
    match = _SECTION_REF_RE.match(title or "")
    if not match:
        return None
    return match.group(1).strip()


def effective_date_from_html(html: str) -> str | None:
    """Return the most recent ``Passed M-D-YY`` date from a section's history.

    Returns an ISO date string (``YYYY-MM-DD``) or ``None``.
    """
    dates: list[str] = []
    for mo, da, yr in _PASSED_RE.findall(html):
        iso = _safe_iso(_expand_year(int(yr)), int(mo), int(da))
        if iso:
            dates.append(iso)
    return max(dates) if dates else None


def currency_to_iso(currency_info: str) -> str | None:
    """``"...current through March 31, 2026 | ..."`` -> ``"2026-03-31"`` (or None)."""
    m = _CURRENCY_RE.search(currency_info or "")
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return _safe_iso(int(m.group(3)), month, int(m.group(2)))


def _strip_heading(html: str) -> str:
    """Drop the leading ``<h4>...</h4>`` section heading so it isn't duplicated."""
    return re.sub(r"<h4[^>]*>.*?</h4>", "", html, count=1, flags=re.IGNORECASE | re.DOTALL)


def parse_render_section(
    render_json: str | dict,
    *,
    deep_link: "DeepLinker",
    breadcrumb: list[str],
    chapter_title: str = "",
    fallback_effective_date: str | None = None,
) -> SectionRecord | None:
    """Build one SectionRecord from a ``/render-section`` response.

    Returns ``None`` for reserved/empty sections.
    """
    payload = json.loads(render_json) if isinstance(render_json, str) else render_json
    if not isinstance(payload, dict):
        raise ValueError("AmLegal render-section response must be a JSON object.")

    title = str(payload.get("title") or "").strip()
    doc_id = str(payload.get("doc_id") or "").strip()
    html = str(payload.get("html") or "")
    if not title or not doc_id:
        return None

    section_ref = section_ref_from_title(title)
    if not section_ref:
        return None
    if _RESERVED_RE.search(title):
        return None

    text = clean_html(_strip_heading(html))
    if not text.strip():
        return None

    effective = effective_date_from_html(html) or fallback_effective_date

    return SectionRecord(
        section_ref=section_ref,
        heading=title,
        text=text,
        url=deep_link(doc_id),
        source_type="zoning_ordinance",
        node_id=doc_id,
        effective_date=effective,
        breadcrumb=list(breadcrumb),
        metadata={
            "scraper": "amlegal",
            "amlegal_doc_id": doc_id,
            "amlegal_chapter": chapter_title,
            "tables_flattened": "<table" in html.lower(),
        },
    )


# ---------------------------------------------------------------------------
# Deep-link builder
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepLinker:
    client_slug: str
    code_slug: str

    @property
    def home_url(self) -> str:
        return f"{SITE_BASE}/codes/{self.client_slug}/latest/{self.code_slug}"

    def __call__(self, doc_id: str) -> str:
        return f"{self.home_url}/{doc_id}"


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


class AmericanLegalFetcher:
    """Fetch zoning ordinance sections from American Legal Publishing."""

    name = "amlegal"

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 2.0,
        max_sections: int | None = None,
        client_slug: str | None = None,
        code_slug: str | None = None,
        impersonate: str | None = "chrome",
    ) -> None:
        self.cache_dir = cache_dir
        # codelibrary.amlegal.com is behind Cloudflare; a polite delay is the minimum.
        self.request_delay = request_delay
        self.max_sections = max_sections
        # Optional overrides bypassing auto-resolution.
        self.client_slug = client_slug
        self.code_slug = code_slug
        # Cloudflare blocks the plain httpx TLS fingerprint; impersonate Chrome.
        self.impersonate = impersonate

    def fetch(self, *, city: str, state: str) -> FetchResult:
        state = state.upper()
        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
            impersonate=self.impersonate,
        )

        with PoliteHttpClient(config) as client:
            self._client = client

            # 1. Resolve client slug.
            client_slug = self.client_slug or self._resolve_client_slug(
                city=city, state=state
            )

            # 2. Resolve code uuid + slug from the landing page.
            landing = client.get_text(
                f"{SITE_BASE}/codes/{client_slug}/",
                cache_suffix=f".landing_{client_slug}.html",
            )
            code_uuid, resolved_slug = extract_code_ref(landing)
            code_slug = self.code_slug or resolved_slug
            deep_link = DeepLinker(client_slug=client_slug, code_slug=code_slug)

            # 3. Code-level effective date (currency) as a fallback.
            fallback_date = self._client_currency_date(client_slug)

            # 4. Top-level TOC + zoning node (data-driven).
            toc = parse_code_toc(
                client.get_text(
                    f"{SITE_BASE}/api/code-toc/{code_uuid}/",
                    cache_suffix=f".codetoc_{code_uuid}.json",
                )
            )
            zoning = find_zoning_node(toc["sections"])

            # 5. Walk to leaf sections and render each.
            sections = self._collect(
                zoning_node=zoning,
                deep_link=deep_link,
                client_slug=client_slug,
                code_slug=code_slug,
                fallback_date=fallback_date,
            )

        return FetchResult(
            sections=sections,
            source_home_url=deep_link.home_url,
            effective_date=fallback_date,
            provenance={
                "fetcher": self.name,
                "client_slug": client_slug,
                "code_slug": code_slug,
                "code_uuid": code_uuid,
                "zoning_node": zoning["title"],
                "retrieved_at": datetime.utcnow().date().isoformat(),
                "impersonate": self.impersonate,
                "auth_guard": (
                    "Cloudflare TLS-fingerprint block — plain httpx returns 403; "
                    f"transport impersonates {self.impersonate or 'none'} via curl_cffi"
                ),
            },
        )

    # -- resolution helpers ----------------------------------------------

    def _resolve_client_slug(self, *, city: str, state: str) -> str:
        raw = self._client.get_text(
            f"{SITE_BASE}/api/clients-search/?s={quote(city)}",
            cache_suffix=f".clients_{_norm(city)}_{state.lower()}.json",
        )
        return parse_client_search(raw, city=city, state=state)

    def _client_currency_date(self, client_slug: str) -> str | None:
        try:
            raw = self._client.get_text(
                f"{SITE_BASE}/api/clients/{client_slug}/",
                cache_suffix=f".client_{client_slug}.json",
            )
            payload = json.loads(raw)
        except (FetchBlockedError, Exception):  # noqa: BLE001
            raise
        for ver in payload.get("versions") or []:
            iso = currency_to_iso(str(ver.get("currency_info") or ""))
            if iso:
                return iso
        return None

    # -- tree walk --------------------------------------------------------

    def _section_toc(self, node_id: int | str) -> dict[str, Any]:
        raw = self._client.get_text(
            f"{SITE_BASE}/api/section-toc/{node_id}/",
            cache_suffix=f".sectoc_{node_id}.json",
        )
        return parse_section_toc(raw)

    def _render(
        self, *, client_slug: str, code_slug: str, orig_doc_id: str, orig_doc_idx: int
    ) -> dict[str, Any]:
        url = (
            f"{SITE_BASE}/api/render-section/{client_slug}/latest/{code_slug}/"
            f"{quote(str(orig_doc_id), safe='')}/{orig_doc_idx}/"
        )
        raw = self._client.get_text(url, cache_suffix=f".render_{orig_doc_id}_{orig_doc_idx}.json")
        return json.loads(raw)

    def _collect(
        self,
        *,
        zoning_node: dict[str, Any],
        deep_link: DeepLinker,
        client_slug: str,
        code_slug: str,
        fallback_date: str | None,
    ) -> list[SectionRecord]:
        records: list[SectionRecord] = []
        seen: set[str] = set()

        def walk(node: dict[str, Any], breadcrumb: list[str], chapter_title: str) -> None:
            if self.max_sections is not None and len(records) >= self.max_sections:
                return
            if is_excluded_branch(node.get("title", "")):
                return
            if node.get("has_children"):
                expanded = self._section_toc(node["id"])
                # The deepest container with a section-style title is the chapter.
                child_chapter = node["title"] if node["title"].lower().startswith("chapter") else chapter_title
                for child in expanded["children"]:
                    walk(child, [*breadcrumb, node["title"]], child_chapter)
                return
            # Leaf section.
            doc_id = node.get("doc_id", "")
            if doc_id in seen:
                return
            seen.add(doc_id)
            render = self._render(
                client_slug=client_slug,
                code_slug=code_slug,
                orig_doc_id=node.get("orig_doc_id") or doc_id,
                orig_doc_idx=node.get("orig_doc_idx") or 0,
            )
            record = parse_render_section(
                render,
                deep_link=deep_link,
                breadcrumb=breadcrumb,
                chapter_title=chapter_title,
                fallback_effective_date=fallback_date,
            )
            if record is not None:
                records.append(record)

        # The zoning node from code-toc carries a numeric id; expand it.
        top = self._section_toc(zoning_node["id"])
        for child in top["children"]:
            walk(child, [zoning_node["title"]], zoning_node["title"])
            if self.max_sections is not None and len(records) >= self.max_sections:
                break
        return records


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _norm_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "doc_id": str(node.get("doc_id") or ""),
        "orig_doc_id": node.get("orig_doc_id"),
        "orig_doc_idx": node.get("orig_doc_idx"),
        "title": str(node.get("title") or ""),
        "type": str(node.get("type") or ""),
        "has_children": bool(node.get("has_children")),
    }


def _expand_year(yy: int) -> int:
    if yy >= 100:
        return yy
    return 2000 + yy if yy <= 49 else 1900 + yy


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None
