from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = "source-pack/v1"

ALLOWED_COVERAGE_STATUSES = {
    "source_discovery",
    "source_indexed",
    "qa_ready",
    "public_supported",
}

ALLOWED_JURISDICTION_TYPES = {
    "municipality",
    "county",
    "independent_city",
    "state",
    "regional_authority",
    "special_district",
}

ALLOWED_SOURCE_TYPES = {
    "zoning_ordinance",
    "zoning_map",
    "planning_page",
    "permit_page",
    "building_code",
    "health_code",
    "fire_code",
    "gis_layer",
    "fee_schedule",
    "application_form",
    "state_law",
}

GLOBAL_SOURCE_TYPES = {
    "building_code",
    "health_code",
    "fire_code",
    "state_law",
}

REQUIRED_JURISDICTION_FIELDS = {
    "jurisdiction_id",
    "name",
    "coverage_status",
    "state",
    "state_fips",
    "county_fips",
    "place_fips",
    "jurisdiction_type",
    "parent_jurisdiction_id",
    "official_source_urls",
    "zoning_map_url",
    "planning_contact",
}

REQUIRED_SOURCE_FIELDS = {
    "source_id",
    "title",
    "section_ref",
    "jurisdiction_id",
    "url",
    "effective_date",
    "source_type",
    "districts",
    "uses",
}


@dataclass
class SourcePackIssue:
    path: Path
    message: str


@dataclass
class JurisdictionSummary:
    manifest_path: Path
    jurisdiction_id: str
    name: str
    source_count: int
    error_count: int = 0
    warning_count: int = 0


@dataclass
class ValidationResult:
    errors: list[SourcePackIssue] = field(default_factory=list)
    warnings: list[SourcePackIssue] = field(default_factory=list)
    summaries: list[JurisdictionSummary] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def default_source_pack_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "services" / "ingestion" / "source_packs"


def validate_source_packs(base_dir: str | Path | None = None) -> ValidationResult:
    root = Path(base_dir) if base_dir else default_source_pack_dir()
    result = ValidationResult()

    if not root.exists():
        result.errors.append(SourcePackIssue(root, "Source pack directory does not exist."))
        return result
    if not root.is_dir():
        result.errors.append(SourcePackIssue(root, "Source pack path must be a directory."))
        return result

    manifests = sorted(root.rglob("manifest.json"))
    if not manifests:
        result.errors.append(SourcePackIssue(root, "No manifest.json files found."))
        return result

    seen_source_ids: dict[str, Path] = {}
    for manifest_path in manifests:
        before_errors = len(result.errors)
        before_warnings = len(result.warnings)
        payload = _load_manifest(manifest_path, result)
        if payload is None:
            result.summaries.append(
                JurisdictionSummary(
                    manifest_path=manifest_path,
                    jurisdiction_id="unknown",
                    name="unknown",
                    source_count=0,
                    error_count=len(result.errors) - before_errors,
                    warning_count=len(result.warnings) - before_warnings,
                )
            )
            continue

        _validate_manifest(manifest_path, payload, seen_source_ids, result)
        jurisdiction = payload.get("jurisdiction") if isinstance(payload.get("jurisdiction"), dict) else {}
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        result.summaries.append(
            JurisdictionSummary(
                manifest_path=manifest_path,
                jurisdiction_id=_text(jurisdiction.get("jurisdiction_id")) or "unknown",
                name=_text(jurisdiction.get("name")) or "unknown",
                source_count=len(sources),
                error_count=len(result.errors) - before_errors,
                warning_count=len(result.warnings) - before_warnings,
            )
        )

    return result


def print_validation_result(result: ValidationResult, *, stream=sys.stdout) -> None:
    print("Source pack validation summary:", file=stream)
    for summary in result.summaries:
        status = "ok" if summary.error_count == 0 else "error"
        print(
            f"- {summary.jurisdiction_id}: {summary.source_count} source(s), "
            f"{summary.error_count} error(s), {summary.warning_count} warning(s) [{status}] "
            f"({summary.manifest_path})",
            file=stream,
        )

    if result.warnings:
        print("\nWarnings:", file=stream)
        for warning in result.warnings:
            print(f"- {warning.path}: {warning.message}", file=stream)

    if result.errors:
        print("\nErrors:", file=stream)
        for error in result.errors:
            print(f"- {error.path}: {error.message}", file=stream)

    if result.ok:
        print("\nValidation passed.", file=stream)
    else:
        print(f"\nValidation failed with {len(result.errors)} error(s).", file=stream)


def _load_manifest(path: Path, result: ValidationResult) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.errors.append(SourcePackIssue(path, f"Invalid JSON: {exc.msg}."))
        return None
    except OSError as exc:
        result.errors.append(SourcePackIssue(path, f"Could not read manifest: {exc}."))
        return None

    if not isinstance(payload, dict):
        result.errors.append(SourcePackIssue(path, "Manifest must be a JSON object."))
        return None
    return payload


def _validate_manifest(
    path: Path,
    payload: dict,
    seen_source_ids: dict[str, Path],
    result: ValidationResult,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        result.errors.append(
            SourcePackIssue(
                path,
                f"schema_version must be {SCHEMA_VERSION!r}.",
            )
        )

    jurisdiction = payload.get("jurisdiction")
    if not isinstance(jurisdiction, dict):
        result.errors.append(SourcePackIssue(path, "jurisdiction must be an object."))
        jurisdiction = {}

    verification_notes = _text(payload.get("verification_notes"))
    if not verification_notes:
        result.errors.append(SourcePackIssue(path, "verification_notes is required."))

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        result.errors.append(SourcePackIssue(path, "sources must be a non-empty array."))
        sources = []

    _validate_jurisdiction(path, jurisdiction, result)

    pack_jurisdiction_id = _text(jurisdiction.get("jurisdiction_id"))
    parent_jurisdiction_id = _text(jurisdiction.get("parent_jurisdiction_id"))
    state = _text(jurisdiction.get("state")).upper()

    for index, source in enumerate(sources):
        source_path = Path(f"{path}#sources[{index}]")
        if not isinstance(source, dict):
            result.errors.append(SourcePackIssue(source_path, "Source must be an object."))
            continue
        _validate_source(
            source_path,
            source,
            pack_jurisdiction_id=pack_jurisdiction_id,
            parent_jurisdiction_id=parent_jurisdiction_id,
            state=state,
            seen_source_ids=seen_source_ids,
            result=result,
        )


def _validate_jurisdiction(path: Path, jurisdiction: dict, result: ValidationResult) -> None:
    for field_name in sorted(REQUIRED_JURISDICTION_FIELDS):
        if field_name not in jurisdiction:
            result.errors.append(SourcePackIssue(path, f"jurisdiction.{field_name} is required."))

    jurisdiction_id = _text(jurisdiction.get("jurisdiction_id"))
    if "jurisdiction_id" in jurisdiction and not jurisdiction_id:
        result.errors.append(SourcePackIssue(path, "jurisdiction.jurisdiction_id must be non-empty."))

    name = _text(jurisdiction.get("name"))
    if "name" in jurisdiction and not name:
        result.errors.append(SourcePackIssue(path, "jurisdiction.name must be non-empty."))

    coverage_status = _text(jurisdiction.get("coverage_status"))
    if coverage_status and coverage_status not in ALLOWED_COVERAGE_STATUSES:
        result.errors.append(
            SourcePackIssue(
                path,
                "jurisdiction.coverage_status must be one of: "
                + ", ".join(sorted(ALLOWED_COVERAGE_STATUSES)),
            )
        )
    elif "coverage_status" in jurisdiction and not coverage_status:
        result.errors.append(SourcePackIssue(path, "jurisdiction.coverage_status must be non-empty."))

    state = _text(jurisdiction.get("state"))
    if "state" in jurisdiction and not state:
        result.errors.append(SourcePackIssue(path, "jurisdiction.state must be non-empty."))

    jurisdiction_type = _text(jurisdiction.get("jurisdiction_type"))
    if jurisdiction_type and jurisdiction_type not in ALLOWED_JURISDICTION_TYPES:
        result.errors.append(
            SourcePackIssue(
                path,
                "jurisdiction.jurisdiction_type must be one of: "
                + ", ".join(sorted(ALLOWED_JURISDICTION_TYPES)),
            )
        )
    elif "jurisdiction_type" in jurisdiction and not jurisdiction_type:
        result.errors.append(SourcePackIssue(path, "jurisdiction.jurisdiction_type must be non-empty."))

    official_urls = jurisdiction.get("official_source_urls")
    if not isinstance(official_urls, list) or not official_urls:
        result.errors.append(SourcePackIssue(path, "jurisdiction.official_source_urls must be a non-empty array."))
    else:
        for index, url in enumerate(official_urls):
            _validate_url(
                Path(f"{path}#jurisdiction.official_source_urls[{index}]"),
                _text(url),
                result,
                allow_local_fallback=False,
            )

    zoning_map_url = jurisdiction.get("zoning_map_url")
    if zoning_map_url is not None and _text(zoning_map_url):
        _validate_url(Path(f"{path}#jurisdiction.zoning_map_url"), _text(zoning_map_url), result)

    planning_contact = jurisdiction.get("planning_contact")
    if not isinstance(planning_contact, dict):
        result.errors.append(SourcePackIssue(path, "jurisdiction.planning_contact must be an object."))
    else:
        contact_points = [
            _text(planning_contact.get("url")),
            _text(planning_contact.get("email")),
            _text(planning_contact.get("phone")),
        ]
        if not any(contact_points):
            result.errors.append(
                SourcePackIssue(path, "jurisdiction.planning_contact must include url, email, or phone.")
            )
        if _text(planning_contact.get("url")):
            _validate_url(Path(f"{path}#jurisdiction.planning_contact.url"), _text(planning_contact.get("url")), result)


def _validate_source(
    path: Path,
    source: dict,
    *,
    pack_jurisdiction_id: str,
    parent_jurisdiction_id: str,
    state: str,
    seen_source_ids: dict[str, Path],
    result: ValidationResult,
) -> None:
    for field_name in sorted(REQUIRED_SOURCE_FIELDS):
        if field_name not in source:
            result.errors.append(SourcePackIssue(path, f"{field_name} is required."))

    if not _text(source.get("excerpt")) and not _text(source.get("full_text")):
        result.errors.append(SourcePackIssue(path, "excerpt or full_text is required."))

    for field_name in ["source_id", "title", "section_ref", "jurisdiction_id", "effective_date"]:
        if field_name in source and not _text(source.get(field_name)):
            result.errors.append(SourcePackIssue(path, f"{field_name} must be non-empty."))

    source_id = _text(source.get("source_id"))
    if source_id:
        previous = seen_source_ids.get(source_id)
        if previous:
            result.errors.append(
                SourcePackIssue(path, f"source_id {source_id!r} duplicates source in {previous}.")
            )
        else:
            seen_source_ids[source_id] = path

    source_type = _text(source.get("source_type"))
    if source_type and source_type not in ALLOWED_SOURCE_TYPES:
        result.errors.append(
            SourcePackIssue(
                path,
                "source_type must be one of: " + ", ".join(sorted(ALLOWED_SOURCE_TYPES)),
            )
        )
    elif "source_type" in source and not source_type:
        result.errors.append(SourcePackIssue(path, "source_type must be non-empty."))

    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    curated_local_fallback = bool(metadata.get("curated_local_fallback"))
    _validate_url(
        Path(f"{path}#url"),
        _text(source.get("url")),
        result,
        allow_local_fallback=curated_local_fallback,
    )
    if curated_local_fallback:
        if not _text(metadata.get("fallback_reason")):
            result.errors.append(SourcePackIssue(path, "curated local fallback requires metadata.fallback_reason."))

    districts = source.get("districts")
    if not isinstance(districts, list) or not districts:
        result.errors.append(SourcePackIssue(path, "districts must be a non-empty array."))
    else:
        normalized_districts = [_text(item).lower() for item in districts if _text(item)]
        if not normalized_districts:
            result.errors.append(SourcePackIssue(path, "districts must include at least one non-empty value."))
        elif normalized_districts == ["unknown"]:
            result.warnings.append(SourcePackIssue(path, "districts contains only 'unknown'."))

    uses = source.get("uses")
    if not isinstance(uses, list) or not uses or not any(_text(item) for item in uses):
        result.errors.append(SourcePackIssue(path, "uses must be a non-empty array."))

    source_jurisdiction_id = _text(source.get("jurisdiction_id"))
    if source_jurisdiction_id:
        _validate_source_scope(
            path,
            source_jurisdiction_id=source_jurisdiction_id,
            pack_jurisdiction_id=pack_jurisdiction_id,
            parent_jurisdiction_id=parent_jurisdiction_id,
            state=state,
            source_type=source_type,
            metadata=metadata,
            result=result,
        )


def _validate_source_scope(
    path: Path,
    *,
    source_jurisdiction_id: str,
    pack_jurisdiction_id: str,
    parent_jurisdiction_id: str,
    state: str,
    source_type: str,
    metadata: dict,
    result: ValidationResult,
) -> None:
    if source_jurisdiction_id == pack_jurisdiction_id:
        return

    if parent_jurisdiction_id and source_jurisdiction_id == parent_jurisdiction_id:
        return

    if source_jurisdiction_id == "*":
        applies_to_states = metadata.get("applies_to_states")
        normalized_states = {_text(item).upper() for item in applies_to_states or [] if _text(item)}
        if source_type not in GLOBAL_SOURCE_TYPES:
            result.errors.append(
                SourcePackIssue(path, "global jurisdiction_id '*' is allowed only for state/building/health/fire law sources.")
            )
        if not state or state not in normalized_states:
            result.errors.append(
                SourcePackIssue(path, "global source requires metadata.applies_to_states containing the pack state.")
            )
        return

    result.errors.append(
        SourcePackIssue(
            path,
            "jurisdiction_id must match the pack, the declared parent_jurisdiction_id, or explicit global '*'.",
        )
    )


def _validate_url(
    path: Path,
    url: str,
    result: ValidationResult,
    *,
    allow_local_fallback: bool = False,
) -> None:
    if not url:
        result.errors.append(SourcePackIssue(path, "url must be non-empty."))
        return

    if "TODO" in url.upper():
        result.errors.append(SourcePackIssue(path, "url contains a TODO placeholder."))
        return

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if _is_placeholder_host(host):
        result.errors.append(SourcePackIssue(path, f"placeholder URL host is not allowed: {host}."))
        return

    if scheme in {"http", "https"} and host:
        return

    if allow_local_fallback and scheme in {"local", "file"}:
        return

    if allow_local_fallback:
        result.errors.append(SourcePackIssue(path, "curated local fallback URL must use local:// or file://."))
    else:
        result.errors.append(SourcePackIssue(path, "url must be an http or https URL."))


def _is_placeholder_host(host: str) -> bool:
    if not host:
        return False
    return host in {
        "example.com",
        "example.gov",
        "example.net",
        "example.org",
        "www.example.com",
        "www.example.gov",
        "www.example.net",
        "www.example.org",
    } or host.endswith(".example.com") or host.endswith(".example.gov")


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate jurisdiction source pack manifests.")
    parser.add_argument(
        "--source-packs-dir",
        type=Path,
        default=default_source_pack_dir(),
        help="Directory containing source pack manifest.json files.",
    )
    args = parser.parse_args(argv)

    result = validate_source_packs(args.source_packs_dir)
    print_validation_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
