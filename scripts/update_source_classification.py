r"""Retag existing Qdrant payloads and SQL chunks with Layer-2 district/use classifications.

The classifier (``app.source_classifier``) runs during source-pack import and
writes real district/use tags additively (e.g. ``["unknown","commercial-employment"]``).
This script applies those tags to an already-indexed corpus WITHOUT re-embedding —
Gemini embeddings are billed; only payloads change.

Safe to run multiple times: the import-time idempotency guard in ingestion.py
prevents overwriting sources that already carry real tags, and ``set_payload``
is a PUT-style operation that can be applied repeatedly.

Run from ``apps/api`` with PRODUCTION env vars set::

    cd apps/api
    # PowerShell:
    $env:DATABASE_URL="postgresql+psycopg://..."
    $env:QDRANT_URL="https://..."; $env:QDRANT_API_KEY="..."
    $env:GEMINI_API_KEY="..."          # not used for embedding here
    $env:EMBEDDING_PROVIDER="gemini"   # required by QdrantVectorStore init
    $env:VECTOR_PROVIDER="qdrant"
    $env:RAG_PROVIDER="hybrid_local"
    .venv\Scripts\python.exe ..\scripts\update_source_classification.py --dry-run
    # review output, then re-run without --dry-run

Flags:
    --dry-run   Print the (section_ref → districts / uses) mapping and a count
                reconciliation; do NOT write to Postgres or Qdrant.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from app.ingestion import build_source_chunks, import_source_packs
from app.rag.vector_store import QdrantVectorStore
from app.services import ensure_seed_sources
from app.settings import get_settings
from app.storage import store


def _log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply Layer-2 district/use tags to Qdrant payloads without re-embedding."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the classification mapping; do not write to Postgres or Qdrant.",
    )
    args = parser.parse_args()

    settings = get_settings()
    _log(
        f"providers: vector={settings.vector_provider} rag={settings.rag_provider} "
        f"embedding={settings.embedding_provider} (not used for embeddings)"
    )
    if settings.vector_provider != "qdrant":
        _log("ERROR: VECTOR_PROVIDER must be 'qdrant' for this script.")
        return 2

    ensure_seed_sources()

    # Step 1: import packs — classifier enriches tags during this call.
    entries = import_source_packs()
    _log(f"classified {len(entries)} source-pack sources.")

    if args.dry_run:
        _log("\n--- DRY RUN: classification mapping (section_ref → districts / uses) ---")
        changed = 0
        for entry in sorted(entries, key=lambda e: e.section_ref or ""):
            default_districts = entry.districts == ["unknown"]
            default_uses = entry.uses == ["general"]
            if not default_districts or not default_uses:
                _log(
                    f"  {entry.section_ref or entry.source_id:<30}  "
                    f"districts={entry.districts}  uses={entry.uses}"
                )
                changed += 1
        _log(
            f"\n{changed}/{len(entries)} sources have non-default district/use tags (dry run — no writes)."
        )
        return 0

    # Step 2: persist classified tags to Postgres (districts_csv / uses_csv columns).
    for entry in entries:
        store.upsert_source(entry)
    _log(f"upserted {len(entries)} sources to Postgres.")

    # Step 3: rebuild source chunks so SQL districts_csv / uses_csv reflect new tags.
    sources = store.list_sources()
    chunks = build_source_chunks(sources)
    store.replace_source_chunks(chunks)
    _log(f"replaced chunk rows for {len(sources)} sources ({len(chunks)} chunks).")

    # Step 4: update Qdrant payloads only — no embedding calls.
    payloads: dict[str, dict[str, Any]] = {
        chunk.chunk_id: {
            "districts": chunk.districts,
            "uses": chunk.uses,
        }
        for chunk in chunks
    }
    vector_store = QdrantVectorStore(settings=settings)
    updated = vector_store.update_chunk_payloads(payloads)
    _log(f"updated {updated} Qdrant point payloads (no re-embedding).")

    # Sanity guard: confirm we made zero embedding calls.
    assert updated == len(payloads), (
        f"payload update count mismatch: {updated} != {len(payloads)}"
    )

    _log(
        f"\nDONE. {updated} Qdrant points retagged. "
        "The A5 cache-version hash now includes districts/uses so stale cached "
        "retrieval results are invalidated automatically on the next query."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
