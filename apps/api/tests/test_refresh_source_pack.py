from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "refresh_source_pack", REPO_ROOT / "scripts" / "refresh_source_pack.py"
)
assert spec and spec.loader
refresher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = refresher
spec.loader.exec_module(refresher)


def _source(source_id: str, **fields) -> dict:
    return {"source_id": source_id, "title": source_id, "districts": ["unknown"], "metadata": {}, **fields}


def test_refresh_keeps_curation_and_real_dates() -> None:
    curated = {
        "jurisdiction": {"coverage_status": "public_supported"},
        "sources": [
            _source(
                "a",
                districts=["agricultural"],
                full_text="old",
                retrieved_at="2026-06-01",
                effective_date="2024-02-26",
                metadata={"effective_date_source": "history_note", "use_standards": True},
            ),
            _source("ref-link", full_text="", retrieved_at="2026-08-01"),
        ],
    }
    draft = {
        "jurisdiction": {"coverage_status": "source_indexed"},
        "sources": [
            _source(
                "a",
                full_text="new",
                retrieved_at="2026-10-09",
                effective_date="2026-10-09",
                metadata={"effective_date_source": "retrieval_date", "scraper": "municode"},
            ),
            _source("b", full_text="added upstream", retrieved_at="2026-10-09"),
        ],
    }

    report = refresher.refresh(curated, draft)

    a, ref_link, b = curated["sources"]
    assert curated["jurisdiction"]["coverage_status"] == "public_supported"
    assert a["districts"] == ["agricultural"]
    assert (a["full_text"], a["retrieved_at"]) == ("new", "2026-10-09")
    # A scraper fallback date must not overwrite a date the page actually stated.
    assert a["effective_date"] == "2024-02-26"
    assert a["metadata"] == {
        "effective_date_source": "history_note",
        "use_standards": True,
        "scraper": "municode",
    }
    assert ref_link["retrieved_at"] == "2026-08-01"
    assert b["full_text"] == "added upstream"
    assert report == {
        "refreshed": 1,
        "text_changed": ["a"],
        "added": ["b"],
        "kept_unscraped": ["ref-link"],
    }


def test_refresh_matches_by_url_when_ids_swap() -> None:
    # Winchester's zoning and subdivision ordinances both have a "Sec. 5-1"; the
    # scraper's collision suffix flipped between scrapes, so ids alone would put
    # subdivision text under the zoning section's district tags.
    zoning_url = "https://example.test/code?nodeId=ZO_S5-1"
    subdivision_url = "https://example.test/code?nodeId=SUOR_S5-1"
    curated = {
        "sources": [
            _source("w-5-1", url=zoning_url, title="Sec. 5-1. - Use regulations.",
                    districts=["residential"], full_text="uses"),
            _source("w-5-1-12", url=subdivision_url, title="Sec. 5-1. - Mutual responsibility.",
                    full_text="mutual"),
        ]
    }
    draft = {
        "sources": [
            _source("w-5-1", url=subdivision_url, title="Sec. 5-1. - Mutual responsibility.",
                    full_text="mutual v2"),
            _source("w-5-1-2", url=zoning_url, title="Sec. 5-1. - Use regulations.",
                    full_text="uses v2"),
        ]
    }

    report = refresher.refresh(curated, draft)

    zoning, subdivision = curated["sources"]
    assert (zoning["source_id"], zoning["full_text"], zoning["districts"]) == (
        "w-5-1", "uses v2", ["residential"],
    )
    assert (subdivision["source_id"], subdivision["full_text"]) == ("w-5-1-12", "mutual v2")
    assert report["added"] == [] and report["kept_unscraped"] == []
