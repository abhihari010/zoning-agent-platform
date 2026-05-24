from __future__ import annotations

import os
from pathlib import Path

import pytest

from .runner import assert_expectations, load_scenarios, run_scenario, write_trace


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda scenario: scenario["id"])
def test_golden_scenario(scenario: dict) -> None:
    run = run_scenario(scenario)
    assert_expectations(run, scenario)

    trace_dir = os.getenv("GOLDEN_TRACE_DIR")
    if trace_dir:
        write_trace(run, Path(trace_dir))
