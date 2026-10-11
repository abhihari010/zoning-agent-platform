"""Fetcher for an ordinance published as one PDF with a "§"-numbered table of contents.

Some codes (Arlington County, VA) exist only as a single PDF. Its table of
contents lists every section as ``§5.6. R-6, One-Family Dwelling District ..... 5-12``,
and each section opens in the body with the same ``§5.6.`` heading line, so the
TOC is the split map: one :class:`SectionRecord` per TOC entry. Each record links
to the PDF page it starts on (``#page=N``).

Use tables are the part plain text extraction destroys. Their district columns
are labelled with rotated text and a blank cell means "not allowed", so a text
dump either drops the column labels or collapses the blanks -- either way a "P"
can no longer be tied to its district. :func:`_table_rows` rebuilds each such
table from character positions: the rotated labels give the columns and the
table's own ruling lines give the rows, emitted as ``|``-delimited lines the
chunker already knows how to carry.

``pdfplumber`` is an optional dependency, imported only when this fetcher runs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..http_client import HttpClientConfig, PoliteHttpClient
from .base import FetchResult, SectionRecord

# Running header and footer bands (points from the top / bottom edge).
_TOP_MARGIN = 60.0
_BOTTOM_MARGIN = 57.0
_TOC_ENTRY_RE = re.compile(r"^§\s*(\d+\.\d+)\.?\s+(.+?)\s*(?:\.\s?){3,}\s*\S+$")
_HEADING_RE = re.compile(r"^§\s*(\d+\.\d+)\.\s+(.+)$")
_EFFECTIVE_RE = re.compile(r"\bEffective\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})")
_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_SNAP = 4.0  # points; table borders are drawn as thin rectangles, i.e. doubled lines


def _merge(values: list[float]) -> list[float]:
    merged: list[float] = []
    for value in sorted(values):
        if not merged or value - merged[-1] > _SNAP:
            merged.append(value)
    return merged


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _cell_text(words: list[dict[str, Any]]) -> str:
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    return " ".join(w["text"] for w in words).replace("|", "/").strip()


def _header_bands(page: Any) -> list[list[dict[str, Any]]]:
    """Group a page's rotated characters into header bands, one per table."""

    bands: list[list[dict[str, Any]]] = []
    for char in sorted((c for c in page.chars if abs(c["matrix"][1]) > 0.5), key=lambda c: c["top"]):
        if bands and char["top"] <= max(c["bottom"] for c in bands[-1]) + 10:
            bands[-1].append(char)
        else:
            bands.append([char])
    return [band for band in bands if sum(1 for c in band if c["text"].strip()) >= 3]


def _table_rows(page: Any, rotated: list[dict[str, Any]], limit: float) -> tuple[list[str], tuple[float, float] | None]:
    """Rebuild the table under one band of rotated column labels; return its rows and y-span.

    Columns: one per rotated label, split at the midpoints between labels, with
    the label area to the left and a trailing notes column to the right. Rows:
    the horizontal rules that cross the first labelled column. A cell in the
    left-most column that spans several rows (a use category beside its use
    types) is resolved through the rules that cross that column instead.
    """

    labels: dict[int, list[dict[str, Any]]] = {}
    for char in rotated:
        labels.setdefault(round(char["x0"]), []).append(char)
    columns = []
    for x in sorted(labels):
        chars = sorted(labels[x], key=lambda c: -c["top"])  # rotated text reads bottom-up
        label = " ".join("".join(c["text"] for c in chars).split())
        if label:
            columns.append((x + chars[0]["width"] / 2, label))
    if len(columns) < 3:
        return [], None
    rotated = [c for c in rotated if c["text"].strip()]
    header_top = min(c["top"] for c in rotated)
    header_bottom = max(c["bottom"] for c in rotated)
    centers = [x for x, _ in columns]
    pitch = (centers[-1] - centers[0]) / max(len(centers) - 1, 1)
    bounds = [centers[0] - pitch / 2] + [(a + b) / 2 for a, b in zip(centers, centers[1:])] + [centers[-1] + pitch / 2]

    def rules_crossing(x: float) -> list[float]:
        return _merge([e["top"] for e in page.edges if e["orientation"] == "h"
                       and e["x0"] <= x <= e["x1"] and header_bottom < e["top"] < limit])

    # Only rules inside the table: a page frame is drawn as vertical lines too.
    table_left = min((e["x0"] for e in page.edges if e["orientation"] == "h"
                      and e["x0"] <= centers[0] <= e["x1"] and header_bottom < e["top"] < limit), default=None)
    if table_left is None:
        return [], None
    words = [w for w in page.extract_words(keep_blank_chars=False, extra_attrs=["upright"])
             if w["upright"] and header_bottom - 1 <= w["top"] < limit]
    left_edges = _merge([e["x0"] for e in page.edges if e["orientation"] == "v"
                         and table_left - _SNAP <= e["x0"] < bounds[0] - _SNAP and e["bottom"] > header_bottom])
    # The left-most column of a two-column label area holds merged category cells.
    split_x = left_edges[1] if len(left_edges) >= 2 else None
    category_y = rules_crossing((left_edges[0] + split_x) / 2) if split_x else []
    # Rows come from the rules crossing the use column: a cell that stacks two values
    # ("P" over "S") is ruled inside, which would split one use into two rows.
    rows_y = rules_crossing(((split_x or table_left) + bounds[0]) / 2)
    if len(rows_y) < 2:
        return [], None

    def merged(top: float, bottom: float) -> bool:
        # No column rule crosses a full-width row (a KEY legend or a category banner).
        mid = (top + bottom) / 2
        return not any(e["orientation"] == "v" and bounds[0] - _SNAP < e["x0"] < bounds[-1] + _SNAP
                       and e["top"] <= mid <= e["bottom"] for e in page.edges)

    def in_band(word: dict[str, Any], top: float, bottom: float) -> bool:
        mid = (word["top"] + word["bottom"]) / 2
        return top <= mid < bottom

    def inside(top: float, bottom: float) -> bool:
        # Some rule of the table crosses every one of its rows, banners included
        # (their outer border); the first band none crosses is the page after it.
        mid = (top + bottom) / 2
        return any(e["orientation"] == "v" and table_left - _SNAP <= e["x0"] <= bounds[-1] + 3 * pitch
                   and e["top"] <= mid <= e["bottom"] for e in page.edges)

    header = ["Use Category", "Specific Use Types"] if split_x else ["Use"]
    lines = ["| " + " | ".join(header + [label for _, label in columns] + ["Use Standards"]) + " |"]
    end = rows_y[0]
    for top, bottom in zip(rows_y, rows_y[1:]):
        if not inside(top, bottom):
            break
        end = bottom
        band = [w for w in words if in_band(w, top, bottom)]
        if not band:
            continue
        if merged(top, bottom):
            lines.append(f"| {_cell_text(band)} |")
            continue
        mid = (top + bottom) / 2
        label_words = [w for w in band if w["x0"] < bounds[0]]
        cells = [_cell_text([w for w in band if lo <= w["x0"] < hi]) for lo, hi in zip(bounds, bounds[1:])]
        notes = _cell_text([w for w in band if w["x0"] >= bounds[-1]])
        if split_x:
            category = ""
            for c_top, c_bottom in zip(category_y, category_y[1:]):
                if c_top <= mid < c_bottom:
                    category = _cell_text([w for w in words if w["x0"] < split_x and in_band(w, c_top, c_bottom)])
            use = _cell_text([w for w in label_words if w["x0"] >= split_x])
            prefix = [category, use]
        else:
            prefix = [_cell_text(label_words)]
        lines.append("| " + " | ".join(prefix + cells + [notes]) + " |")
    return lines, (header_top, end)


def page_text(page: Any) -> str:
    """One page's body text, with any rotated-label table rebuilt as ``|`` rows."""

    top, bottom = _TOP_MARGIN, page.height - _BOTTOM_MARGIN
    body = page.crop((0, top, page.width, bottom))
    bands = _header_bands(body)
    parts: list[str] = []
    cursor = top
    for index, band in enumerate(bands):
        limit = min(c["top"] for c in bands[index + 1]) if index + 1 < len(bands) else bottom
        table, span = _table_rows(body, band, limit)
        if not span:
            continue
        # Between the text above and the first row sit only the rotated labels,
        # which the rebuilt header row replaces.
        if span[0] - 1 > cursor:
            parts.append(body.crop((0, cursor, page.width, span[0] - 1)).extract_text() or "")
        parts.append("\n".join(table))
        cursor = max(cursor, min(span[1], bottom - 1))
    parts.append(body.crop((0, cursor, page.width, bottom)).extract_text() or "")
    return "\n".join(part for part in parts if part)


def split_sections(pages: list[str], *, url: str) -> list[SectionRecord]:
    """Split page texts into one record per table-of-contents entry."""

    toc: dict[str, str] = {}
    toc_pages: set[int] = set()
    for index, text in enumerate(pages):
        for line in text.splitlines():
            match = _TOC_ENTRY_RE.match(line.strip())
            if match:
                toc.setdefault(match.group(1), match.group(2))
                toc_pages.add(index)

    records: list[SectionRecord] = []
    current: tuple[str, str, int] | None = None
    body: list[str] = []

    def flush() -> None:
        if current and "\n".join(body).strip():
            number, title, page_no = current
            records.append(SectionRecord(
                section_ref=f"§{number}",
                heading=f"§{number}. {title}",
                text="\n".join(body).strip(),
                url=f"{url}#page={page_no}",
                node_id=number,
            ))

    for index, text in enumerate(pages):
        if index in toc_pages:
            continue
        for line in text.splitlines():
            match = _HEADING_RE.match(line.strip())
            # A wrapped cross-reference can also open a line with "§13.13."; only
            # the heading carries the TOC's own title after it.
            if (match and match.group(1) in toc
                    and _squash(match.group(2)).startswith(_squash(toc[match.group(1)])[:12])
                    and (not current or match.group(1) != current[0])):
                flush()
                current = (match.group(1), toc[match.group(1)], index + 1)
                body = [line.strip()]
            elif current:
                body.append(line)
    flush()
    return records


def effective_date(text: str) -> str | None:
    match = _EFFECTIVE_RE.search(text)
    if not match or match.group(1).lower() not in _MONTHS:
        return None
    return f"{match.group(3)}-{_MONTHS.index(match.group(1).lower()) + 1:02d}-{int(match.group(2)):02d}"


class PdfFetcher:
    """Fetch one ordinance PDF and split it on its table of contents."""

    name = "pdf"

    def __init__(
        self,
        url: str,
        *,
        cache_dir: Path | None = None,
        request_delay: float = 1.0,
        impersonate: str | None = None,
        max_sections: int | None = None,
    ) -> None:
        self.url = url
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.impersonate = impersonate
        self.max_sections = max_sections

    def fetch(self, *, city: str, state: str) -> FetchResult:
        try:
            import pdfplumber
        except ImportError as exc:  # pragma: no cover - exercised via message
            raise ImportError("The pdf fetcher needs pdfplumber: pip install pdfplumber") from exc
        import io

        config = HttpClientConfig(
            request_delay=self.request_delay,
            cache_dir=self.cache_dir,
            impersonate=self.impersonate,
            timeout=180.0,
        )
        with PoliteHttpClient(config) as client:
            data = client.get_bytes(self.url, cache_suffix=".pdf")
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page_text(page) for page in pdf.pages]
            # The cover's "Effective <date>" sits where body pages carry their footer.
            cover = pdf.pages[0].extract_text() or ""
        sections = split_sections(pages, url=self.url)
        if self.max_sections:
            sections = sections[: self.max_sections]
        return FetchResult(
            sections=sections,
            source_home_url=self.url,
            effective_date=effective_date(cover),
            provenance={"fetcher": self.name, "url": self.url, "pages": len(pages)},
        )
