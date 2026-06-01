from __future__ import annotations

import json
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
            return (
                _string_list(rule.get("districts")) or DEFAULT_DISTRICTS,
                _string_list(rule.get("uses")) or DEFAULT_USES,
            )
    return DEFAULT_DISTRICTS, DEFAULT_USES


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
