"""HTML -> clean plain text, preserving paragraph and list structure.

Used by every fetcher to turn ordinance HTML fragments (Municode ``Content``
blocks, or a generic zoning page body) into the plain text stored in
``full_text``.  We avoid pulling in BeautifulSoup/lxml — the input is small,
well-formed-enough fragments, and the standard-library ``html.parser`` plus a
little normalization is sufficient and dependency-free.

Goals:
- Drop ``<script>``/``<style>``/``<nav>``/``<header>``/``<footer>`` boilerplate.
- Insert paragraph breaks for block-level elements so list items and clauses
  (e.g. ``(a)``, ``(b)``) stay on their own lines.
- Collapse runs of whitespace inside a line; collapse blank-line runs.
- Decode HTML entities.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Tags whose entire content is discarded.
_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "form", "button"}

# Block-level tags that should force a line break around their text.
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "tr",
    "table",
    "section",
    "article",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _normalize(text: str) -> str:
    # Normalize non-breaking spaces and similar before collapsing.
    text = text.replace("\xa0", " ").replace("​", "")
    lines = []
    for raw_line in text.split("\n"):
        collapsed = re.sub(r"[ \t\r\f\v]+", " ", raw_line).strip()
        lines.append(collapsed)

    # Collapse 2+ consecutive blank lines into a single blank line.
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


def clean_html(html: str) -> str:
    """Convert an HTML fragment/document to clean plain text."""
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return _normalize(parser.get_text())
