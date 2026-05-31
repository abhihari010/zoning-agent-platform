from __future__ import annotations

from app.ingestion import import_source_packs
from app.models import SourceRegistryEntry
from app.source_classifier import classify_source


RULES = {
    "rules": [
        {
            "article_contains": "ARTICLE III. - DISTRICT STANDARDS",
            "division_contains": "GENERAL COMMERCIAL",
            "districts": ["unknown", "commercial-employment"],
            "uses": ["general"],
        },
        {
            "article_contains": "ARTICLE IV. - USE AND DESIGN STANDARDS",
            "division_contains": "COMMERCIAL USES",
            "districts": ["unknown"],
            "uses": ["food-service", "food-business", "general"],
        },
    ]
}


def _source(article: str, division: str, title: str = "Sec. 1 - Test") -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id="test-source",
        title=title,
        excerpt="This source has enough text to satisfy source registry validation.",
        section_ref="Sec. 1",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
        metadata={"breadcrumb": ["APPENDIX A", article, division]},
    )


# ---------------------------------------------------------------------------
# Article III district classification
# ---------------------------------------------------------------------------


def test_classify_article_iii_commercial_adds_unknown_and_canonical_district() -> None:
    districts, uses = classify_source(
        _source("ARTICLE III. - DISTRICT STANDARDS", "DIVISION 15. - GENERAL COMMERCIAL DISTRICT"),
        RULES,
    )

    assert districts == ["unknown", "commercial-employment"]
    assert uses == ["general"]


def test_classify_article_iii_residential_r4_maps_to_residential_low_density() -> None:
    districts, uses = classify_source(
        _source(
            "ARTICLE III. - DISTRICT STANDARDS",
            "DIVISION 7. - R-4 LOW DENSITY RESIDENTIAL DISTRICT",
        ),
        {
            "rules": [
                {
                    "article_contains": "ARTICLE III. - DISTRICT STANDARDS",
                    "division_contains": "RESIDENTIAL",
                    "districts": ["unknown", "residential-low-density"],
                    "uses": ["general"],
                }
            ]
        },
    )

    assert districts == ["unknown", "residential-low-density"]
    assert uses == ["general"]


def test_classify_article_iii_otr_maps_to_residential_low_density() -> None:
    districts, uses = classify_source(
        _source(
            "ARTICLE III. - DISTRICT STANDARDS",
            "DIVISION 10. - OTR OLD TOWN RESIDENTIAL DISTRICT",
        ),
        {
            "rules": [
                {
                    "article_contains": "ARTICLE III. - DISTRICT STANDARDS",
                    "division_contains": "RESIDENTIAL",
                    "districts": ["unknown", "residential-low-density"],
                    "uses": ["general"],
                }
            ]
        },
    )

    assert districts == ["unknown", "residential-low-density"]
    assert uses == ["general"]


def test_classify_article_iii_industrial_maps_to_industrial_zone() -> None:
    districts, uses = classify_source(
        _source(
            "ARTICLE III. - DISTRICT STANDARDS",
            "DIVISION 18. - INDUSTRIAL DISTRICT",
        ),
        {
            "rules": [
                {
                    "article_contains": "ARTICLE III. - DISTRICT STANDARDS",
                    "division_contains": "INDUSTRIAL",
                    "districts": ["unknown", "industrial-zone"],
                    "uses": ["general"],
                }
            ]
        },
    )

    assert districts == ["unknown", "industrial-zone"]
    assert uses == ["general"]


def test_classify_article_iii_mixed_use_development_maps_to_mixed_use_core() -> None:
    districts, uses = classify_source(
        _source(
            "ARTICLE III. - DISTRICT STANDARDS",
            "DIVISION 20. - MIXED USE DEVELOPMENT DISTRICT",
        ),
        {
            "rules": [
                {
                    "article_contains": "ARTICLE III. - DISTRICT STANDARDS",
                    "division_contains": "MIXED USE",
                    "districts": ["unknown", "mixed-use-core"],
                    "uses": ["general"],
                }
            ]
        },
    )

    assert districts == ["unknown", "mixed-use-core"]
    assert uses == ["general"]


def test_classify_article_iii_downtown_commercial_maps_to_mixed_use_core() -> None:
    # DOWNTOWN COMMERCIAL must map to mixed-use-core, not commercial-employment.
    # Guards against ordering bugs where a broad "COMMERCIAL" rule fires before
    # the more specific "DOWNTOWN" rule.
    from app.source_classifier import load_classification_rules
    from pathlib import Path

    rules_path = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "data"
        / "source_packs"
        / "va"
        / "blacksburg-va"
    )
    rules = load_classification_rules(rules_path / "manifest.json")

    districts, uses = classify_source(
        _source(
            "ARTICLE III. - DISTRICT STANDARDS",
            "DIVISION 16. - DOWNTOWN COMMERCIAL DISTRICT",
        ),
        rules,
    )

    assert "mixed-use-core" in districts
    assert "commercial-employment" not in districts


# ---------------------------------------------------------------------------
# Article IV use classification
# ---------------------------------------------------------------------------


def test_classify_article_iv_commercial_uses_adds_food_use_tags() -> None:
    districts, uses = classify_source(
        _source("ARTICLE IV. - USE AND DESIGN STANDARDS", "DIVISION 5. - COMMERCIAL USES"),
        RULES,
    )

    assert districts == ["unknown"]
    assert uses == ["food-service", "food-business", "general"]


def test_classify_article_iv_restaurant_title_adds_food_service() -> None:
    districts, uses = classify_source(
        _source(
            "ARTICLE IV. - USE AND DESIGN STANDARDS",
            "DIVISION 5. - COMMERCIAL USES",
            title="Sec. 4555 - Restaurant, small",
        ),
        RULES,
    )

    assert "food-service" in uses
    assert "food-business" in uses
    assert "general" in uses


# ---------------------------------------------------------------------------
# Cross-cutting articles (I, II, V) — stay unknown/general
# ---------------------------------------------------------------------------


def test_classify_article_i_admin_stays_unknown_general() -> None:
    districts, uses = classify_source(
        _source("ARTICLE I. - IN GENERAL", "DIVISION 1. - GENERALLY", "Sec. 1100 - Authority and citation."),
        RULES,
    )

    assert districts == ["unknown"]
    assert uses == ["general"]


def test_classify_article_ii_definitions_stays_unknown_general() -> None:
    districts, uses = classify_source(
        _source("ARTICLE II. - DEFINITIONS", "DIVISION 1. - GENERALLY", "Sec. 2103 - Definitions."),
        RULES,
    )

    assert districts == ["unknown"]
    assert uses == ["general"]


def test_classify_article_v_development_standards_stays_unknown_general() -> None:
    districts, uses = classify_source(_source("ARTICLE V. - DEVELOPMENT STANDARDS", "DIVISION 1"), RULES)

    assert districts == ["unknown"]
    assert uses == ["general"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_classify_unknown_breadcrumb_falls_back_to_wildcards() -> None:
    source = SourceRegistryEntry(
        source_id="no-breadcrumb",
        title="Sec. 99 - No breadcrumb",
        excerpt="This source has enough text to satisfy source registry validation.",
        section_ref="Sec. 99",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
        metadata={},  # no breadcrumb at all
    )
    districts, uses = classify_source(source, RULES)

    assert districts == ["unknown"]
    assert uses == ["general"]


def test_classify_none_rules_returns_defaults() -> None:
    districts, uses = classify_source(
        _source("ARTICLE III. - DISTRICT STANDARDS", "DIVISION 15. - GENERAL COMMERCIAL DISTRICT"),
        None,
    )

    assert districts == ["unknown"]
    assert uses == ["general"]


# ---------------------------------------------------------------------------
# Integration — Blacksburg pack import
# ---------------------------------------------------------------------------


def test_blacksburg_pack_import_enriches_scraped_sections_additively() -> None:
    entries = {entry.source_id: entry for entry in import_source_packs()}

    assert entries["blacksburg-va-sec-3151"].districts == ["unknown", "commercial-employment"]
    assert entries["blacksburg-va-sec-4555"].districts == ["unknown"]
    assert "food-service" in entries["blacksburg-va-sec-4555"].uses
    assert entries["blacksburg-va-sec-2103"].districts == ["unknown"]
    assert entries["blacksburg-va-sec-2103"].uses == ["general"]
