from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.models import SourceRegistryEntry


DEFAULT_DISTRICTS = ["unknown"]
DEFAULT_USES = ["general"]


def load_classification_rules(pack_path: Path) -> dict[str, Any] | None:
    rules_path = pack_path.with_name("classification_rules.json")
    if not rules_path.exists():
        return None
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def classify_source(source: SourceRegistryEntry, rules: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not rules:
        return DEFAULT_DISTRICTS, DEFAULT_USES

    breadcrumb = source.metadata.get("breadcrumb")
    if not isinstance(breadcrumb, list):
        breadcrumb = []
    article = str(breadcrumb[1]) if len(breadcrumb) > 1 else ""
    division = str(breadcrumb[2]) if len(breadcrumb) > 2 else ""
    title = source.title or ""
    haystack = " ".join([article, division, title]).lower()

    for rule in rules.get("rules", []):
        if not isinstance(rule, dict):
            continue
        if _matches(rule, article, division, title, haystack):
            districts = _string_list(rule.get("districts")) or DEFAULT_DISTRICTS
            return _with_district_code(districts, rule, article, division, title), (
                _string_list(rule.get("uses")) or DEFAULT_USES
            )
    return DEFAULT_DISTRICTS, DEFAULT_USES


# "DIVISION 10. - R-53 MULTIFAMILY RESIDENTIAL DISTRICT" -> R-53, and
# "ARTICLE 8 - HIGHWAY COMMERCIAL DISTRICT-B-2" -> B-2.
_NUMBERING = re.compile(
    r"^[^A-Za-z0-9]*(?:(?:ARTICLE|SEC|SECTION|DIVISION|CHAPTER|APPENDIX)\.?\s*)?"
    r"[0-9IVX][0-9IVX.\-]*[A-Z]?\s*[:.\-—]\s*",
    re.I,
)
_AFTER_DISTRICT = re.compile(r"(?:DISTRICT|ZONE)S?\W{1,3}([A-Z0-9][A-Z0-9\-]{0,7})(?![A-Za-z0-9])")
_CODE_SHAPE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]{0,7}$")
# Ordinary heading words share the shape of a short code, so a bare candidate only
# counts as a code when it carries a digit or a separator, or is very short.
_NOT_A_CODE = {"USE", "USES", "THE", "AND", "FOR", "ALL", "ANY", "NEW", "LOT",
               "LOTS", "MAP", "MAPS", "AREA", "PART", "PLAN", "SIGN", "SIGNS",
               "LOW", "HIGH", "OLD", "ONE", "TWO", "MID", "SUB", "NON"}


def _with_district_code(
    districts: list[str], rule: dict[str, Any], article: str, division: str, title: str
) -> list[str]:
    """Append the district's own code (``R-1``) alongside its coarse family.

    The coarse vocabulary lumps every R district together, so a question about R-1
    boosts all of them equally and the right section has to win on wording alone.
    The heading the rule matched on already names the district, so the precise code
    is free -- and carrying BOTH keeps every existing family-level match working.
    """

    if not districts or districts == DEFAULT_DISTRICTS:
        return districts
    for source_text in (rule.get("division_contains"), rule.get("article_contains"), division, article, title):
        code = _district_code(str(source_text or ""))
        if code and code not in districts:
            return [*districts, code]
    return districts


def _district_code(heading: str) -> str | None:
    if not heading:
        return None
    body = heading
    previous = None
    while previous != body:
        previous = body
        body = _NUMBERING.sub("", body, count=1).lstrip(" -—:.")
    # "...RESIDENTIAL DISTRICT-LR" names the code after the word, and that beats the
    # leading token, which there is the adjective "LOW".
    match = _AFTER_DISTRICT.search(heading.upper())
    if match and _is_code(match.group(1)):
        return match.group(1)
    lead = re.split(r"[\s,;:()�—–]+", body.strip())
    candidate = lead[0].strip(".-/") if lead and lead[0] else ""
    return candidate if _is_code(candidate) else None


def _is_code(candidate: str) -> bool:
    if not _CODE_SHAPE.match(candidate) or not any(ch.isalpha() for ch in candidate):
        return False
    if candidate in _NOT_A_CODE:
        return False
    return any(ch.isdigit() for ch in candidate) or "-" in candidate or len(candidate) <= 4


def _matches(rule: dict[str, Any], article: str, division: str, title: str, haystack: str) -> bool:
    article_contains = str(rule.get("article_contains") or "").lower()
    division_contains = str(rule.get("division_contains") or "").lower()
    title_contains = str(rule.get("title_contains") or "").lower()
    any_contains = str(rule.get("contains") or "").lower()

    if article_contains and article_contains not in article.lower():
        return False
    if division_contains and division_contains not in division.lower():
        return False
    if title_contains and title_contains not in title.lower():
        return False
    if any_contains and any_contains not in haystack:
        return False
    return bool(article_contains or division_contains or title_contains or any_contains)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
