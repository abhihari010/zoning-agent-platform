"""Test configuration for the WS1 scraper.

Adds the repo root to ``sys.path`` so ``import services.ingestion.scraper...``
resolves when running ``python -m pytest services/ingestion/scraper/tests`` from
the repo root, and exposes the fixtures directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")
