"""Test configuration for scripts/tests.

Adds the repo root to ``sys.path`` so ``import scripts.batch_scrape`` and
``import services.ingestion.scraper...`` resolve when running::

    python -m pytest scripts/tests -q

from the repo root.

Also redirects pytest's tmp_path base to a writable location under the
project root, since ``C:\\Users\\...\\AppData\\Local\\Temp\\pytest-of-*``
may be access-denied on some Windows configurations.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Redirect pytest tmp dirs to a writable location under the project tree.
_TMP_BASE = _REPO_ROOT / ".tmp" / "pytest-scripts-tests"
_TMP_BASE.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def tmp_path_factory(tmp_path_factory):
    """Override the session-scoped factory to use a writable base dir."""
    tmp_path_factory._basetemp = _TMP_BASE
    return tmp_path_factory
