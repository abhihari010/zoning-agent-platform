r"""Bulk-load the source corpus into production Qdrant from a local machine.

The admin "Reindex sources" button embeds the whole corpus *inside one HTTP
request*. With the full breadth packs (~1,719 chunks) that exceeds the request
timeout on the rate-limited Gemini free tier, so the call hangs. This script
runs the same pipeline with no HTTP timeout, embedding in checkpointed slices
and upserting each slice to Qdrant as it goes.

It is incremental and resumable: chunks already present in Qdrant are skipped
(a chunk_id encodes its content hash), so if a run dies on a Gemini rate limit
you can simply re-run it and it picks up where it left off. Once this has loaded
the bulk, the admin button stays fast because it only embeds new/changed chunks.

Run from ``apps/api`` with the PRODUCTION provider env vars set so ``app``
imports resolve and settings point at prod Postgres + Qdrant + Gemini::

    cd apps/api
    # PowerShell:
    $env:DATABASE_URL="postgresql+psycopg://..."   # prod Postgres
    $env:QDRANT_URL="https://...";  $env:QDRANT_API_KEY="..."
    $env:GEMINI_API_KEY="..."
    $env:EMBEDDING_PROVIDER="gemini"; $env:VECTOR_PROVIDER="qdrant"
    $env:RAG_PROVIDER="hybrid_local"
    .venv\Scripts\python.exe ..\scripts\reindex_prod.py

Flags:
    --slice N        chunks embedded+upserted per checkpoint (default 96)
    --full-rebuild   wipe the Qdrant collection first and re-embed everything
    --skip-import    do not import source packs; reindex existing DB sources only
"""
from __future__ import annotations

import argparse
import sys
import time

from app.ai.interfaces import EmbeddingProviderRequest
from app.ai.registry import get_embedding_provider
from app.ingestion import build_source_chunks, import_source_packs
from app.rag.vector_store import QdrantVectorStore
from app.services import ensure_seed_sources
from app.settings import get_settings
from app.storage import store


def _log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-load source chunks into production Qdrant.")
    parser.add_argument("--slice", type=int, default=96, help="Chunks per embed/upsert checkpoint.")
    parser.add_argument("--full-rebuild", action="store_true", help="Wipe the collection and re-embed everything.")
    parser.add_argument("--skip-import", action="store_true", help="Skip importing source packs.")
    args = parser.parse_args()

    settings = get_settings()
    _log(
        f"providers: embedding={settings.embedding_provider} vector={settings.vector_provider} "
        f"rag={settings.rag_provider} model={settings.gemini_embedding_model}"
    )
    if settings.vector_provider != "qdrant":
        _log("ERROR: VECTOR_PROVIDER must be 'qdrant' for this script.")
        return 2
    if settings.embedding_provider != "gemini":
        _log(f"WARNING: EMBEDDING_PROVIDER is '{settings.embedding_provider}', expected 'gemini'.")

    ensure_seed_sources()

    if not args.skip_import:
        entries = import_source_packs()
        for entry in entries:
            store.upsert_source(entry)
        _log(f"imported {len(entries)} source-pack sources into the DB.")

    sources = store.list_sources()
    chunks = build_source_chunks(sources)
    store.replace_source_chunks(chunks)
    _log(f"built {len(chunks)} chunks from {len(sources)} sources.")

    vector_store = QdrantVectorStore(settings=settings)
    if args.full_rebuild:
        _log("full rebuild: resetting Qdrant collection.")
        vector_store.reset_collection()
        existing_ids: set[str] = set()
    else:
        existing_ids = vector_store.existing_chunk_ids()
        _log(f"{len(existing_ids)} chunks already in Qdrant; they will be skipped.")

    pending = [chunk for chunk in chunks if chunk.chunk_id not in existing_ids]
    _log(f"{len(pending)} chunks need embedding.")

    provider = get_embedding_provider(settings)
    embedded = 0
    started = time.monotonic()
    for start in range(0, len(pending), args.slice):
        batch = pending[start : start + args.slice]
        embeddings = provider.embed(
            EmbeddingProviderRequest(texts=[chunk.chunk_text for chunk in batch])
        ).embeddings
        if not embeddings or any(not embedding for embedding in embeddings):
            _log("ERROR: embedding provider returned empty vectors. Stopping; re-run to resume.")
            return 1
        vector_store.upsert_chunks(batch, embeddings)
        embedded += len(batch)
        elapsed = time.monotonic() - started
        _log(f"  embedded {embedded}/{len(pending)} (+{len(batch)})  {elapsed:0.0f}s elapsed")

    pruned = vector_store.delete_missing_chunk_ids({chunk.chunk_id for chunk in chunks})
    count = vector_store.count()
    _log(f"pruned {pruned} stale points. Qdrant now holds {count} points.")
    _log("DONE" if count >= len(chunks) else f"WARNING: count {count} < chunks {len(chunks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
