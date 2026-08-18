r"""Retag existing Qdrant payloads and SQL chunks with Layer-2 district/use classifications.

The classifier (``app.source_classifier``) runs during source-pack import and
writes real district/use tags additively (e.g. ``["unknown","commercial-employment"]``).
This script applies those tags to an already-indexed corpus WITHOUT re-embedding —
Gemini embeddings are billed; only payloads change.

Safe to run multiple times: the import-time idempotency guard in ingestion.py
prevents overwriting sources that already carry real tags, and ``set_payload``
is a PUT-style operation that can be applied repeatedly.

Only sources whose tags actually differ from the database are rewritten. Each
``upsert_source`` is its own transaction plus an audit row, so rewriting the
whole corpus is ~19k round trips to a remote Postgres and tends to lose the
connection partway. Pass ``--jurisdiction`` to narrow the scan further.

Run from ``apps/api`` with PRODUCTION env vars set::

    cd apps/api
    # PowerShell:
    $env:DATABASE_URL="postgresql+psycopg://..."
    $env:QDRANT_URL="https://..."; $env:QDRANT_API_KEY="..."
    $env:GEMINI_API_KEY="..."          # not used for embedding here
    $env:EMBEDDING_PROVIDER="gemini"   # required by QdrantVectorStore init
    $env:VECTOR_PROVIDER="qdrant"
    $env:RAG_PROVIDER="hybrid_local"
    $env:PYTHONPATH="."                # so `app` resolves to THIS checkout
    python ..\..\scripts\update_source_classification.py --dry-run --jurisdiction chesapeake-va
    # review output, then re-run without --dry-run

``scripts/`` lives at the repo root, so from ``apps/api`` the path is
``..\..\scripts\`` (two levels), not ``..\scripts\``.

Flags:
    --dry-run       Print the sources whose tags would change, old -> new; do
                    NOT write to Postgres or Qdrant.
    --jurisdiction  Comma-separated jurisdiction_ids to limit the run to.
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
    parser.add_argument(
        "--jurisdiction",
        default="",
        help=(
            "Comma-separated jurisdiction_ids to limit the run to (e.g. "
            "'chesapeake-va'). Default: every pack."
        ),
    )
    args = parser.parse_args()
    only = {j.strip() for j in args.jurisdiction.split(",") if j.strip()}

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
    if only:
        entries = [e for e in entries if e.jurisdiction_id in only]
    _log(f"classified {len(entries)} source-pack sources" + (f" in {sorted(only)}." if only else "."))
    if not entries:
        _log("ERROR: no sources matched --jurisdiction; check the id.")
        return 2

    # Only sources whose tags actually MOVED are rewritten. Every upsert_source is
    # its own transaction plus an audit row -- ~2 round trips each -- so rewriting
    # all 9641 sources means ~19k round trips to a remote Postgres, which is what
    # made the whole-corpus run drop its connection partway through. A tag change
    # typically moves a handful of sources; the rest are identical rewrites.
    # One query loads the stored side.
    stored = {s.source_id: s for s in store.list_sources()}
    changed = [
        e
        for e in entries
        if (lambda s: s is None or s.districts != e.districts or s.uses != e.uses)(
            stored.get(e.source_id)
        )
    ]
    _log(f"{len(changed)}/{len(entries)} sources have tags differing from the database.")

    if args.dry_run:
        _log("\n--- DRY RUN: sources whose tags would change (section_ref -> districts / uses) ---")
        for entry in sorted(changed, key=lambda e: e.section_ref or ""):
            was = stored.get(entry.source_id)
            _log(
                f"  {entry.section_ref or entry.source_id:<30}  "
                f"districts={entry.districts}  uses={entry.uses}"
                + (f"   (was districts={was.districts} uses={was.uses})" if was else "   (new)")
            )
        _log(f"\n{len(changed)} source(s) would be rewritten (dry run — no writes).")
        return 0

    if not changed:
        _log("Nothing to do — the database already matches the packs.")
        return 0

    # Step 2: persist classified tags to Postgres (districts_csv / uses_csv columns).
    for entry in changed:
        store.upsert_source(entry)
    _log(f"upserted {len(changed)} sources to Postgres.")

    # Step 3: rebuild chunk rows for the changed sources only, so SQL
    # districts_csv / uses_csv reflect the new tags. A tag change never alters a
    # chunk_id (it is derived from source_id/section_ref/index/text hash), so
    # there are no stale chunks to prune and upsert is enough -- replacing the
    # whole corpus here would rewrite all 34k chunk rows over the wire to fix a
    # handful.
    chunks = build_source_chunks(changed)
    store.upsert_source_chunks(chunks)
    _log(f"upserted chunk rows for {len(changed)} sources ({len(chunks)} chunks).")

    # Step 4: update Qdrant payloads only — no embedding calls.
    payloads: dict[str, dict[str, Any]] = {
        chunk.chunk_id: {
            "districts": chunk.districts,
            "uses": chunk.uses,
        }
        for chunk in chunks
    }
    vector_store = QdrantVectorStore(settings=settings)
    updated, skipped = vector_store.update_chunk_payloads(payloads)
    _log(f"updated {updated} Qdrant point payloads (no re-embedding).")
    if skipped:
        _log(
            f"NOTE: skipped {skipped} chunk(s) whose points are not in Qdrant yet -- "
            "their source text is newer than the last reindex. Run reindex_prod.py to "
            "embed them (new points are written with correct district/use payloads), "
            "then re-run this script to retag the rest."
        )

    # Accounting guard: every non-empty payload was either applied or explicitly skipped.
    non_empty = sum(1 for payload in payloads.values() if payload)
    assert updated + skipped == non_empty, (
        f"payload accounting mismatch: {updated} + {skipped} != {non_empty}"
    )

    _log(
        f"\nDONE. {updated} Qdrant points retagged"
        + (f" ({skipped} skipped, pending reindex)." if skipped else ".")
        + " Retrieval-cache versioning is a live districts/uses fingerprint, so stale "
        "cached results are invalidated automatically on the next query."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
