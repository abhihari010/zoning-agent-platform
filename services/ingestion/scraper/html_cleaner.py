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
- Delimit ``<td>``/``<th>`` with ``|`` so a use table's empty cells hold their
  column position.  Without this, ``<td></td>`` contributes nothing and a use
  row flattens to ``Antique Shop/Dealers P P P P P P`` — six symbols against 27
  district columns, with no way to tell which six.
- Resolve permission-symbol ``<img>`` (Municode renders P/PL/CU/NP as PNGs in
  some codes) to its filename stem, so the grid survives at all.
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

# Table cells get a delimiter instead of a line break, so an empty cell still
# occupies a column.  Block tags *inside* a cell (Municode wraps cell text in
# <p>) collapse to a space, so one table row stays on one line.
_CELL_TAGS = {"td", "th"}
_CELL_SEP = " | "

# An <img> standing in for a table symbol resolves to its filename stem
# ("np.png" -> "np").  Anything longer is a logo/diagram, not a symbol.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9/*+-]{1,4}$")

_WS_RE = re.compile(r"\s+")


def _image_symbol(attrs: list[tuple[str, str | None]]) -> str:
    attr = dict(attrs)
    raw = attr.get("data-image-filename") or attr.get("alt") or attr.get("src") or ""
    stem = raw.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()
    return stem if _SYMBOL_RE.match(stem) else ""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._cell_depth = 0

    def _break(self) -> None:
        # Inside a cell a block tag must not end the row's line.
        self._parts.append(" " if self._cell_depth else "\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _CELL_TAGS:
            self._cell_depth += 1
        elif tag in _BLOCK_TAGS:
            self._break()
        elif tag == "img" and self._skip_depth == 0:
            self._parts.append(_image_symbol(attrs))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag in _SKIP_TAGS or tag in _CELL_TAGS:
            # Self-closing, so it never reaches handle_endtag to be balanced.
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _CELL_TAGS:
            self._cell_depth = max(0, self._cell_depth - 1)
            self._parts.append(_CELL_SEP)
        elif tag in _BLOCK_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            # Whitespace in the source is insignificant in HTML; only the tags
            # above decide where a line ends.  Municode indents its markup, so
            # leaving raw newlines in would put every <td> on its own line.
            self._parts.append(_WS_RE.sub(" ", data))

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
