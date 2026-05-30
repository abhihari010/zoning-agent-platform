"""WS1 real document ingestion scraper.

Fetches real municipal zoning ordinance text and writes it into the existing
``source-pack/v1`` manifest format consumed by ``apps/api/app/ingestion.py``.

The public surface is intentionally small:

- :class:`~services.ingestion.scraper.fetchers.base.SectionRecord` — one ordinance
  section (its own ``section_ref``, heading, text, and deep-link URL).
- :class:`~services.ingestion.scraper.fetchers.base.Fetcher` — the protocol every
  concrete fetcher implements.
- :func:`~services.ingestion.scraper.manifest_builder.build_manifest` — turns
  ``SectionRecord``s + jurisdiction info into a schema-valid manifest dict.

See ``README.md`` for the design notes (esp. one-source-per-section).
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
