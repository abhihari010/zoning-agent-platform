"""Generic HTML fallback fetcher.

When a jurisdiction's zoning code is not on Municode (or Municode blocks us), we
fall back to fetching an official zoning page directly and cleaning the HTML into
one or a few sections.  This is intentionally low-fidelity: it produces a single
``SectionRecord`` (or one per ``<h2>/<h3>`` heading) so the manifest still
carries real, citable text instead of a hand-written summary.

It is given explicit URLs because there is no generic way to discover a
jurisdiction's zoning page — discovery is handled upstream by
``scripts/discover_jurisdiction_sources.py``.  No per-city logic lives here.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..html_cleaner import clean_html
from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

# Split cleaned text on lines that look like headings to create coarse sections.
_HEADING_LINE_RE = re.compile(r"^(?:Sec\.?\s*[0-9]|Article\s|Division\s|Chapter\s)", re.IGNORECASE)


def split_into_sections(text: str, *, base_url: str, source_type: str) -> list[SectionRecord]:
    """Split cleaned page text into coarse sections on heading-like lines.

    Pure and unit-testable.  Falls back to a single record when no headings are
    detected.
    """
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if _HEADING_LINE_RE.match(line.strip()) and line.strip():
            if current_body:
                sections.append((current_heading, current_body))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_heading, current_body))

    records: list[SectionRecord] = []
    for heading, body in sections:
        body_text = "\n".join(body).strip()
        if not body_text:
            continue
        section_ref = _section_ref(heading) or "Zoning page excerpt"
        records.append(
            SectionRecord(
                section_ref=section_ref,
                heading=heading or "Zoning page excerpt",
                text=(f"{heading}\n{body_text}" if heading else body_text).strip(),
                url=base_url,
                source_type=source_type,
                node_id="",
            )
        )

    if not records and text.strip():
        records.append(
            SectionRecord(
                section_ref="Zoning page excerpt",
                heading="Zoning page excerpt",
                text=text.strip(),
                url=base_url,
                source_type=source_type,
            )
        )
    return records


def _section_ref(heading: str) -> str | None:
    match = re.match(
        r"^(Sec\.?\s*[0-9][0-9A-Za-z.\-]*|Article\s+[IVXLC0-9]+|Chapter\s+[0-9A-Za-z.\-]+)",
        heading.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


class GenericHtmlFetcher:
    """Fetch and clean one or more official zoning pages."""

    name = "generic_html"

    def __init__(
        self,
        urls: list[str],
        *,
        source_type: str = "zoning_ordinance",
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
    ) -> None:
        if not urls:
            raise ValueError("GenericHtmlFetcher requires at least one URL.")
        self.urls = urls
        self.source_type = source_type
        self.cache_dir = cache_dir
        self.request_delay = request_delay

    def fetch(self, *, city: str, state: str) -> FetchResult:
        config = HttpClientConfig(request_delay=self.request_delay, cache_dir=self.cache_dir)
        sections: list[SectionRecord] = []
        with PoliteHttpClient(config) as client:
            for url in self.urls:
                html = client.get_text(url, cache_suffix=".html")
                cleaned = clean_html(html)
                sections.extend(
                    split_into_sections(cleaned, base_url=url, source_type=self.source_type)
                )
        return FetchResult(
            sections=sections,
            source_home_url=self.urls[0],
            provenance={"fetcher": self.name, "urls": list(self.urls)},
        )
