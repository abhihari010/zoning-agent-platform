from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.models import SourceChunk, SourceRegistryEntry


def _resolve_default_docs_path() -> Path:
    here = Path(__file__).resolve()
    if len(here.parents) >= 4:
        return here.parents[3] / "services" / "ingestion" / "documents"
    return here.parent / "data" / "documents"


DEFAULT_INGESTION_DOCS_PATH = _resolve_default_docs_path()
SUPPORTED_FILE_SUFFIXES = {".md", ".txt", ".json"}
DEFAULT_CHUNK_MAX_CHARS = 900


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_csv_field(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _extract_excerpt(body: str) -> str:
    normalized = " ".join(body.split())
    return normalized[:500]


def _chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_MAX_CHARS) -> list[str]:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return [normalized] if normalized else []

    chunks: list[str] = []
    words = normalized.split()
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        chunks.append(" ".join(current))
    return chunks


def build_source_chunks(sources: list[SourceRegistryEntry]) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []

    for source in sorted(sources, key=lambda item: item.source_id):
        source_text = " ".join(source.excerpt.split())
        source_text_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

        for index, chunk_text in enumerate(_chunk_text(source_text)):
            stable_key = f"{source.source_id}|{source.section_ref}|{index}"
            digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
            chunks.append(
                SourceChunk(
                    chunk_id=f"{source.source_id}:chunk:{digest}",
                    source_id=source.source_id,
                    title=source.title,
                    chunk_text=chunk_text,
                    chunk_index=index,
                    source_text_hash=source_text_hash,
                    section_ref=source.section_ref,
                    url=source.url,
                    effective_date=source.effective_date,
                    districts=source.districts,
                    uses=source.uses,
                )
            )

    return chunks


def _parse_text_document(path: Path) -> SourceRegistryEntry:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    in_metadata = True

    for line in lines:
        if in_metadata and ":" in line:
            key, value = line.split(":", 1)
            key_normalized = key.strip().lower()
            if key_normalized in {
                "source_id",
                "title",
                "section_ref",
                "url",
                "effective_date",
                "districts",
                "uses",
            }:
                metadata[key_normalized] = value.strip()
                continue

        if line.strip() == "" and in_metadata:
            in_metadata = False
            continue

        in_metadata = False
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    title = metadata.get("title")
    if not title:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break
        if not title:
            title = path.stem.replace("-", " ").replace("_", " ").title()

    section_ref = metadata.get("section_ref") or "Document excerpt"
    excerpt = _extract_excerpt(body or title)

    return SourceRegistryEntry(
        source_id=metadata.get("source_id") or _slugify(path.stem),
        title=title,
        excerpt=excerpt,
        section_ref=section_ref,
        url=metadata.get("url"),
        effective_date=metadata.get("effective_date"),
        districts=_parse_csv_field(metadata.get("districts", "general")) or ["general"],
        uses=_parse_csv_field(metadata.get("uses", "general")) or ["general"],
    )


def _parse_json_document(path: Path) -> list[SourceRegistryEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [SourceRegistryEntry.model_validate(item) for item in payload]
    if isinstance(payload, dict):
        return [SourceRegistryEntry.model_validate(payload)]
    raise ValueError(f"Unsupported JSON structure in {path}")


def parse_source_file(path: Path) -> list[SourceRegistryEntry]:
    if path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
        return []
    if path.suffix.lower() == ".json":
        return _parse_json_document(path)
    return [_parse_text_document(path)]


def import_source_documents(directory: str | Path | None = None) -> list[SourceRegistryEntry]:
    base_path = Path(directory) if directory else DEFAULT_INGESTION_DOCS_PATH
    if not base_path.exists():
        raise FileNotFoundError(f"Ingestion directory not found: {base_path}")
    if not base_path.is_dir():
        raise ValueError(f"Ingestion path must be a directory: {base_path}")

    entries: dict[str, SourceRegistryEntry] = {}
    for path in sorted(base_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
            continue
        for entry in parse_source_file(path):
            entries[entry.source_id] = entry
    return list(entries.values())
