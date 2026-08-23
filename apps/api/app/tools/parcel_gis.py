"""Runtime zoning-district lookup against a jurisdiction's published GIS layer.

Zoning is a per-municipality legal designation, so no global geocoder carries it --
each city or county publishes its own parcel/zoning layer. This module turns the
coordinates we already get from the Google geocode into that jurisdiction's real
district code, and maps the code onto the coarse vocabulary the source packs are
tagged with.

Every failure path returns ``None``. A zoning answer must never depend on a third
party staying up: when the lookup cannot answer, the caller falls back to exactly
the behaviour it had before this module existed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.settings import get_settings

logger = logging.getLogger(__name__)

GIS_SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "parcel_gis_sources.json"


@dataclass(frozen=True)
class ParcelGisResult:
    parcel_id: str | None
    zoning_code: str
    district: str | None
    attribution: str


@lru_cache(maxsize=1)
def load_gis_sources() -> dict[str, Any]:
    if not GIS_SOURCES_PATH.exists():
        return {}
    try:
        with GIS_SOURCES_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load parcel GIS sources")
        return {}
    jurisdictions = payload.get("jurisdictions") if isinstance(payload, dict) else None
    return jurisdictions if isinstance(jurisdictions, dict) else {}


def lookup(jurisdiction_id: str, lat: float | None, lng: float | None) -> ParcelGisResult | None:
    """Resolve a parcel's zoning district from coordinates, or ``None``."""

    settings = get_settings()
    if not settings.parcel_gis_enabled:
        return None
    if not jurisdiction_id or lat is None or lng is None:
        return None
    if jurisdiction_id not in load_gis_sources():
        return None

    # Cached on the exact coordinates: a repeat request for the same address gets the
    # same floats back from the geocoder, so this collapses to one upstream call.
    # Rounding was tried and rejected -- it can walk a point across a parcel boundary.
    return _lookup_cached(
        jurisdiction_id,
        float(lat),
        float(lng),
        settings.parcel_gis_timeout_seconds,
    )


def clear_cache() -> None:
    _lookup_cached.cache_clear()
    load_gis_sources.cache_clear()


@lru_cache(maxsize=2048)
def _lookup_cached(
    jurisdiction_id: str,
    lat: float,
    lng: float,
    timeout_seconds: float,
) -> ParcelGisResult | None:
    config = load_gis_sources().get(jurisdiction_id) or {}
    provider = str(config.get("provider", "arcgis"))
    if provider not in ("arcgis", "arcgis_layer_per_district"):
        return None

    try:
        if provider == "arcgis_layer_per_district":
            return _lookup_layer_per_district(config, lat, lng, timeout_seconds)
        attributes = _query_arcgis(config, lat, lng, timeout_seconds)
    except Exception:  # noqa: BLE001 - an upstream outage must not fail the request
        logger.warning("Parcel GIS lookup failed for %s", jurisdiction_id, exc_info=True)
        return None

    if attributes is None:
        return None

    expected = str(config.get("jurisdiction_value", "")).strip().upper()
    jurisdiction_field = str(config.get("jurisdiction_field", "")).strip()
    if expected and jurisdiction_field:
        actual = str(attributes.get(jurisdiction_field) or "").strip().upper()
        # A shared county layer serves several towns, and a geocode can land on a
        # neighbouring parcel. Answering with the wrong town's zoning is worse than
        # not answering.
        if actual != expected:
            return None

    zoning_code = str(attributes.get(str(config.get("zoning_field", "ZONING"))) or "").strip()
    if not zoning_code:
        return None

    parcel_id_field = str(config.get("parcel_id_field", "")).strip()
    parcel_id = str(attributes.get(parcel_id_field) or "").strip() if parcel_id_field else ""

    categories = config.get("district_categories")
    district = None
    if isinstance(categories, dict):
        district = _match_category(zoning_code, categories)

    return ParcelGisResult(
        parcel_id=parcel_id or None,
        zoning_code=zoning_code,
        district=district,
        attribution=str(config.get("attribution", "")).strip(),
    )


def _lookup_layer_per_district(
    config: dict[str, Any],
    lat: float,
    lng: float,
    timeout_seconds: float,
) -> ParcelGisResult | None:
    """Resolve against a service that publishes one layer per zoning district.

    Springfield, TN draws each district as its own layer rather than storing the code
    in a column, so the layer's NAME is the code and the answer is whichever layer
    contains the point. ArcGIS answers all of them in a single request via layerDefs,
    so this still costs one round trip.
    """

    layers = config.get("layers")
    if not isinstance(layers, dict) or not layers:
        return None
    layer_ids = sorted(int(layer_id) for layer_id in layers)
    params = {
        "geometry": json.dumps({"x": lng, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "layerDefs": json.dumps([{"layerId": i, "outFields": "OBJECTID"} for i in layer_ids]),
        "returnGeometry": "false",
        "f": "json",
    }
    response = httpx.get(str(config.get("url", "")).rstrip("/") + "/query",
                         params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(f"ArcGIS query returned an error: {payload['error']}")

    hits = [str(layer.get("id")) for layer in (payload.get("layers") or []) if layer.get("features")]
    # Overlapping planned-development layers can both answer; without a single winner
    # the honest result is no district rather than an arbitrary pick.
    if len(hits) != 1:
        return None

    zoning_code = str(layers.get(hits[0]) or "").strip()
    if not zoning_code:
        return None
    categories = config.get("district_categories")
    return ParcelGisResult(
        parcel_id=None,
        zoning_code=zoning_code,
        district=_match_category(zoning_code, categories) if isinstance(categories, dict) else None,
        attribution=str(config.get("attribution", "")).strip(),
    )


def _match_category(zoning_code: str, categories: dict[str, Any]) -> str | None:
    normalized = _normalize_code(zoning_code)
    for code, district in categories.items():
        if _normalize_code(str(code)) == normalized:
            return str(district)
    return None


def _normalize_code(code: str) -> str:
    """Fold the punctuation and case differences between a GIS layer and an ordinance.

    A layer records ``R1`` where the ordinance article reads ``R-1``; both name the
    same district. Only separators are folded, so ``R1`` never collides with ``RM1``.
    """

    return "".join(ch for ch in code.upper() if ch.isalnum())


def _query_arcgis(
    config: dict[str, Any],
    lat: float,
    lng: float,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    out_fields = [
        str(config.get(field, "")).strip()
        for field in ("zoning_field", "parcel_id_field", "jurisdiction_field")
    ]
    params = {
        "geometry": json.dumps({"x": lng, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(field for field in out_fields if field),
        "returnGeometry": "false",
        "resultRecordCount": "1",
        "f": "json",
    }

    url = str(config.get("url", "")).rstrip("/") + "/query"
    response = httpx.get(url, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(f"ArcGIS query returned an error: {payload['error']}")

    features = payload.get("features") if isinstance(payload, dict) else None
    if not features:
        return None

    attributes = features[0].get("attributes")
    return attributes if isinstance(attributes, dict) else None
