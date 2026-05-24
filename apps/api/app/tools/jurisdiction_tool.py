from __future__ import annotations

from typing import Any

from app.jurisdictions import detect_jurisdiction, load_jurisdictions
from app.models import JurisdictionResult


class JurisdictionTool:
    """Resolve zoning jurisdiction and support status."""

    def resolve(
        self,
        address: str | None,
        lat: float | None,
        lng: float | None,
        explicit_jurisdiction: str | None,
        address_components: list[dict[str, Any]] | None = None,
    ) -> JurisdictionResult:
        if explicit_jurisdiction:
            match = _by_id(explicit_jurisdiction)
            if match:
                return JurisdictionResult(
                    jurisdiction_id=match.jurisdiction_id,
                    jurisdiction_name=match.name,
                    supported=match.supported,
                    confidence=1.0,
                    method="explicit",
                    warnings=[] if match.supported else [_unsupported_warning(match.name)],
                )
            return JurisdictionResult(
                jurisdiction_id=explicit_jurisdiction,
                jurisdiction_name=explicit_jurisdiction,
                supported=False,
                confidence=0.7,
                method="explicit",
                warnings=[_unsupported_warning(explicit_jurisdiction)],
            )

        if address_components:
            match = detect_jurisdiction(address or "", address_components)
            if match.recognized:
                return JurisdictionResult(
                    jurisdiction_id=match.jurisdiction_id,
                    jurisdiction_name=match.name,
                    supported=match.supported,
                    confidence=0.95,
                    method="geocode",
                    warnings=[] if match.supported else [_unsupported_warning(match.name or "this jurisdiction")],
                )

        normalized_address = (address or "").lower()
        for jurisdiction in load_jurisdictions():
            locality_match = any(name.lower() in normalized_address for name in jurisdiction.locality_names)
            county_match = any(name.lower() in normalized_address for name in jurisdiction.county_names)
            state_match = any(name.lower() in normalized_address for name in jurisdiction.state_names)
            if (locality_match or county_match) and state_match:
                return JurisdictionResult(
                    jurisdiction_id=jurisdiction.jurisdiction_id,
                    jurisdiction_name=jurisdiction.name,
                    supported=jurisdiction.supported,
                    confidence=0.85,
                    method="fixture",
                    warnings=[] if jurisdiction.supported else [_unsupported_warning(jurisdiction.name)],
                )

        if lat is not None and lng is not None:
            return JurisdictionResult(
                jurisdiction_id=None,
                jurisdiction_name=None,
                supported=False,
                confidence=0.2,
                method="geocode",
                warnings=["Coordinates did not resolve to a supported zoning jurisdiction."],
            )

        return JurisdictionResult(
            jurisdiction_id=None,
            jurisdiction_name=None,
            supported=False,
            confidence=0.0,
            method="unknown",
            warnings=["Jurisdiction could not be resolved from the address."],
        )


def _by_id(jurisdiction_id: str):
    for jurisdiction in load_jurisdictions():
        if jurisdiction.jurisdiction_id == jurisdiction_id:
            return jurisdiction
    return None


def _unsupported_warning(name: str) -> str:
    return f"This tool does not yet support zoning review for {name}."
