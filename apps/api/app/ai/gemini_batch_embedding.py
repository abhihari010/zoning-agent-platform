"""Asynchronous Gemini Batch API embeddings for the OFFLINE bulk reindex.

The synchronous :class:`GeminiEmbeddingProvider` (``embedding_provider.py``) powers
the live retrieval path and the admin "Reindex" button -- both need an immediate
result. This module is different: it drives the Gemini **Batch API**, which
processes embeddings asynchronously at **half the price** ($0.075 vs $0.15 per 1M
input tokens) with a target turnaround of up to 24h (usually much faster). That
latency means it is only suitable for ``scripts/reindex_prod.py --batch`` -- a
full re-embed of the corpus is non-urgent, so the discount is free money.

Flow: write a JSONL file of requests keyed by ``chunk_id`` -> upload via the Files
API -> ``batches.create_embeddings`` -> poll until terminal -> download the result
file -> map ``chunk_id`` back to its (normalized) vector. The job name is persisted
so a killed run resumes polling instead of resubmitting (and re-paying).

Requires the optional ``google-genai`` dependency::

    pip install -e '.[batch]'

It is imported lazily so the rest of the app never depends on it.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

# Batch jobs end in exactly one of these states (mirrors the genai SDK enum names).
TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}

_STATE_FILE_NAME = "reindex_batch_job.json"
_REQUESTS_FILE_NAME = "embedding_requests.jsonl"


@dataclass(frozen=True)
class BatchChunk:
    """The minimal chunk shape the batch path needs: an id to key on + its text."""

    chunk_id: str
    text: str


def _normalize(vector: list[float]) -> list[float]:
    """Unit-normalize so dot-product == cosine in the hybrid retriever.

    Gemini returns un-normalized vectors when ``output_dimensionality`` truncates
    below the native 3072, so we normalize here exactly like the sync provider.
    """
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def build_request_lines(chunks: Sequence[BatchChunk], dimensions: int | None) -> list[str]:
    """Build JSONL request lines keyed by ``chunk_id`` for the batch input file.

    Shape per the Gemini batch-embeddings docs::

        {"key": "<chunk_id>", "request": {"output_dimensionality": N,
                                           "content": {"parts": [{"text": "..."}]}}}
    """
    lines: list[str] = []
    for chunk in chunks:
        request: dict[str, Any] = {"content": {"parts": [{"text": chunk.text}]}}
        if dimensions:
            request["output_dimensionality"] = dimensions
        lines.append(json.dumps({"key": chunk.chunk_id, "request": request}))
    return lines


def _extract_values(response: Any) -> list[float]:
    """Pull the embedding vector out of a single result's ``response`` object.

    The Batch API result schema for embeddings is not fully pinned in the public
    docs, so accept the handful of shapes Gemini is known to emit rather than
    assuming one. Returns ``[]`` when none match (caller treats as missing)."""
    if not isinstance(response, dict):
        return []
    # {"response": {"embedding": {"values": [...]}}}
    embedding = response.get("embedding")
    if isinstance(embedding, dict) and isinstance(embedding.get("values"), list):
        return embedding["values"]
    # {"response": {"embeddings": [{"values": [...]}]}}
    embeddings = response.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], dict):
        values = embeddings[0].get("values")
        if isinstance(values, list):
            return values
    # {"response": {"values": [...]}} (flattened)
    values = response.get("values")
    if isinstance(values, list):
        return values
    return []


def parse_result_lines(lines: Sequence[str]) -> dict[str, list[float]]:
    """Map ``chunk_id`` -> normalized vector from the downloaded JSONL result file."""
    vectors: dict[str, list[float]] = {}
    sample_unparsed: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        key = obj.get("key")
        values = _extract_values(obj.get("response"))
        if key and values:
            vectors[key] = _normalize(values)
        elif sample_unparsed is None:
            sample_unparsed = line[:500]
    if not vectors and sample_unparsed is not None:
        raise RuntimeError(
            "Could not extract any embeddings from the batch result file. The "
            f"response schema may have changed. First unparsed line: {sample_unparsed}"
        )
    return vectors


def _import_genai() -> Any:
    try:
        from google import genai  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "Batch embedding mode requires the optional 'google-genai' package. "
            "Install it with:  pip install -e '.[batch]'"
        ) from exc
    return genai


def run_batch_embedding(
    chunks: Sequence[BatchChunk],
    *,
    api_key: str,
    model: str,
    dimensions: int | None,
    work_dir: str | Path,
    poll_interval_seconds: float = 30.0,
    log: Callable[[str], None] = print,
    client: Any | None = None,
) -> dict[str, list[float]]:
    """Embed ``chunks`` via the Gemini Batch API and return chunk_id -> vector.

    Resumable: the created job name is written to ``work_dir/reindex_batch_job.json``;
    if that file exists on entry we resume polling the existing job instead of
    resubmitting. The state file is removed once results are downloaded.

    ``client`` may be injected for testing; otherwise a ``genai.Client`` is built.
    """
    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)
    state_path = work_path / _STATE_FILE_NAME

    if client is None:
        genai = _import_genai()
        client = genai.Client(api_key=api_key)

    # genai's create_embeddings expects a bare model id (no "models/" prefix).
    model_id = model[len("models/") :] if model.startswith("models/") else model

    job_name: str | None = None
    if state_path.exists():
        job_name = json.loads(state_path.read_text(encoding="utf-8")).get("job_name")
        log(f"resuming existing batch job {job_name} (delete {state_path} to start over)")

    if not job_name:
        requests_path = work_path / _REQUESTS_FILE_NAME
        requests_path.write_text(
            "\n".join(build_request_lines(chunks, dimensions)) + "\n", encoding="utf-8"
        )
        log(f"wrote {len(chunks)} embedding requests to {requests_path}")
        uploaded = client.files.upload(file=str(requests_path))
        log(f"uploaded request file as {uploaded.name}")
        job = client.batches.create_embeddings(
            model=model_id, src={"file_name": uploaded.name}
        )
        job_name = job.name
        state_path.write_text(json.dumps({"job_name": job_name}), encoding="utf-8")
        log(f"created batch embedding job {job_name}")

    state = ""
    job = None
    while True:
        job = client.batches.get(name=job_name)
        state = job.state.name
        if state in TERMINAL_STATES:
            break
        log(f"  job {state}; polling again in {poll_interval_seconds:0.0f}s")
        time.sleep(poll_interval_seconds)

    if state != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(
            f"batch job {job_name} ended in {state}: {getattr(job, 'error', None)}. "
            f"State file kept at {state_path} for inspection."
        )

    result_file = job.dest.file_name
    log(f"job succeeded; downloading results from {result_file}")
    content = client.files.download(file=result_file)
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    vectors = parse_result_lines(content.splitlines())
    log(f"parsed {len(vectors)} embeddings from batch result.")

    state_path.unlink(missing_ok=True)
    return vectors
