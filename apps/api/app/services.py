from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.ai import get_analysis_provider, get_retrieval_provider
from app.ai.interfaces import RetrievalProviderRequest
from app.ai.source_registry_retriever import ensure_seed_sources
from app.district_mapping import map_district_from_components
from app.jurisdictions import detect_jurisdiction
from app.models import (
    AnalyzeResult,
    SourceCitation,
)


DISCLAIMER_TEXT = [
    "This tool provides educational zoning guidance and is not legal advice.",
    "Always verify requirements with your local planning office before action.",
]


@dataclass
class IntentExtraction:
    missing_fields: list[str]
    inferred_use: str
    user_intent: str
    project_category: str


@dataclass
class AddressNormalizationResult:
    normalized_address: str
    district: str
    place_id: str | None
    latitude: float | None
    longitude: float | None
    is_valid: bool
    warnings: list[str]
    support_status: Literal["supported", "unsupported", "invalid"] = "supported"
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _load_keyword_district_rules() -> dict[str, str]:
    raw_rules = os.getenv("GOOGLE_DISTRICT_KEYWORD_MAP", "")
    if not raw_rules:
        return {
            "downtown": "mixed-use-core",
            "market": "mixed-use-core",
            "industrial": "industrial-zone",
            "business park": "commercial-employment",
            "suburb": "residential-low-density",
            "residential": "residential-low-density",
        }

    try:
        payload = json.loads(raw_rules)
        if isinstance(payload, dict):
            return {str(k).lower(): str(v) for k, v in payload.items()}
    except json.JSONDecodeError:
        pass
    return {}


def _extract_district_from_components(address_components: list[dict[str, Any]]) -> str:
    mapped = map_district_from_components(address_components)
    if mapped != "unknown":
        return mapped

    preferred_types = {"sublocality_level_1", "neighborhood"}
    for component in address_components:
        types = set(component.get("types", []))
        if preferred_types.intersection(types):
            long_name = component.get("long_name")
            if long_name:
                return f"district-{_slugify(long_name)}"
    return "unknown"


def _district_from_keywords(normalized_address: str, rules: dict[str, str]) -> str:
    haystack = normalized_address.lower()
    for keyword, mapped in rules.items():
        if keyword in haystack:
            return mapped
    return "unknown"


def _google_find_place(address: str, api_key: str, timeout_seconds: float) -> dict[str, Any] | None:
    params = {
        "input": address,
        "inputtype": "textquery",
        "fields": "place_id,formatted_address,geometry,name",
        "key": api_key,
    }
    response = httpx.get(
        "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
        params=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        raise ValueError(f"Google Places API returned status: {status}")
    if status == "ZERO_RESULTS":
        return None

    candidates = payload.get("candidates", [])
    return candidates[0] if candidates else None


def _google_geocode(address: str, api_key: str, timeout_seconds: float) -> dict[str, Any] | None:
    params = {"address": address, "key": api_key}
    response = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        raise ValueError(f"Google Geocoding API returned status: {status}")
    if status == "ZERO_RESULTS":
        return None

    results = payload.get("results", [])
    return results[0] if results else None


def suggest_addresses(query: str, session_token: str | None = None) -> list[str]:
    trimmed = " ".join(query.split()).strip()
    if len(trimmed) < 3:
        return []

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured.")

    timeout_seconds = float(os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "8"))
    # Bias toward Blacksburg, VA (37.2296, -80.4139) within a 6 km radius
    params = {
        "input": trimmed,
        "types": "address",
        "location": "37.2296,-80.4139",
        "radius": "6000",
        "strictbounds": "true",
        "components": "country:US",
        "key": api_key,
    }
    if session_token:
        params["sessiontoken"] = session_token

    response = httpx.get(
        "https://maps.googleapis.com/maps/api/place/autocomplete/json",
        params=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    payload = response.json()
    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        raise ValueError(f"Google Places Autocomplete returned status: {status}")
    if status == "ZERO_RESULTS":
        return []

    suggestions: list[str] = []
    for prediction in payload.get("predictions", []):
        description = prediction.get("description")
        if description:
            suggestions.append(str(description))
    return suggestions[:6]


def normalize_address(address: str) -> AddressNormalizationResult:
    cleaned_input = " ".join(address.split()).strip()
    if len(cleaned_input) < 5:
        return AddressNormalizationResult(
            normalized_address=cleaned_input,
            district="unknown",
            place_id=None,
            latitude=None,
            longitude=None,
            is_valid=False,
            warnings=["Address appears incomplete."],
            support_status="invalid",
        )

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured.")

    timeout_seconds = float(os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "8"))
    keyword_rules = _load_keyword_district_rules()

    place_candidate = _google_find_place(cleaned_input, api_key, timeout_seconds)
    geocode_result = _google_geocode(cleaned_input, api_key, timeout_seconds)

    if not place_candidate and not geocode_result:
        return AddressNormalizationResult(
            normalized_address=cleaned_input,
            district="unknown",
            place_id=None,
            latitude=None,
            longitude=None,
            is_valid=False,
            warnings=["Address could not be validated with Google Maps APIs."],
            support_status="invalid",
        )

    formatted_address = (
        (place_candidate or {}).get("formatted_address")
        or (geocode_result or {}).get("formatted_address")
        or cleaned_input
    )

    address_components = (
        (place_candidate or {}).get("address_components")
        or (geocode_result or {}).get("address_components")
        or []
    )
    jurisdiction = detect_jurisdiction(formatted_address, address_components)
    if not jurisdiction.supported:
        jurisdiction_name = jurisdiction.name or "this jurisdiction"
        return AddressNormalizationResult(
            normalized_address=formatted_address,
            district="unknown",
            place_id=None,
            latitude=None,
            longitude=None,
            is_valid=False,
            warnings=[f"This tool does not yet support zoning review for {jurisdiction_name}."],
            support_status="unsupported",
            jurisdiction_id=jurisdiction.jurisdiction_id,
            jurisdiction_name=jurisdiction.name,
        )

    place_id = (place_candidate or {}).get("place_id") or (geocode_result or {}).get("place_id")

    geometry = (place_candidate or {}).get("geometry") or (geocode_result or {}).get("geometry") or {}
    location = geometry.get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")

    district = _extract_district_from_components(address_components)
    if district == "unknown":
        district = _district_from_keywords(formatted_address, keyword_rules)

    warnings: list[str] = []
    if district == "unknown":
        warnings.append("District could not be inferred from returned location context.")

    return AddressNormalizationResult(
        normalized_address=formatted_address,
        district=district,
        place_id=place_id,
        latitude=float(lat) if isinstance(lat, (float, int)) else None,
        longitude=float(lng) if isinstance(lng, (float, int)) else None,
        is_valid=True,
        warnings=warnings,
        support_status="supported",
        jurisdiction_id=jurisdiction.jurisdiction_id,
        jurisdiction_name=jurisdiction.name,
    )


def extract_intent(project_description: str) -> IntentExtraction:
    lower = project_description.lower()
    missing_fields: list[str] = []
    inferred_use = "general"
    user_intent = "review whether the proposed project is allowed on the property"
    project_category = "general-project"

    if "garage" in lower and "bakery" in lower:
        inferred_use = "home-based-food-business"
        user_intent = "open a bakery from an attached garage conversion"
        project_category = "home-business"
    elif "bakery" in lower:
        inferred_use = "food-business"
        user_intent = "open a bakery on the property"
        project_category = "business-opening"
    elif "restaurant" in lower or "cafe" in lower:
        inferred_use = "food-service"
        user_intent = "open a food service business on the property"
        project_category = "business-opening"
    elif "addition" in lower or "build" in lower or "construction" in lower:
        user_intent = "confirm whether the proposed construction is allowed"
        project_category = "construction"

    if "hours" not in lower:
        missing_fields.append("operating hours")
    if "employees" not in lower:
        missing_fields.append("number of employees")
    if "renovation" not in lower and "construction" not in lower:
        missing_fields.append("construction scope")

    if len(lower.split()) < 8:
        missing_fields.insert(0, "project scope and intended use")

    return IntentExtraction(
        missing_fields=list(dict.fromkeys(missing_fields)),
        inferred_use=inferred_use,
        user_intent=user_intent,
        project_category=project_category,
    )


def retrieve_zoning_context(
    district: str,
    inferred_use: str,
    project_description: str = "",
    jurisdiction_id: str | None = None,
) -> list[SourceCitation]:
    result = get_retrieval_provider().retrieve(
        RetrievalProviderRequest(
            district=district,
            inferred_use=inferred_use,
            project_description=project_description,
            jurisdiction_id=jurisdiction_id,
        )
    )
    return result.citations


def _confidence_score(missing_fields: list[str], citations: list[SourceCitation]) -> float:
    base = 0.82
    coverage_penalty = min(0.35, 0.07 * len(missing_fields))
    citation_bonus = min(0.15, 0.05 * len(citations))
    retrieval_penalty = 0.28 if not citations else 0
    score = base - coverage_penalty + citation_bonus
    score -= retrieval_penalty
    return max(0.1, min(0.98, score))


def _merge_project_context(
    project_description: str,
    clarification_answers: dict[str, str] | None = None,
) -> str:
    answers = clarification_answers or {}
    usable_answers = [(question.strip(), answer.strip()) for question, answer in answers.items() if answer.strip()]
    if not usable_answers:
        return project_description

    clarification_lines = "\n".join(f"- {question}: {answer}" for question, answer in usable_answers)
    return f"{project_description}\n\nClarifications:\n{clarification_lines}"


def _normalize_follow_up_key(question: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    tokens = set(normalized.split())

    if "hours" in tokens:
        return "operating hours"
    if "employee" in tokens or "employees" in tokens or "workers" in tokens:
        return "number of employees"
    if ("construction" in tokens or "renovation" in tokens or "renovations" in tokens) and (
        "scope" in tokens or "planned" in tokens or "modifications" in tokens
    ):
        return "construction scope"
    if "noise" in tokens or ("surrounding" in tokens and "residential" in tokens):
        return "noise and neighborhood impact"
    if "parking" in tokens:
        return "parking"
    if "lot" in tokens and "size" in tokens:
        return "lot size"
    return normalized


def _dedupe_follow_up_questions(questions: list[str]) -> list[str]:
    best_by_key: dict[str, str] = {}

    for question in questions:
        cleaned = " ".join(question.split()).strip()
        if not cleaned:
            continue

        key = _normalize_follow_up_key(cleaned)
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = cleaned
            continue

        existing_generic = existing.lower().startswith("please provide ")
        cleaned_generic = cleaned.lower().startswith("please provide ")
        if existing_generic and not cleaned_generic:
            best_by_key[key] = cleaned

    ordered: list[str] = []
    seen: set[str] = set()
    for question in questions:
        cleaned = " ".join(question.split()).strip()
        if not cleaned:
            continue
        key = _normalize_follow_up_key(cleaned)
        chosen = best_by_key[key]
        if chosen not in seen:
            ordered.append(chosen)
            seen.add(chosen)
    return ordered


def analyze_project(
    project_description: str,
    district: str,
    jurisdiction_id: str | None = None,
    jurisdiction_name: str | None = None,
    normalized_address: str | None = None,
    project_id: str | None = None,
    clarification_answers: dict[str, str] | None = None,
    trace_recorder: Any | None = None,
) -> AnalyzeResult:
    from app.orchestrator import ZoningOrchestrator

    return ZoningOrchestrator().analyze_project(
        project_description=project_description,
        district=district,
        jurisdiction_id=jurisdiction_id,
        jurisdiction_name=jurisdiction_name,
        normalized_address=normalized_address,
        project_id=project_id,
        clarification_answers=clarification_answers,
        trace_recorder=trace_recorder,
    )
