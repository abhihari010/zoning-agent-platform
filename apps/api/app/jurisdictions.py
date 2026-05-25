from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


JURISDICTIONS_PATH = Path(__file__).resolve().parent / "data" / "jurisdictions.json"
GOLDEN_SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "tests" / "golden" / "scenarios.json"


@dataclass(frozen=True)
class Jurisdiction:
    jurisdiction_id: str
    name: str
    supported: bool
    coverage_status: str
    jurisdiction_type: str
    locality_names: tuple[str, ...]
    county_names: tuple[str, ...]
    state_names: tuple[str, ...]
    state: str | None = None
    state_fips: str | None = None
    county_fips: str | None = None
    place_fips: str | None = None
    parent_jurisdiction_id: str | None = None
    official_source_urls: tuple[str, ...] = ()
    zoning_map_url: str | None = None
    planning_contact: dict[str, str] | None = None
    last_verified_at: str | None = None
    match_strategy: str = "locality"


@dataclass(frozen=True)
class JurisdictionMatch:
    jurisdiction_id: str | None
    name: str | None
    supported: bool
    coverage_status: str = "unsupported"
    jurisdiction_type: str = "unknown"
    recognized: bool = False
    state: str | None = None
    county: str | None = None
    locality: str | None = None
    official_source_urls: tuple[str, ...] = ()
    zoning_map_url: str | None = None
    planning_contact: dict[str, str] | None = None


@dataclass(frozen=True)
class JurisdictionScope:
    jurisdiction_id: str
    state: str | None = None
    county: str | None = None
    municipality: str | None = None
    parent_jurisdiction_id: str | None = None


@dataclass(frozen=True)
class PublicSupportValidationResult:
    jurisdiction_id: str
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(item).strip()}


def _coverage_status(item: dict[str, Any]) -> str:
    raw = str(item.get("coverage_status") or "").strip()
    if raw:
        return raw
    return "public_supported" if bool(item.get("supported", False)) else "unsupported"


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
                supported=_coverage_status(item) == "public_supported",
                coverage_status=_coverage_status(item),
                jurisdiction_type=str(item.get("jurisdiction_type", "unknown")).strip() or "unknown",
                locality_names=_string_tuple(item.get("locality_names")),
                county_names=_string_tuple(item.get("county_names")),
                state_names=_string_tuple(item.get("state_names")),
                state=str(item.get("state") or "").strip() or None,
                state_fips=str(item.get("state_fips") or "").strip() or None,
                county_fips=str(item.get("county_fips") or "").strip() or None,
                place_fips=str(item.get("place_fips") or "").strip() or None,
                parent_jurisdiction_id=str(item.get("parent_jurisdiction_id") or "").strip() or None,
                official_source_urls=_string_tuple(item.get("official_source_urls")),
                zoning_map_url=str(item.get("zoning_map_url") or "").strip() or None,
                planning_contact=_string_dict(item.get("planning_contact")),
                last_verified_at=str(item.get("last_verified_at") or "").strip() or None,
                match_strategy=str(item.get("match_strategy", "locality")).strip().lower() or "locality",
            )
        )
    return jurisdictions


def _component_name(
    address_components: list[dict[str, Any]],
    component_type: str,
    *,
    short: bool = False,
) -> str:
    for component in address_components:
        if component_type in component.get("types", []):
            key = "short_name" if short else "long_name"
            return str(component.get(key) or component.get("long_name", "")).strip()
    return ""


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def detect_jurisdiction(
    formatted_address: str,
    address_components: list[dict[str, Any]],
) -> JurisdictionMatch:
    locality = _component_name(address_components, "locality").lower()
    county = _component_name(address_components, "administrative_area_level_2").lower()
    state = _component_name(address_components, "administrative_area_level_1").lower()
    country = _component_name(address_components, "country", short=True).upper()
    formatted = formatted_address.lower()

    jurisdictions = sorted(load_jurisdictions(), key=lambda item: item.match_strategy == "county")
    for jurisdiction in jurisdictions:
        locality_names = {name.lower() for name in jurisdiction.locality_names}
        county_names = {name.lower() for name in jurisdiction.county_names}
        state_names = {name.lower() for name in jurisdiction.state_names}

        locality_match = False
        if locality_names:
            locality_match = locality in locality_names if locality else any(name in formatted for name in locality_names)

        county_match = False
        if county_names:
            county_match = county in county_names if county else any(name in formatted for name in county_names)

        state_match = (
            state in state_names
            if state
            else any(name in formatted for name in state_names)
        )
        if jurisdiction.match_strategy == "county":
            place_match = county_match
        elif jurisdiction.match_strategy == "locality_and_county":
            place_match = locality_match and county_match
        else:
            place_match = locality_match
        if place_match and state_match:
            return JurisdictionMatch(
                jurisdiction_id=jurisdiction.jurisdiction_id,
                name=jurisdiction.name,
                supported=jurisdiction.supported,
                coverage_status=jurisdiction.coverage_status,
                jurisdiction_type=jurisdiction.jurisdiction_type,
                recognized=True,
                state=jurisdiction.state,
                county=next(iter(jurisdiction.county_names), None),
                locality=next(iter(jurisdiction.locality_names), None),
                official_source_urls=jurisdiction.official_source_urls,
                zoning_map_url=jurisdiction.zoning_map_url,
                planning_contact=jurisdiction.planning_contact,
            )

    if country in {"US", "USA", ""}:
        fallback = fallback_us_jurisdiction(formatted_address, address_components)
        if fallback:
            return fallback

    return JurisdictionMatch(jurisdiction_id=None, name=None, supported=False, recognized=False)


def fallback_us_jurisdiction(
    formatted_address: str,
    address_components: list[dict[str, Any]],
) -> JurisdictionMatch | None:
    state_short = _component_name(address_components, "administrative_area_level_1", short=True)
    state_long = _component_name(address_components, "administrative_area_level_1")
    county = _component_name(address_components, "administrative_area_level_2")
    locality = (
        _component_name(address_components, "locality")
        or _component_name(address_components, "postal_town")
        or _component_name(address_components, "sublocality")
    )
    country = _component_name(address_components, "country", short=True).upper()
    if country and country not in {"US", "USA"}:
        return None
    if not state_short and not state_long:
        return None

    state_label = state_short or state_long
    place_label = locality or county or formatted_address
    state_slug = _slugify(state_short or state_long)
    county_slug = _slugify(county.replace(" County", "")) if county else "unknown-county"
    place_slug = _slugify(locality) if locality else "unincorporated"
    jurisdiction_id = f"us-{state_slug}-{county_slug}-{place_slug}"
    name = f"{place_label}, {state_label}"
    jurisdiction_type = "municipality" if locality else "unincorporated"
    return JurisdictionMatch(
        jurisdiction_id=jurisdiction_id,
        name=name,
        supported=False,
        coverage_status="unsupported",
        jurisdiction_type=jurisdiction_type,
        recognized=True,
        state=state_label,
        county=county or None,
        locality=locality or None,
        official_source_urls=(),
        planning_contact={},
    )


def jurisdiction_payloads() -> list[dict[str, Any]]:
    if not JURISDICTIONS_PATH.exists():
        return []
    with JURISDICTIONS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def get_jurisdiction_scope(jurisdiction_id: str | None) -> JurisdictionScope | None:
    if not jurisdiction_id:
        return None
    for jurisdiction in load_jurisdictions():
        if jurisdiction.jurisdiction_id == jurisdiction_id:
            return JurisdictionScope(
                jurisdiction_id=jurisdiction.jurisdiction_id,
                state=jurisdiction.state,
                county=next(iter(jurisdiction.county_names), None),
                municipality=next(iter(jurisdiction.locality_names), None),
                parent_jurisdiction_id=jurisdiction.parent_jurisdiction_id,
            )
    return None


def source_applies_to_jurisdiction(
    *,
    source_jurisdiction_id: str | None,
    source_metadata: dict[str, Any] | None,
    target_jurisdiction_id: str | None,
) -> bool:
    if not target_jurisdiction_id:
        return not source_jurisdiction_id
    if not source_jurisdiction_id:
        return False
    if source_jurisdiction_id == target_jurisdiction_id:
        return True

    target_scope = get_jurisdiction_scope(target_jurisdiction_id)
    metadata = source_metadata or {}
    if target_scope and source_jurisdiction_id == target_scope.parent_jurisdiction_id:
        return True
    if source_jurisdiction_id != "*":
        return False

    applies_to_states = metadata.get("applies_to_states")
    if isinstance(applies_to_states, str):
        states = {item.strip().upper() for item in applies_to_states.split(",") if item.strip()}
    elif isinstance(applies_to_states, list):
        states = {str(item).strip().upper() for item in applies_to_states if str(item).strip()}
    else:
        states = set()

    metadata_state = str(metadata.get("state") or "").strip().upper()
    if metadata_state:
        states.add(metadata_state)
    return bool(target_scope and target_scope.state and target_scope.state.upper() in states)


def validate_public_support_candidate(
    jurisdiction_id: str,
    *,
    source_store: Any,
    golden_scenarios_path: Path = GOLDEN_SCENARIOS_PATH,
) -> PublicSupportValidationResult:
    jurisdiction = source_store.get_jurisdiction(jurisdiction_id)
    if jurisdiction is None:
        jurisdiction = next(
            (
                candidate
                for candidate in load_jurisdictions()
                if candidate.jurisdiction_id == jurisdiction_id
            ),
            None,
        )
    if jurisdiction is None:
        return PublicSupportValidationResult(
            jurisdiction_id=jurisdiction_id,
            eligible=False,
            errors=(f"Jurisdiction '{jurisdiction_id}' does not exist.",),
        )

    errors: list[str] = []
    warnings: list[str] = []
    planning_contact = getattr(jurisdiction, "planning_contact", None) or {}
    if not any(planning_contact.get(key) for key in ["url", "email", "phone"]):
        errors.append("Planning contact must include a URL, email, or phone number.")
    if not getattr(jurisdiction, "official_source_urls", None):
        errors.append("Jurisdiction must have at least one official source URL.")
    coverage_status = str(getattr(jurisdiction, "coverage_status", "") or "")
    if coverage_status not in {"qa_ready", "public_supported"}:
        errors.append("Coverage status must be qa_ready before promotion to public_supported.")

    sources = [
        source
        for source in source_store.list_sources()
        if source_applies_to_jurisdiction(
            source_jurisdiction_id=source.jurisdiction_id,
            source_metadata=source.metadata,
            target_jurisdiction_id=jurisdiction_id,
        )
    ]
    local_sources = [source for source in sources if source.jurisdiction_id == jurisdiction_id]
    if not local_sources:
        errors.append("Source registry must include at least one local source for the jurisdiction.")
    for source in local_sources:
        missing = []
        if not source.url:
            missing.append("url")
        if not source.effective_date:
            missing.append("effective_date")
        if missing:
            errors.append(f"Source '{source.source_id}' is missing {', '.join(missing)}.")

    chunk_source_ids = {
        chunk.source_id
        for chunk in source_store.list_source_chunks()
        if source_applies_to_jurisdiction(
            source_jurisdiction_id=chunk.jurisdiction_id,
            source_metadata=chunk.metadata,
            target_jurisdiction_id=jurisdiction_id,
        )
    }
    if not any(source.source_id in chunk_source_ids for source in local_sources):
        errors.append("Indexed source chunks must exist for the jurisdiction.")

    scenario_gate = _golden_scenario_gate_for_jurisdiction(jurisdiction_id, golden_scenarios_path)
    if not scenario_gate["scenario_ids"]:
        errors.append("At least one golden QA scenario must exist for the jurisdiction.")
    elif not scenario_gate["supported_scenario_ids"]:
        errors.append(
            "At least one golden QA scenario must expect public support and source-backed citations."
        )
    elif len(scenario_gate["scenario_ids"]) == 1:
        warnings.append("Only one golden QA scenario currently covers this jurisdiction.")

    return PublicSupportValidationResult(
        jurisdiction_id=jurisdiction_id,
        eligible=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(warnings),
    )


def _golden_scenario_gate_for_jurisdiction(jurisdiction_id: str, path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {"scenario_ids": [], "supported_scenario_ids": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"scenario_ids": [], "supported_scenario_ids": []}
    if not isinstance(payload, list):
        return {"scenario_ids": [], "supported_scenario_ids": []}

    scenario_ids: list[str] = []
    supported_scenario_ids: list[str] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("jurisdiction_id") != jurisdiction_id:
            continue
        scenario_id = str(item.get("id"))
        scenario_ids.append(scenario_id)
        expect = item.get("expect") if isinstance(item.get("expect"), dict) else {}
        if expect.get("jurisdiction_supported") is True and int(expect.get("min_citations") or 0) >= 1:
            supported_scenario_ids.append(scenario_id)
    return {"scenario_ids": scenario_ids, "supported_scenario_ids": supported_scenario_ids}
