from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models import ParcelResult
from app.tools import parcel_gis


PARCEL_FIXTURES_PATH = Path(__file__).resolve().parents[1] / "data" / "parcel_fixtures.json"


class ParcelTool:
    """Look up parcel and zoning district using local fixtures first."""

    def lookup(
        self,
        address: str,
        lat: float | None,
        lng: float | None,
        jurisdiction_id: str,
    ) -> ParcelResult:
        fixture = _fixture_match(address, jurisdiction_id)
        if fixture is not None:
            return ParcelResult(
                parcel_id=fixture.get("parcel_id"),
                zoning_district=fixture.get("zoning_district"),
                zoning_code=fixture.get("zoning_code"),
                overlays=list(fixture.get("overlays") or []),
                confidence=float(fixture.get("confidence", 0.9)),
                method=str(fixture.get("method", "fixture")),
                warnings=[],
            )

        gis = parcel_gis.lookup(jurisdiction_id, lat, lng)
        if gis is not None:
            attribution = f" ({gis.attribution})" if gis.attribution else ""
            if gis.district:
                return ParcelResult(
                    parcel_id=gis.parcel_id,
                    zoning_district=gis.district,
                    zoning_code=gis.zoning_code,
                    overlays=[],
                    confidence=0.9,
                    method="gis_lookup",
                    warnings=[],
                )
            # The parcel is real but its code is not mapped to a category yet, so the
            # district stays unresolved rather than being guessed at.
            return ParcelResult(
                parcel_id=gis.parcel_id,
                zoning_district=None,
                zoning_code=gis.zoning_code,
                overlays=[],
                confidence=0.0,
                method="gis_unmapped_district",
                warnings=[
                    f"Parcel is zoned {gis.zoning_code}{attribution}, "
                    "which is not yet mapped to a district category.",
                ],
            )

        district = _keyword_district(address)
        if district:
            return ParcelResult(
                parcel_id=None,
                zoning_district=district,
                overlays=[],
                confidence=0.3,
                method="keyword_fallback",
                warnings=["Zoning district was inferred from address keywords and should be verified."],
            )

        return ParcelResult(
            parcel_id=None,
            zoning_district=None,
            overlays=[],
            confidence=0.0,
            method="unknown",
            warnings=["Zoning district could not be resolved from local parcel data."],
        )


@lru_cache(maxsize=1)
def _load_fixtures() -> list[dict[str, Any]]:
    if not PARCEL_FIXTURES_PATH.exists():
        return []
    with PARCEL_FIXTURES_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def _fixture_match(address: str, jurisdiction_id: str) -> dict[str, Any] | None:
    normalized = address.lower()
    for fixture in _load_fixtures():
        if str(fixture.get("jurisdiction_id", "")) != jurisdiction_id:
            continue
        pattern = str(fixture.get("address_pattern", "")).lower()
        if pattern and pattern in normalized:
            return fixture
    return None


def _keyword_district(address: str) -> str | None:
    haystack = address.lower()
    keyword_rules = {
        "downtown": "mixed-use-core",
        "main st": "mixed-use-core",
        "market": "mixed-use-core",
        "industrial": "industrial-zone",
        "business park": "commercial-employment",
        "suburb": "residential-low-density",
        "residential": "residential-low-density",
    }
    for keyword, district in keyword_rules.items():
        if keyword in haystack:
            return district
    return None
