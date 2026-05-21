from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


JURISDICTIONS_PATH = Path(__file__).resolve().parent / "data" / "jurisdictions.json"


@dataclass(frozen=True)
class Jurisdiction:
    jurisdiction_id: str
    name: str
    supported: bool
    locality_names: tuple[str, ...]
    state_names: tuple[str, ...]


@dataclass(frozen=True)
class JurisdictionMatch:
    jurisdiction_id: str | None
    name: str | None
    supported: bool


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@lru_cache(maxsize=1)
def load_jurisdictions() -> list[Jurisdiction]:
    if not JURISDICTIONS_PATH.exists():
        return []

    with JURISDICTIONS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        return []

    jurisdictions: list[Jurisdiction] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        jurisdiction_id = str(item.get("jurisdiction_id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not jurisdiction_id or not name:
            continue
        jurisdictions.append(
            Jurisdiction(
                jurisdiction_id=jurisdiction_id,
                name=name,
                supported=bool(item.get("supported", False)),
                locality_names=_string_tuple(item.get("locality_names")),
                state_names=_string_tuple(item.get("state_names")),
            )
        )
    return jurisdictions


def _component_name(address_components: list[dict[str, Any]], component_type: str) -> str:
    for component in address_components:
        if component_type in component.get("types", []):
            return str(component.get("long_name", "")).strip()
    return ""


def detect_jurisdiction(
    formatted_address: str,
    address_components: list[dict[str, Any]],
) -> JurisdictionMatch:
    locality = _component_name(address_components, "locality").lower()
    state = _component_name(address_components, "administrative_area_level_1").lower()
    formatted = formatted_address.lower()

    for jurisdiction in load_jurisdictions():
        locality_match = (
            locality in {name.lower() for name in jurisdiction.locality_names}
            if locality
            else any(name.lower() in formatted for name in jurisdiction.locality_names)
        )
        state_match = (
            state in {name.lower() for name in jurisdiction.state_names}
            if state
            else any(name.lower() in formatted for name in jurisdiction.state_names)
        )
        if locality_match and state_match:
            return JurisdictionMatch(
                jurisdiction_id=jurisdiction.jurisdiction_id,
                name=jurisdiction.name,
                supported=jurisdiction.supported,
            )

    return JurisdictionMatch(jurisdiction_id=None, name=None, supported=False)
