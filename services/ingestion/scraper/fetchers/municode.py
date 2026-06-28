"""Municode fetcher.

Municode (``library.municode.com``) is a single-page app backed by a public JSON
API at ``api.municode.com``.  The endpoints used here were discovered by
inspecting the SPA's network traffic (see ``../README.md`` for the full
investigation log).  In summary:

1. ``GET /Clients/name?clientName={city}&stateAbbr={ST}`` -> ``ClientID``.
2. ``GET /ClientContent/{clientId}`` -> the ``codes`` product list; we pick the
   product whose ``contentTypeId == "CODES"`` (e.g. ``productId`` 10159,
   "Code of Ordinances").
3. ``GET /Jobs/latest/{productId}`` -> the latest published ``Job`` (``Id`` /
   ``jobId``) plus a ``BannerText`` that states the codification/effective date.
4. ``GET /CodesToc?jobId={jobId}&productId={productId}`` -> the root table of
   contents (chapters/appendices), each node carrying ``Id`` and ``Heading``.
5. ``GET /CodesToc/Children?jobId=&productId=&nodeId={id}`` -> child nodes of a
   TOC node (walked recursively to reach Article -> Division -> Section).
6. ``GET /CodesContent?jobId=&nodeId={id}&productId=`` -> a *chunk group* of
   ``Docs``; each doc has ``Id``, ``Title`` (e.g. ``"Sec. 4211 - Home
   occupations."``) and ``Content`` (HTML).  One CodesContent call returns every
   section in the node's chunk group, so we fetch once per division.

The deep-link URL for a section on the public site is::

    https://library.municode.com/{state}/{city}/codes/code_of_ordinances?nodeId={nodeId}

Design: we emit **one SectionRecord per leaf section node** (Sec. NNNN), giving
accurate, citable ``section_ref`` + deep-link granularity.  Reserved/empty
sections are skipped.  The zoning ordinance is identified data-drivenly by
heading text (``"zoning"``), never by a hard-coded per-city node id.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

API_BASE = "https://api.municode.com"
LIBRARY_BASE = "https://library.municode.com"

# Headings that identify the zoning ordinance chapter/appendix, case-insensitive.
_ZONING_HEADING_HINTS = ("zoning ordinance", "zoning")
# Headings to never treat as the zoning ordinance even if they contain a hint.
_ZONING_HEADING_EXCLUDE = ("subdivision", "comparative table", "supplement history")
# Product names that mark a *dedicated* zoning/development code product (a
# separate Municode "code" with its own slug, e.g. Chesapeake's "Zoning" or
# Suffolk's "Unified Development Ordinance") rather than the combined Code of
# Ordinances.  When one exists it is the authoritative zoning source.
_ZONING_PRODUCT_HINTS = (
    "unified development ordinance",
    "land development",
    "development ordinance",
    "development code",
    "zoning ordinance",
    "zoning",
)

# Matches a leaf section heading, capturing the citation prefix + number:
#   "Sec. 4211 - Home occupations."   -> "Sec. 4211"
#   "§ 6-100. - Intent."              -> "§ 6-100"   (Chesapeake-style § numbering)
#   "3-101 - Purpose."                -> "3-101"     (Alexandria-style bare numbering)
# The bare form requires a "." or "-" separator so structural docs ("ARTICLE
# III. - ...") and lone numbers never false-match as sections.
_SECTION_REF_RE = re.compile(
    r"^\s*("
    r"Sec\.?\s*[0-9][0-9A-Za-z.\-]*"
    r"|§\s*[0-9][0-9A-Za-z.\-]*"
    r"|[0-9]+[.\-][0-9A-Za-z][0-9A-Za-z.\-]*"
    r")",
    re.IGNORECASE,
)
# "Secs. 4202—4210 - [Reserved]." style ranges are skipped as non-substantive.
_RESERVED_RE = re.compile(r"\[?\s*reserved\s*\]?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-tested against saved fixtures, no network)
# ---------------------------------------------------------------------------


def parse_client_id(client_json: str | dict) -> int:
    payload = _as_dict(client_json)
    client_id = payload.get("ClientID")
    if not isinstance(client_id, int):
        raise ValueError("Municode client response missing integer ClientID.")
    return client_id


def parse_code_product_id(client_content_json: str | dict) -> int:
    payload = _as_dict(client_content_json)
    codes = payload.get("codes")
    if not isinstance(codes, list) or not codes:
        raise ValueError("Municode ClientContent response has no codes products.")
    # Prefer an explicit CODES content type; fall back to the first product.
    for code in codes:
        if isinstance(code, dict) and code.get("contentTypeId") == "CODES":
            pid = code.get("productId")
            if isinstance(pid, int):
                return pid
    pid = codes[0].get("productId") if isinstance(codes[0], dict) else None
    if not isinstance(pid, int):
        raise ValueError("Municode ClientContent response missing productId.")
    return pid


def select_zoning_product(client_content_json: str | dict) -> tuple[int, str, bool]:
    """Pick the product that holds the zoning ordinance.

    Returns ``(product_id, product_name, is_dedicated)``.

    Some jurisdictions publish zoning as a **separate** Municode code product
    (its own slug, e.g. Chesapeake's "Zoning" or Suffolk's "Unified Development
    Ordinance") alongside the combined "Code of Ordinances".  When such a
    dedicated product exists it is authoritative and ``is_dedicated`` is True —
    its entire TOC is the zoning code.  Otherwise we fall back to the primary
    Code of Ordinances product, inside which zoning lives as a chapter/appendix
    (``is_dedicated`` False).
    """
    payload = _as_dict(client_content_json)
    codes = payload.get("codes")
    if not isinstance(codes, list) or not codes:
        raise ValueError("Municode ClientContent response has no codes products.")
    products = [
        code
        for code in codes
        if isinstance(code, dict) and isinstance(code.get("productId"), int)
    ]
    if not products:
        raise ValueError("Municode ClientContent response missing productId.")

    # Prefer a dedicated zoning/development product when one is present.  A pure
    # "Subdivision"/"Comparative Table" product never matches a zoning hint, so
    # no extra exclusion is needed here — and excluding on "subdivision" would
    # wrongly skip a combined "Zoning and Subdivision Ordinance" product.
    for code in products:
        name = str(code.get("productName") or "")
        lowered = name.lower()
        if any(hint in lowered for hint in _ZONING_PRODUCT_HINTS):
            return code["productId"], name, True

    # Fall back to the combined Code of Ordinances (CODES content type).
    for code in products:
        if code.get("contentTypeId") == "CODES":
            return code["productId"], str(code.get("productName") or ""), False
    first = products[0]
    return first["productId"], str(first.get("productName") or ""), False


def parse_job(job_json: str | dict) -> tuple[int, str | None]:
    """Return ``(jobId, effective_date)`` from a ``/Jobs/latest`` response."""
    payload = _as_dict(job_json)
    job_id = payload.get("Id")
    if not isinstance(job_id, int):
        raise ValueError("Municode Jobs response missing integer Id.")
    effective = _effective_date_from_banner(payload.get("BannerText"))
    if not effective:
        effective = _iso_date(payload.get("PublishDate"))
    return job_id, effective


def find_zoning_node(toc_root_json: str | dict) -> tuple[str, str]:
    """Return ``(nodeId, heading)`` for the zoning ordinance chapter/appendix."""
    payload = _as_dict(toc_root_json)
    children = payload.get("Children")
    if not isinstance(children, list):
        raise ValueError("Municode TOC root has no Children.")
    candidates: list[tuple[str, str, bool]] = []
    for node in children:
        if not isinstance(node, dict):
            continue
        heading = str(node.get("Heading") or "")
        node_id = str(node.get("Id") or "")
        if not node_id or not heading:
            continue
        lowered = heading.lower()
        if any(bad in lowered for bad in _ZONING_HEADING_EXCLUDE):
            continue
        if any(hint in lowered for hint in _ZONING_HEADING_HINTS):
            candidates.append((node_id, heading, bool(node.get("HasChildren"))))
    if not candidates:
        raise ValueError("Could not locate a zoning ordinance node in the Municode TOC.")
    # Prefer a node that actually has children (some codes carry an empty
    # "Chapter NN - ZONING" stub alongside the populated chapter, e.g. Portsmouth
    # 40.1 stub vs 40.2 content), then the most specific match ("zoning
    # ordinance" over a bare "zoning").
    candidates.sort(
        key=lambda item: (not item[2], "zoning ordinance" not in item[1].lower(), item[1])
    )
    return candidates[0][0], candidates[0][1]


def parse_toc_children(children_json: str | list) -> list[dict[str, Any]]:
    payload = json.loads(children_json) if isinstance(children_json, str) else children_json
    if not isinstance(payload, list):
        raise ValueError("Municode CodesToc/Children response must be a JSON array.")
    out: list[dict[str, Any]] = []
    for node in payload:
        if not isinstance(node, dict):
            continue
        out.append(
            {
                "id": str(node.get("Id") or ""),
                "heading": str(node.get("Heading") or ""),
                "has_children": bool(node.get("HasChildren")),
            }
        )
    return out


def parse_content_sections(
    content_json: str | dict,
    *,
    deep_link: "DeepLinker",
    breadcrumb: list[str] | None = None,
    effective_date: str | None = None,
) -> list[SectionRecord]:
    """Turn a ``/CodesContent`` chunk-group response into SectionRecords.

    Only substantive leaf sections (those whose heading parses to a ``Sec.``
    reference and which have non-empty cleaned text) become records.  Reserved
    placeholders and structural (Article/Division) docs are skipped.
    """
    payload = _as_dict(content_json)
    docs = payload.get("Docs")
    if not isinstance(docs, list):
        raise ValueError("Municode CodesContent response missing Docs array.")

    records: list[SectionRecord] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        title = str(doc.get("Title") or "").strip()
        node_id = str(doc.get("Id") or "").strip()
        if not title or not node_id:
            continue
        if _RESERVED_RE.search(title):
            continue
        section_ref = _section_ref_from_title(title)
        if not section_ref:
            # Structural node (Article/Division) — skip; its sections come through
            # as their own docs.
            continue
        text = clean_html(str(doc.get("Content") or ""))
        if not text.strip():
            continue
        records.append(
            SectionRecord(
                section_ref=section_ref,
                heading=title,
                text=text,
                url=deep_link(node_id),
                source_type="zoning_ordinance",
                node_id=node_id,
                effective_date=effective_date,
                breadcrumb=list(breadcrumb or []),
                metadata={"municode_node_id": node_id},
            )
        )
    return records


# ---------------------------------------------------------------------------
# Deep-link builder
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepLinker:
    state: str
    city_slug: str
    code_slug: str = "code_of_ordinances"

    def __call__(self, node_id: str) -> str:
        return (
            f"{LIBRARY_BASE}/{self.state.lower()}/{self.city_slug}"
            f"/codes/{self.code_slug}?nodeId={node_id}"
        )

    @property
    def home_url(self) -> str:
        return f"{LIBRARY_BASE}/{self.state.lower()}/{self.city_slug}/codes/{self.code_slug}"


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------


def _slugify_city(city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", city.lower()).strip("_")


def _slugify_product(name: str) -> str:
    """Derive a Municode code URL slug from a product name.

    Municode's public ``/codes/{slug}`` path is the lowercased product name with
    runs of non-alphanumerics collapsed to underscores: ``"Zoning"`` ->
    ``"zoning"``, ``"Unified Development Ordinance"`` ->
    ``"unified_development_ordinance"``, ``"Code of Ordinances"`` ->
    ``"code_of_ordinances"``.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "code_of_ordinances"


class MunicodeFetcher:
    """Fetch zoning ordinance sections from the Municode JSON API."""

    name = "municode"

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        max_sections: int | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.max_sections = max_sections

    def fetch(self, *, city: str, state: str) -> FetchResult:
        state = state.upper()
        city_slug = _slugify_city(city)
        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
        )

        with PoliteHttpClient(config) as client:
            client_json = client.get_text(
                f"{API_BASE}/Clients/name?clientName={city}&stateAbbr={state}",
                cache_suffix=".client.json",
            )
            client_id = parse_client_id(client_json)

            content_json = client.get_text(
                f"{API_BASE}/ClientContent/{client_id}",
                cache_suffix=".clientcontent.json",
            )
            product_id, product_name, is_dedicated = select_zoning_product(content_json)
            # The deep-link slug must match the chosen product's public URL path;
            # for a combined code that is "code_of_ordinances", for a dedicated
            # product it is the slugified product name (e.g. "zoning").
            code_slug = _slugify_product(product_name) if is_dedicated else "code_of_ordinances"
            deep_link = DeepLinker(state=state, city_slug=city_slug, code_slug=code_slug)

            job_json = client.get_text(
                f"{API_BASE}/Jobs/latest/{product_id}",
                cache_suffix=".job.json",
            )
            job_id, effective_date = parse_job(job_json)

            toc_root = client.get_text(
                f"{API_BASE}/CodesToc?jobId={job_id}&productId={product_id}",
                cache_suffix=".toc_root.json",
            )
            dedicated_children: list[dict[str, Any]] | None = None
            if is_dedicated:
                # The whole product is the zoning code.  Its TOC root is the
                # productId node, whose children are *only* available inline in
                # the CodesToc response — ``/CodesToc/Children?nodeId={productId}``
                # does not resolve — so we seed the walk from the inline children.
                root = _as_dict(toc_root)
                zoning_node_id = str(root.get("Id") or "")
                zoning_heading = str(root.get("Heading") or product_name)
                dedicated_children = [
                    c for c in (root.get("Children") or []) if isinstance(c, dict)
                ]
                if not dedicated_children:
                    # Degenerate TOC — fall back to in-code node search.
                    zoning_node_id, zoning_heading = find_zoning_node(toc_root)
                    dedicated_children = None
            else:
                zoning_node_id, zoning_heading = find_zoning_node(toc_root)

            sections = self._collect_sections(
                client=client,
                job_id=job_id,
                product_id=product_id,
                zoning_node_id=zoning_node_id,
                zoning_heading=zoning_heading,
                deep_link=deep_link,
                effective_date=effective_date,
                dedicated_children=dedicated_children,
            )

        return FetchResult(
            sections=sections,
            source_home_url=deep_link.home_url,
            effective_date=effective_date,
            provenance={
                "fetcher": self.name,
                "client_id": client_id,
                "product_id": product_id,
                "product_name": product_name,
                "dedicated_zoning_product": is_dedicated,
                "code_slug": code_slug,
                "job_id": job_id,
                "zoning_node_id": zoning_node_id,
                "zoning_heading": zoning_heading,
            },
        )

    def _children(
        self, client: PoliteHttpClient, job_id: int, product_id: int, node_id: str
    ) -> list[dict[str, Any]]:
        raw = client.get_text(
            f"{API_BASE}/CodesToc/Children?jobId={job_id}&productId={product_id}&nodeId={node_id}",
            cache_suffix=f".toc_{node_id}.json",
        )
        return parse_toc_children(raw)

    def _collect_sections(
        self,
        *,
        client: PoliteHttpClient,
        job_id: int,
        product_id: int,
        zoning_node_id: str,
        zoning_heading: str,
        deep_link: DeepLinker,
        effective_date: str | None,
        dedicated_children: list[dict[str, Any]] | None = None,
    ) -> list[SectionRecord]:
        """Walk Article -> Division and fetch one CodesContent chunk group per
        leaf-bearing node, deduplicating sections by node id.

        For a combined code, the walk starts at ``zoning_node_id``.  For a
        dedicated zoning product, ``dedicated_children`` supplies the product
        root's top-level nodes (which must be seeded inline — see ``fetch``) and
        each is walked in turn.
        """
        records: dict[str, SectionRecord] = {}

        # Walk the TOC to find nodes whose children are leaf sections; each such
        # node maps to a single CodesContent chunk group.
        if dedicated_children is not None:
            chunk_group_nodes: list[tuple[str, list[str]]] = []
            for child in dedicated_children:
                child_id = str(child.get("Id") or "")
                child_heading = str(child.get("Heading") or "")
                if not child_id:
                    continue
                if child.get("HasChildren"):
                    chunk_group_nodes.extend(
                        self._find_chunk_group_nodes(
                            client, job_id, product_id, child_id,
                            [zoning_heading, child_heading],
                        )
                    )
                else:
                    # A top-level leaf (e.g. a cover or supplement-history node);
                    # its CodesContent rarely holds substantive sections but we
                    # include it so genuine flat sections are not missed.
                    chunk_group_nodes.append((child_id, [zoning_heading, child_heading]))
        else:
            chunk_group_nodes = self._find_chunk_group_nodes(
                client, job_id, product_id, zoning_node_id, [zoning_heading]
            )

        for node_id, breadcrumb in chunk_group_nodes:
            content_raw = client.get_text(
                f"{API_BASE}/CodesContent?jobId={job_id}&nodeId={node_id}&productId={product_id}",
                cache_suffix=f".content_{node_id}.json",
            )
            for record in parse_content_sections(
                content_raw,
                deep_link=deep_link,
                breadcrumb=breadcrumb,
                effective_date=effective_date,
            ):
                records.setdefault(record.node_id or record.section_ref, record)
                if self.max_sections is not None and len(records) >= self.max_sections:
                    return list(records.values())

        return list(records.values())

    def _find_chunk_group_nodes(
        self,
        client: PoliteHttpClient,
        job_id: int,
        product_id: int,
        node_id: str,
        breadcrumb: list[str],
    ) -> list[tuple[str, list[str]]]:
        """Return ``(node_id, breadcrumb)`` for every node that directly contains
        leaf sections.  Such a node's CodesContent call yields its sections."""
        children = self._children(client, job_id, product_id, node_id)
        if not children:
            return []

        leaf_children = [c for c in children if not c["has_children"]]
        result: list[tuple[str, list[str]]] = []
        if leaf_children:
            # This node is a chunk group: its CodesContent returns these sections.
            result.append((node_id, breadcrumb))

        for child in children:
            if child["has_children"]:
                result.extend(
                    self._find_chunk_group_nodes(
                        client,
                        job_id,
                        product_id,
                        child["id"],
                        [*breadcrumb, child["heading"]],
                    )
                )
        return result


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------


def _as_dict(value: str | dict) -> dict:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _section_ref_from_title(title: str) -> str | None:
    match = _SECTION_REF_RE.match(title)
    if not match:
        return None
    ref = re.sub(r"\s+", " ", match.group(1)).strip()
    # Drop trailing punctuation captured from "§ 6-100. - Intent." -> "§ 6-100".
    ref = ref.rstrip(".-").strip()
    # Normalize "Sec 4211" -> "Sec. 4211"
    ref = re.sub(r"^Sec(?!\.)", "Sec.", ref, flags=re.IGNORECASE)
    return ref


def _effective_date_from_banner(banner: object) -> str | None:
    if not isinstance(banner, str):
        return None
    # e.g. "Codified through Ordinance No. 2104, enacted December 9, 2025."
    match = re.search(
        r"enacted\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", banner
    )
    if not match:
        return None
    return _parse_us_date(match.group(1))


def _parse_us_date(value: str) -> str | None:
    from datetime import datetime

    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _iso_date(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.split("T", 1)[0]
