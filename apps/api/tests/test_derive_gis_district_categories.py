from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "derive_gis_district_categories", REPO_ROOT / "scripts" / "derive_gis_district_categories.py"
)
assert spec and spec.loader
derive = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = derive
spec.loader.exec_module(derive)


def test_heading_led_by_a_roman_looking_code_still_defines_it():
    # LEAD reads a leading "I-" as a roman numeral; Fairfax's industrial districts
    # went unmapped because "I-2 Low ..." was stripped to "2 Low ...".
    assert derive.defines("I-2 Low Intensity Industrial District", "I-2")
    assert derive.defines("I-I Industrial Institutional District", "I-I")


def test_dotted_subsection_number_is_not_a_district_code():
    # "4102.5.II" is subsection II of 4102.5; it mapped I-I to commercial.
    assert not derive.defines("4102.5.II Retail Sales, Large", "I-I")


def test_outline_table_name_stops_at_the_line_end():
    # Nashville's "A. Agricultural Districts: AG, AR2a. / B. Residential Districts:".
    text = "A.\nAgricultural Districts: AG, AR2a.\nB.\nResidential Districts:\n1.\nSingle-Family Districts:\na.\nRS80 (80,000 square foot lot)."
    sources = [{"title": "17.08.010 - Zoning districts established.", "full_text": text}]
    found = derive.established_table(sources, ["AG", "RS80"])
    assert found["AG"][0] == "agricultural"
    assert found["RS80"][0] == "residential-low-density"
