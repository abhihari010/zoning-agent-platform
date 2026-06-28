from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from app.ai.gemini_batch_embedding import (
    BatchChunk,
    build_request_lines,
    parse_result_lines,
    run_batch_embedding,
)


def test_build_request_lines_keys_by_chunk_id_and_sets_dimensions() -> None:
    chunks = [BatchChunk("c1", "alpha text"), BatchChunk("c2", "beta text")]

    lines = build_request_lines(chunks, dimensions=768)

    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["key"] == "c1"
    assert first["request"]["content"]["parts"][0]["text"] == "alpha text"
    assert first["request"]["output_dimensionality"] == 768


def test_build_request_lines_omits_dimensions_when_none() -> None:
    lines = build_request_lines([BatchChunk("c1", "x")], dimensions=None)

    assert "output_dimensionality" not in json.loads(lines[0])["request"]


def test_parse_result_lines_normalizes_and_keys_by_chunk_id() -> None:
    lines = [
        json.dumps({"key": "c1", "response": {"embedding": {"values": [3.0, 4.0]}}}),
        "",  # blank lines are skipped
        json.dumps({"key": "c2", "response": {"embeddings": [{"values": [0.0, 5.0]}]}}),
    ]

    vectors = parse_result_lines(lines)

    assert set(vectors) == {"c1", "c2"}
    # [3,4] -> magnitude 5 -> [0.6, 0.8]
    assert vectors["c1"] == pytest.approx([0.6, 0.8])
    assert vectors["c2"] == pytest.approx([0.0, 1.0])
    # all unit length
    for vec in vectors.values():
        assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0)


def test_parse_result_lines_raises_on_unknown_schema() -> None:
    lines = [json.dumps({"key": "c1", "response": {"unexpected": "shape"}})]

    with pytest.raises(RuntimeError, match="response schema may have changed"):
        parse_result_lines(lines)


class _FakeFiles:
    def __init__(self, result_text: str) -> None:
        self._result_text = result_text
        self.uploaded: list[str] = []

    def upload(self, *, file: str):
        self.uploaded.append(file)
        return SimpleNamespace(name="files/uploaded-1")

    def download(self, *, file: str) -> bytes:
        return self._result_text.encode("utf-8")


class _FakeBatches:
    def __init__(self, states: list[str]) -> None:
        self._states = states
        self.created: list[dict] = []
        self._poll_index = 0

    def create_embeddings(self, *, model: str, src: dict):
        self.created.append({"model": model, "src": src})
        return SimpleNamespace(name="batches/job-1")

    def get(self, *, name: str):
        state = self._states[min(self._poll_index, len(self._states) - 1)]
        self._poll_index += 1
        return SimpleNamespace(
            name=name,
            state=SimpleNamespace(name=state),
            dest=SimpleNamespace(file_name="files/result-1"),
            error=None,
        )


class _FakeClient:
    def __init__(self, result_text: str, states: list[str]) -> None:
        self.files = _FakeFiles(result_text)
        self.batches = _FakeBatches(states)


def test_run_batch_embedding_submits_polls_and_returns_vectors(tmp_path) -> None:
    result_text = "\n".join(
        [
            json.dumps({"key": "c1", "response": {"embedding": {"values": [3.0, 4.0]}}}),
            json.dumps({"key": "c2", "response": {"embedding": {"values": [0.0, 1.0]}}}),
        ]
    )
    client = _FakeClient(result_text, states=["JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED"])

    vectors = run_batch_embedding(
        [BatchChunk("c1", "a"), BatchChunk("c2", "b")],
        api_key="unused",
        model="models/gemini-embedding-001",
        dimensions=768,
        work_dir=tmp_path,
        poll_interval_seconds=0,
        client=client,
    )

    assert set(vectors) == {"c1", "c2"}
    # model id passed to the SDK has the "models/" prefix stripped.
    assert client.batches.created[0]["model"] == "gemini-embedding-001"
    assert client.batches.created[0]["src"] == {"file_name": "files/uploaded-1"}
    # state file is cleaned up after a successful download.
    assert not (tmp_path / "reindex_batch_job.json").exists()


def test_run_batch_embedding_resumes_existing_job_without_resubmitting(tmp_path) -> None:
    (tmp_path / "reindex_batch_job.json").write_text(
        json.dumps({"job_name": "batches/existing-job"}), encoding="utf-8"
    )
    result_text = json.dumps({"key": "c1", "response": {"embedding": {"values": [1.0, 0.0]}}})
    client = _FakeClient(result_text, states=["JOB_STATE_SUCCEEDED"])

    vectors = run_batch_embedding(
        [BatchChunk("c1", "a")],
        api_key="unused",
        model="gemini-embedding-001",
        dimensions=None,
        work_dir=tmp_path,
        poll_interval_seconds=0,
        client=client,
    )

    assert set(vectors) == {"c1"}
    # resumed: no new job created, no file uploaded.
    assert client.batches.created == []
    assert client.files.uploaded == []


def test_run_batch_embedding_raises_on_failed_job(tmp_path) -> None:
    client = _FakeClient("", states=["JOB_STATE_FAILED"])

    with pytest.raises(RuntimeError, match="JOB_STATE_FAILED"):
        run_batch_embedding(
            [BatchChunk("c1", "a")],
            api_key="unused",
            model="gemini-embedding-001",
            dimensions=None,
            work_dir=tmp_path,
            poll_interval_seconds=0,
            client=client,
        )
    # state file is kept for inspection on failure.
    assert (tmp_path / "reindex_batch_job.json").exists()
