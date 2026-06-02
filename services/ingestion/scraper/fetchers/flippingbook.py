"""FlippingBook fetcher.

FlippingBook (web.flippingbook.com or self-hosted) renders PDFs as per-page HTML
served at ``{base_url}/{page}/``.  The real text lives in
``<div id="text-container">``.  Navigation chrome is in a separate
``<div class="nav-links">`` div and in the ``<h1>`` title, so we strip those
before extracting content.

Each page's ``<p>`` starts with sidebar artefacts that FlippingBook injects
(page number, chapter/section heading from the running header, chapter sidebar
indicator "01 Chapter", publication title, effective date).  We strip the
known patterns so what remains is the body of the ordinance section.

Pages are then concatenated and split at "CHAPTER N" headings to produce one
SectionRecord per chapter.  This is reusable: any FlippingBook-hosted zoning
ordinance can use ``--fetcher flippingbook --url <base_url>``.

Usage::

    python services/ingestion/scraper/run_scrape.py \\
        --city "Franklin" --state TN \\
        --fetcher flippingbook \\
        --url "https://web.franklintn.gov/flippingbook/FranklinZoningOrdinance"
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

# Matches "CHAPTER 3" or "CHAPTER 3 ZONING DISTRICTS" in ALL-CAPS.
# Not case-insensitive: we want to match only the all-caps chapter headings,
# not inline cross-references like "see Chapter 3" (mixed case) or the
# per-page sidebar "03 Chapter" (lowercase).
# Title is optional — some chapter-title pages may only have the number.
_CHAPTER_HEADING_RE = re.compile(
    # Chapter titles are alphabetic words only ("ZONING DISTRICTS", "NONCONFORMITIES").
    # No digits in the title group so we don't bleed into the following section number
    # (e.g. "CHAPTER 2 NONCONFORMITIES 2.1 General..." must NOT capture the trailing "2").
    r"CHAPTER\s+(\d+)\.?\s*([A-Z][A-Z ,&'—–\-]+)?",
)

_EFFECTIVE_DATE_RE = re.compile(
    r"\bEffective\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b"
)


def _parse_effective_date(text: str) -> str | None:
    """Return the ordinance effective date as ISO YYYY-MM-DD, or None."""
    m = _EFFECTIVE_DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


class _TextContainerExtractor(HTMLParser):
    """Extract text from <div id="text-container">, excluding <h1>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_text_container = False
        self._in_h1 = False
        self._skip_depth = 0
        self._h1_depth = 0
        self._container_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div":
            attrs_dict = dict(attrs)
            if attrs_dict.get("id") == "text-container":
                self._in_text_container = True
                self._container_depth = 1
                return
        if self._in_text_container:
            if tag == "div":
                self._container_depth += 1
            if tag == "h1":
                self._in_h1 = True
                self._h1_depth = 1
                return
            if tag in ("p", "li", "br", "h2", "h3", "h4", "h5", "h6", "div"):
                self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._in_text_container:
            if tag == "div":
                self._container_depth -= 1
                if self._container_depth <= 0:
                    self._in_text_container = False
                    return
            if tag == "h1" and self._in_h1:
                self._in_h1 = False
                self._h1_depth = 0
                return
            if tag in ("p", "li", "h2", "h3", "h4", "h5", "h6", "div"):
                self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_text_container and not self._in_h1:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse horizontal whitespace; preserve newlines.
        lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in raw.split("\n")]
        out: list[str] = []
        blank_run = 0
        for line in lines:
            if line:
                blank_run = 0
                out.append(line)
            else:
                blank_run += 1
                if blank_run == 1:
                    out.append("")
        return "\n".join(out).strip()


def _extract_page_text(html: str) -> str:
    """Extract text from the FlippingBook text-container, skipping the h1 title."""
    extractor = _TextContainerExtractor()
    extractor.feed(html)
    extractor.close()
    text = extractor.get_text()
    if text:
        return text
    # Fallback: clean the full HTML (navigation noise included, but workable)
    return clean_html(html)


# ---------------------------------------------------------------------------
# Boilerplate stripping
# ---------------------------------------------------------------------------


def _strip_boilerplate(text: str, title: str) -> str:
    """Strip FlippingBook running-header artefacts from extracted page text.

    FlippingBook's PDF renderer injects per-page sidebar elements into the
    ``<p>`` content block:
    - Chapter sidebar number + "Chapter" keyword: "03 20 Chapter"
    - Publication title: "Franklin Zoning Ordinance"
    - Effective date: "Effective January 13, 2026"
    - FlippingBook footer: "Made with FlippingBook"
    - FlippingBook publisher fingerprint token: "RkJQdWJsaXNoZXIy NTY1Mzc2"
    - Standalone page numbers and navigation artefacts
    """
    # Remove BOM
    text = text.replace("﻿", "").replace("ï»¿", "")

    # Remove "Made with FlippingBook …" (end of page)
    text = re.sub(r"Made\s+with\s+FlippingBook[^\n]*", "", text, flags=re.IGNORECASE)

    # FlippingBook publisher fingerprint always starts with "RkJQ"
    text = re.sub(r"RkJQ[A-Za-z0-9+/=\s]+", "", text)

    # Remove publication title (case-insensitive exact match)
    text = re.sub(re.escape(title), "", text, flags=re.IGNORECASE)

    # Remove effective date "Effective Month DD, YYYY"
    text = re.sub(
        r"\bEffective\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\b", "", text, flags=re.IGNORECASE
    )

    # Remove chapter sidebar indicators (anywhere in text):
    # "03 20 Chapter" or "03 Chapter" (sidebar chapter-number + page + "Chapter")
    text = re.sub(r"\b0\d\s+\d+\s+Chapter\b", "", text)
    text = re.sub(r"\b0\d\s+Chapter\b", "", text)

    # Remove standalone navigation numbers (1-3 digit numbers alone in text after stripping)
    text = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", text)

    # "Table of Contents" navigation artefact
    text = re.sub(r"\bTable\s+of\s+Contents\b", "", text, flags=re.IGNORECASE)

    # Collapse extra blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Chapter grouping
# ---------------------------------------------------------------------------


def _group_into_chapters(pages: list[str], *, base_url: str) -> list[SectionRecord]:
    """Concatenate page texts and split at CHAPTER headings.

    The Table of Contents (pages 4-5) contains CHAPTER headings followed by
    just a page number, then the actual chapter intro pages repeat the same
    heading with full body text.  We split on every occurrence and keep only
    the one with the longest body per chapter number, so TOC stub entries
    never win over the real chapter body.
    """
    full_text = "\n".join(pages)

    # re.split with 2 capture groups returns [pre, g1, g2, body, g1, g2, body, …]
    parts = _CHAPTER_HEADING_RE.split(full_text)

    # Collect all occurrences per chapter number; keep the longest body.
    # chapter_best: {int -> (title_suffix, body)}
    chapter_best: dict[int, tuple[str, str]] = {}

    i = 1
    while i + 2 < len(parts):
        chapter_num_str = parts[i].strip()
        chapter_title_suffix = (parts[i + 1] or "").strip()
        body = parts[i + 2].strip()
        i += 3

        if not chapter_num_str.isdigit():
            continue
        chapter_num = int(chapter_num_str)

        # Fix 2: strip running-header residue, e.g. "43 ZONING DISTRICTS"
        if chapter_title_suffix:
            body = re.sub(
                rf"\b\d{{1,3}}\s+{re.escape(chapter_title_suffix)}\b",
                "",
                body,
            )
        # Fix 3: strip TOC page numbers — bare 1-3 digit number between a title
        # and the next N.N section marker (leaves real dimensions like "60 feet" intact)
        body = re.sub(r"\s+\d{1,3}(?=\s+\d+\.\d+(?:\.\d+)?\b)", "", body)
        # Collapse whitespace introduced by stripping
        body = re.sub(r"[ \t]{2,}", " ", body)
        body = re.sub(r"\n{3,}", "\n\n", body)
        body = body.strip()

        existing_title, existing_body = chapter_best.get(chapter_num, ("", ""))
        # Prefer the occurrence with the most body text (real chapter over TOC stub)
        if len(body) > len(existing_body):
            # Use whichever title is longer/more descriptive
            title = chapter_title_suffix if len(chapter_title_suffix) >= len(existing_title) else existing_title
            chapter_best[chapter_num] = (title, body)

    # Build ordered records
    records: list[SectionRecord] = []
    for chapter_num in sorted(chapter_best.keys()):
        chapter_title_suffix, body = chapter_best[chapter_num]
        section_ref = f"Chapter {chapter_num}"
        heading = section_ref
        if chapter_title_suffix:
            heading = f"Chapter {chapter_num}. {chapter_title_suffix}"

        combined = f"{heading}\n\n{body}".strip()
        if not combined:
            continue

        records.append(
            SectionRecord(
                section_ref=section_ref,
                heading=heading,
                text=combined,
                url=base_url,
                source_type="zoning_ordinance",
            )
        )

    return records


# ---------------------------------------------------------------------------
# Public fetcher class
# ---------------------------------------------------------------------------


def _slugify_title(url_segment: str) -> str:
    """Convert CamelCase URL segment to display title. 'FranklinZoningOrdinance' → 'Franklin Zoning Ordinance'."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", url_segment)
    return re.sub(r"[_-]+", " ", spaced).strip()


def _total_pages_from_html(html: str) -> int:
    """Parse page count from a FlippingBook page (look for the 'last' nav link)."""
    # <a class="internalLink" rel="last" href="../437/" …>437</a>
    m = re.search(r'rel=["\']last["\'][^>]*href=["\'][^"\']*?(\d+)/["\']', html, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: largest number appearing in nav-links div
    nav_match = re.search(r'class=["\']nav-links["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
    if nav_match:
        nums = [int(n) for n in re.findall(r"\b(\d{2,4})\b", nav_match.group(1))]
        if nums:
            return max(nums)
    return 0


class FlippingBookFetcher:
    """Fetch a zoning ordinance from a FlippingBook-hosted publication.

    Scrapes individual page HTML from ``{base_url}/{page}/``, strips nav chrome,
    and groups text into chapter-level SectionRecords using CHAPTER headings.

    All pages are cached under the pack's ``raw/`` directory, so re-runs after
    a partial failure are free (no re-fetching of already-cached pages).
    """

    name = "flippingbook"

    def __init__(
        self,
        base_url: str,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        max_sections: int | None = None,
        effective_date: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.max_sections = max_sections  # applied as a page cap for smoke runs
        self.effective_date = effective_date

    def fetch(self, *, city: str, state: str) -> FetchResult:
        state = state.upper()
        # Derive the title for boilerplate stripping from the URL segment
        url_segment = self.base_url.rstrip("/").split("/")[-1]
        title = _slugify_title(url_segment)

        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
        )

        with PoliteHttpClient(config) as client:
            # Discover total page count from page 2 (page 1 is a redirect)
            page2_html = client.get_text(
                f"{self.base_url}/2/", cache_suffix=".page_2.html"
            )
            total_pages = _total_pages_from_html(page2_html)
            if total_pages < 2:
                raise ValueError(
                    f"Could not determine page count from {self.base_url!r}. "
                    "Check that the URL is a valid FlippingBook publication."
                )

            # Apply max_sections as a page limit for smoke runs
            fetch_up_to = total_pages
            if self.max_sections is not None:
                fetch_up_to = min(total_pages, self.max_sections * 18)

            print(
                f"[ws1] FlippingBook: title={title!r} total_pages={total_pages}"
                f" fetching_up_to={fetch_up_to}",
                file=sys.stderr,
            )

            pages: list[str] = []
            parsed_effective_date: str | None = None
            for page_num in range(1, fetch_up_to + 1):
                url = f"{self.base_url}/{page_num}/"
                html = client.get_text(url, cache_suffix=f".page_{page_num:04d}.html")
                raw_text = _extract_page_text(html)
                if parsed_effective_date is None:
                    parsed_effective_date = _parse_effective_date(raw_text)
                stripped = _strip_boilerplate(raw_text, title)
                if stripped:
                    pages.append(stripped)
                if page_num % 50 == 0:
                    print(
                        f"[ws1] ... fetched {page_num}/{fetch_up_to} pages",
                        file=sys.stderr,
                    )

        sections = _group_into_chapters(pages, base_url=self.base_url)
        if self.max_sections is not None:
            sections = sections[: self.max_sections]

        print(
            f"[ws1] FlippingBook: {len(pages)} pages → {len(sections)} chapter sections",
            file=sys.stderr,
        )
        return FetchResult(
            sections=sections,
            source_home_url=self.base_url,
            effective_date=self.effective_date or parsed_effective_date,
            provenance={
                "fetcher": self.name,
                "base_url": self.base_url,
                "total_pages": total_pages,
                "pages_fetched": len(pages),
            },
        )
