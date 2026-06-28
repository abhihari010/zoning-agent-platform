from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from services.ingestion.scraper.fetchers.base import SectionRecord
from services.ingestion.scraper.manifest_builder import build_manifest

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_validator():
    path = _REPO_ROOT / "scripts" / "validate_source_packs.py"
    spec = importlib.util.spec_from_file_location("_ws1_validator", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sample_records() -> list[SectionRecord]:
    return [
        SectionRecord(
            section_ref="Sec. 4211",
            heading="Sec. 4211 - Home occupations.",
            text=(
                "(a) Intent. Under certain unique circumstances a small-scaled "
                "commercial activity may be appropriate within a residential dwelling. "
                "(b) General standards: the home occupation shall be limited in scope."
            ),
            url="https://library.municode.com/va/blacksburg/codes/code_of_ordinances?nodeId=S4211HOOC",
            node_id="S4211HOOC",
            effective_date="2025-12-09",
            breadcrumb=["ARTICLE IV. - USE AND DESIGN STANDARDS"],
        ),
        SectionRecord(
            section_ref="Sec. 4216",
            heading="Sec. 4216 - Multifamily dwelling.",
            text="Multifamily dwellings shall comply with the following density and design standards.",
            url="https://library.municode.com/va/blacksburg/codes/code_of_ordinances?nodeId=S4216MUDW",
            node_id="S4216MUDW",
            effective_date="2025-12-09",
        ),
    ]


def test_build_manifest_one_source_per_section():
    manifest = build_manifest(
        city="Blacksburg",
        state="VA",
        county="Montgomery",
        records=_sample_records(),
        effective_date="2025-12-09",
        provenance={"fetcher": "municode", "source_home_url": "https://library.municode.com/va/blacksburg/codes/code_of_ordinances"},
    )
    assert manifest["schema_version"] == "source-pack/v1"
    assert manifest["jurisdiction"]["jurisdiction_id"] == "blacksburg-va"
    assert manifest["jurisdiction"]["coverage_status"] == "source_indexed"
    assert manifest["jurisdiction"]["parent_jurisdiction_id"] == "montgomery-county-va"
    assert len(manifest["sources"]) == 2

    first = manifest["sources"][0]
    assert first["section_ref"] == "Sec. 4211"
    assert first["full_text"]
    assert first["excerpt"]
    assert first["source_type"] == "zoning_ordinance"
    assert first["url"].endswith("nodeId=S4211HOOC")
    assert first["jurisdiction_id"] == "blacksburg-va"


def test_build_manifest_drops_too_short_sections():
    # A stub section whose body normalises to under the SourceRegistryEntry
    # excerpt minimum (10 chars) must be dropped so the pack stays ingestible.
    records = _sample_records() + [
        SectionRecord(
            section_ref="Sec. 11-5",
            heading="Sec. 11-5 - Penalties.",
            text="None.",
            url="https://library.municode.com/va/winchester/codes/zoning?nodeId=S11-5",
            node_id="S11-5",
        )
    ]
    manifest = build_manifest(city="Winchester", state="VA", records=records)
    refs = {s["section_ref"] for s in manifest["sources"]}
    assert "Sec. 11-5" not in refs
    assert len(manifest["sources"]) == 2
    assert all(len(s["excerpt"]) >= 10 for s in manifest["sources"])


def test_unique_source_ids_even_for_duplicate_section_refs():
    records = _sample_records()
    records.append(records[0])  # duplicate Sec. 4211
    manifest = build_manifest(city="Blacksburg", state="VA", records=records)
    ids = [s["source_id"] for s in manifest["sources"]]
    assert len(ids) == len(set(ids))


def test_effective_date_falls_back_to_retrieval_when_unknown():
    records = [
        SectionRecord(
            section_ref="Sec. 1",
            heading="Sec. 1 - Foo.",
            text="Some ordinance text that is long enough to matter for chunking.",
            url="https://library.municode.com/va/blacksburg/codes/code_of_ordinances?nodeId=N1",
        )
    ]
    manifest = build_manifest(city="Blacksburg", state="VA", records=records)
    src = manifest["sources"][0]
    assert src["effective_date"]  # non-empty (retrieval date)
    assert src["metadata"]["effective_date_source"] == "retrieval_date"


def test_manifest_passes_real_validator(tmp_path):
    validator = _load_validator()
    manifest = build_manifest(
        city="Blacksburg",
        state="VA",
        county="Montgomery",
        records=_sample_records(),
        effective_date="2025-12-09",
        provenance={"fetcher": "municode"},
    )
    pack_dir = tmp_path / "va" / "blacksburg-va"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = validator.validate_source_packs(tmp_path)
    assert result.ok, [f"{i.path}: {i.message}" for i in result.errors]
