"""Fetcher protocol and the shared :class:`SectionRecord` value object.

A *fetcher* knows how to pull the zoning code for one jurisdiction from one kind
of host (Municode, a plain HTML page, etc.) and return a flat list of
:class:`SectionRecord`.  Each record becomes exactly one source in the emitted
``source-pack/v1`` manifest — see ``README.md`` for why we emit one source per
ordinance section rather than one blob per ordinance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class SectionRecord:
    """A single ordinance section ready to become one manifest source.

    Attributes:
        section_ref: Human-citable reference, e.g. ``"Sec. 4211"``.  Must be
            non-empty; the schema validator rejects blank ``section_ref``.
        heading: Full heading text, e.g. ``"Sec. 4211 - Home occupations."``.
        text: Clean plain-text body of the section (no HTML).
        url: Deep-link/anchor URL to this section on the official host.
        source_type: One of ``scripts.validate_source_packs.ALLOWED_SOURCE_TYPES``;
            defaults to ``"zoning_ordinance"``.
        node_id: Opaque host identifier (e.g. Municode ``nodeId``) for traceability.
        effective_date: ISO date the ordinance was codified/adopted, if known.
        breadcrumb: Ordered ancestor headings (Article -> Division), for context.
        metadata: Free-form extra metadata merged into the manifest source.
    """

    section_ref: str
    heading: str
    text: str
    url: str
    source_type: str = "zoning_ordinance"
    node_id: str = ""
    effective_date: str | None = None
    breadcrumb: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass(slots=True)
class FetchResult:
    """What a fetcher returns: the records plus host-level provenance."""

    sections: list[SectionRecord]
    source_home_url: str
    effective_date: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Fetcher(Protocol):
    """Every concrete fetcher implements this."""

    name: str

    def fetch(self, *, city: str, state: str) -> FetchResult:
        """Return the ordinance sections for ``city, state``.

        Implementations should be polite (rate-limit, retry with backoff,
        cache raw responses on disk) and must raise a descriptive exception
        rather than hammering a host that blocks automated access.
        """
        ...
