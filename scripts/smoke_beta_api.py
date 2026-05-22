#!/usr/bin/env python3
"""Run deployed beta API smoke checks.

Required environment:
  BETA_ACCESS_KEY
  BETA_TEST_SUPPORTED_ADDRESS
  BETA_TEST_UNSUPPORTED_ADDRESS

Optional environment:
  BETA_BASE_API_URL, defaulting to https://zoning-agent-api.onrender.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_API_URL = "https://zoning-agent-api.onrender.com"
INVALID_BETA_KEY = "__invalid_beta_smoke_key__"
INVALID_ADDRESS = "0 Not A Real Zoning Smoke Test Address, Nowhere, ZZ 00000"
PROJECT_DESCRIPTION = (
    "Convert an existing residential garage into a small home bakery with two employees, "
    "limited customer pickup hours, and no exterior signage."
)


class SmokeFailure(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    body: Any
    text: str


class SmokeClient:
    def __init__(self, base_url: str, beta_key: str, timeout: float) -> None:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/api/v1"):
            normalized = normalized[: -len("/api/v1")]
        self.base_url = normalized
        self.api_url = f"{normalized}/api/v1"
        self.beta_key = beta_key
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        beta_key: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Response:
        if path == "/health":
            url = f"{self.base_url}{path}"
        elif path.startswith("/api/v1/"):
            url = f"{self.base_url}{path}"
        elif path.startswith("/"):
            url = f"{self.api_url}{path}"
        else:
            url = f"{self.api_url}/{path}"

        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if beta_key is not None:
            headers["X-Beta-Access-Key"] = beta_key

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as raw_response:
                text = raw_response.read().decode("utf-8", errors="replace")
                return Response(raw_response.status, _parse_json(text), text)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return Response(exc.code, _parse_json(text), text)
        except urllib.error.URLError as exc:
            raise SmokeFailure(f"{method} {path} failed to connect: {exc}") from exc
        except TimeoutError as exc:
            raise SmokeFailure(f"{method} {path} timed out after {self.timeout:g}s") from exc

    def get(self, path: str, *, beta_key: str | None = None) -> Response:
        return self.request("GET", path, beta_key=beta_key)

    def post(
        self,
        path: str,
        *,
        beta_key: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Response:
        return self.request("POST", path, beta_key=beta_key, json_body=json_body)


class SmokeRunner:
    def __init__(self, client: SmokeClient, supported_address: str, unsupported_address: str) -> None:
        self.client = client
        self.supported_address = supported_address
        self.unsupported_address = unsupported_address
        self.failures: list[str] = []

    def run(self) -> int:
        checks = [
            ("health", self.check_health),
            ("missing beta key", self.check_missing_beta_key),
            ("invalid beta key", self.check_invalid_beta_key),
            ("ingestion readiness", self.check_ingestion_readiness),
            ("supported intake/analyze", self.check_supported_flow),
            ("unsupported jurisdiction", self.check_unsupported_flow),
        ]

        print(f"Smoke target: {self.client.base_url}")
        print("Secrets: BETA_ACCESS_KEY=<redacted>")

        for name, check in checks:
            try:
                detail = check()
            except SmokeFailure as exc:
                self.failures.append(f"{name}: {_redact(str(exc), self.client.beta_key)}")
                print(f"FAIL {name}: {_redact(str(exc), self.client.beta_key)}")
            else:
                print(f"PASS {name}: {_redact(detail, self.client.beta_key)}")

        if self.failures:
            print("\nSmoke test failed:")
            for failure in self.failures:
                print(f"- {_redact(failure, self.client.beta_key)}")
            return 1

        print("\nSmoke test passed.")
        return 0

    def check_health(self) -> str:
        response = self.client.request("GET", "/health")
        _expect_status(response, 200, "GET /health")
        if _json_get(response.body, "status") != "ok":
            raise SmokeFailure(f"GET /health returned unexpected body: {_summarize(response.body)}")
        return "GET /health returned ok"

    def check_missing_beta_key(self) -> str:
        response = self.client.post("/sessions")
        _expect_status(response, 401, "POST /api/v1/sessions without beta key")
        return "protected route returned 401 without key"

    def check_invalid_beta_key(self) -> str:
        invalid_key = INVALID_BETA_KEY
        if invalid_key == self.client.beta_key:
            invalid_key = f"{INVALID_BETA_KEY}-wrong"
        response = self.client.post("/sessions", beta_key=invalid_key)
        _expect_status(response, 403, "POST /api/v1/sessions with invalid beta key")
        return "protected route returned 403 with invalid key"

    def check_ingestion_readiness(self) -> str:
        status = self._ingestion_status()
        source_count = _json_int(status.body, "source_count")
        chunk_count = _json_int(status.body, "chunk_count")
        if source_count <= 0:
            raise SmokeFailure(f"source_count must be nonzero: {_summarize(status.body)}")

        if chunk_count <= 0:
            reindex = self.client.post("/ingestion/reindex", beta_key=self.client.beta_key)
            _expect_status(reindex, 200, "POST /api/v1/ingestion/reindex")
            reindex_chunks = _json_int(reindex.body, "chunk_count")
            if reindex_chunks <= 0:
                raise SmokeFailure(f"reindex did not create chunks: {_summarize(reindex.body)}")
            status = self._ingestion_status()
            chunk_count = _json_int(status.body, "chunk_count")
            if chunk_count <= 0:
                raise SmokeFailure(f"chunk_count still zero after reindex: {_summarize(status.body)}")

        readiness_bits = _collect_readiness_bits(status.body)
        suffix = f"; readiness={readiness_bits}" if readiness_bits else ""
        return f"sources={source_count}, chunks={chunk_count}{suffix}"

    def check_supported_flow(self) -> str:
        session_id = self._create_session()
        intake = self.client.post(
            "/projects/intake",
            beta_key=self.client.beta_key,
            json_body={
                "session_id": session_id,
                "project_description": PROJECT_DESCRIPTION,
                "address": self.supported_address,
            },
        )
        _expect_status(intake, 200, "POST /api/v1/projects/intake for supported address")
        if _json_get(intake.body, "status") != "created":
            raise SmokeFailure(f"supported intake did not create a project: {_summarize(intake.body)}")
        project_id = _json_get(intake.body, "project_id")
        if not isinstance(project_id, str) or not project_id:
            raise SmokeFailure(f"supported intake did not return project_id: {_summarize(intake.body)}")

        analysis = self.client.post(
            f"/projects/{project_id}/analyze",
            beta_key=self.client.beta_key,
            json_body={"project_id": project_id, "clarification_answers": {}},
        )
        _expect_status(analysis, 200, f"POST /api/v1/projects/{project_id}/analyze")
        self._assert_analysis_payload(analysis.body, "analysis response")

        result = self.client.get(f"/projects/{project_id}/result", beta_key=self.client.beta_key)
        _expect_status(result, 200, f"GET /api/v1/projects/{project_id}/result")
        self._assert_analysis_payload(result.body, "stored result")

        trace = self.client.get(f"/projects/{project_id}/trace", beta_key=self.client.beta_key)
        _expect_status(trace, 200, f"GET /api/v1/projects/{project_id}/trace")
        events = _json_get(trace.body, "events")
        if not isinstance(events, list) or not events:
            raise SmokeFailure(f"trace endpoint returned no events: {_summarize(trace.body)}")

        return (
            f"project={project_id}, status={_json_get(result.body, 'status')}, "
            f"citations={len(_json_get(result.body, 'citations') or [])}, trace_events={len(events)}"
        )

    def check_unsupported_flow(self) -> str:
        session_id = self._create_session()
        unsupported = self.client.post(
            "/projects/intake",
            beta_key=self.client.beta_key,
            json_body={
                "session_id": session_id,
                "project_description": PROJECT_DESCRIPTION,
                "address": self.unsupported_address,
            },
        )
        _expect_status(unsupported, 200, "POST /api/v1/projects/intake for unsupported address")
        if _json_get(unsupported.body, "status") == "created":
            raise SmokeFailure(
                "BETA_TEST_UNSUPPORTED_ADDRESS produced a supported project; "
                "choose an address in a recognized but unsupported jurisdiction"
            )

        invalid = self.client.post(
            "/projects/intake",
            beta_key=self.client.beta_key,
            json_body={
                "session_id": session_id,
                "project_description": PROJECT_DESCRIPTION,
                "address": INVALID_ADDRESS,
            },
        )
        if invalid.status not in {200, 400, 422, 502, 503}:
            raise SmokeFailure(
                f"invalid-address probe returned unexpected status {invalid.status}: "
                f"{_summarize(invalid.body)}"
            )

        unsupported_markers = _status_markers(unsupported.body)
        invalid_markers = _status_markers(invalid.body)
        if not _looks_unsupported(unsupported.body):
            raise SmokeFailure(
                "unsupported-address response did not expose unsupported-jurisdiction markers: "
                f"{_summarize(unsupported.body)}"
            )
        if _normalize_markers(unsupported_markers) == _normalize_markers(invalid_markers):
            raise SmokeFailure(
                "unsupported and invalid address responses were not distinguishable: "
                f"unsupported={_summarize(unsupported.body)} invalid={_summarize(invalid.body)}"
            )

        return "unsupported jurisdiction response is distinct from invalid-address probe"

    def _create_session(self) -> str:
        session = self.client.post("/sessions", beta_key=self.client.beta_key)
        _expect_status(session, 200, "POST /api/v1/sessions")
        session_id = _json_get(session.body, "session_id")
        if not isinstance(session_id, str) or not session_id:
            raise SmokeFailure(f"session response did not include session_id: {_summarize(session.body)}")
        return session_id

    def _ingestion_status(self) -> Response:
        response = self.client.get("/ingestion/status", beta_key=self.client.beta_key)
        _expect_status(response, 200, "GET /api/v1/ingestion/status")
        return response

    def _assert_analysis_payload(self, body: Any, label: str) -> None:
        status = _json_get(body, "status")
        if status not in {"success", "needs_clarification", "low_confidence", "error"}:
            raise SmokeFailure(f"{label} returned unexpected status: {_summarize(body)}")
        if not _json_get(body, "trace_id"):
            raise SmokeFailure(f"{label} did not include trace_id: {_summarize(body)}")
        if not isinstance(_json_get(body, "feasibility"), dict):
            raise SmokeFailure(f"{label} did not include feasibility: {_summarize(body)}")
        checklist = _json_get(body, "checklist")
        if not isinstance(checklist, dict) or not isinstance(checklist.get("steps"), list):
            raise SmokeFailure(f"{label} did not include checklist steps: {_summarize(body)}")
        citations = _json_get(body, "citations")
        if not isinstance(citations, list):
            raise SmokeFailure(f"{label} did not include citations/evidence list: {_summarize(body)}")
        if not citations:
            raise SmokeFailure(f"{label} returned no citations/evidence: {_summarize(body)}")


def _parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _expect_status(response: Response, expected: int, label: str) -> None:
    if response.status != expected:
        raise SmokeFailure(
            f"{label} expected HTTP {expected}, got {response.status}: {_summarize(response.body)}"
        )


def _json_get(body: Any, key: str) -> Any:
    return body.get(key) if isinstance(body, dict) else None


def _json_int(body: Any, key: str) -> int:
    value = _json_get(body, key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    raise SmokeFailure(f"response missing integer {key}: {_summarize(body)}")


def _summarize(body: Any) -> str:
    text = json.dumps(body, sort_keys=True) if not isinstance(body, str) else body
    collapsed = " ".join(text.split())
    if len(collapsed) > 500:
        return f"{collapsed[:497]}..."
    return collapsed


def _redact(text: str, secret: str) -> str:
    redacted = text
    if secret:
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


def _collect_readiness_bits(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    keys = [
        "has_index",
        "index_ready",
        "is_ready",
        "ready",
        "needs_reindex",
        "stale_chunk_count",
        "missing_chunk_count",
    ]
    bits = [f"{key}={body[key]}" for key in keys if key in body]
    if isinstance(body.get("sources_missing_metadata"), list):
        bits.append(f"sources_missing_metadata={len(body['sources_missing_metadata'])}")
    return ", ".join(bits)


def _status_markers(body: Any) -> list[str]:
    markers: list[str] = []
    if isinstance(body, dict):
        for key in (
            "status",
            "support_status",
            "jurisdiction_status",
            "reason",
            "detail",
            "normalized_address",
            "district",
        ):
            value = body.get(key)
            if isinstance(value, str):
                markers.append(f"{key}:{value}")
        followups = body.get("follow_up_questions")
        if isinstance(followups, list):
            markers.extend(str(item) for item in followups)
        warnings = body.get("warnings")
        if isinstance(warnings, list):
            markers.extend(str(item) for item in warnings)
    elif isinstance(body, str):
        markers.append(body)
    return markers


def _looks_unsupported(body: Any) -> bool:
    text = _normalize_markers(_status_markers(body))
    unsupported_words = ("unsupported", "not yet support", "does not yet support", "coverage")
    invalid_only_words = ("could not be validated", "appears incomplete")
    return any(word in text for word in unsupported_words) and not all(
        word in text for word in invalid_only_words
    )


def _normalize_markers(markers: list[str]) -> str:
    return " ".join(markers).strip().lower()


def _env(name: str, *, default: str | None = None) -> str:
    value = os.getenv(name, default or "").strip()
    if not value:
        raise SmokeFailure(f"Missing required environment variable {name}")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deployed Zoning Agent beta API smoke checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Environment:
              BETA_BASE_API_URL                 API origin, default https://zoning-agent-api.onrender.com
              BETA_ACCESS_KEY                   private beta key, never printed
              BETA_TEST_SUPPORTED_ADDRESS       supported-jurisdiction address
              BETA_TEST_UNSUPPORTED_ADDRESS     valid address outside supported coverage
            """
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("BETA_SMOKE_TIMEOUT_SECONDS", "30")),
        help="HTTP timeout in seconds (default: env BETA_SMOKE_TIMEOUT_SECONDS or 30)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        base_url = _env("BETA_BASE_API_URL", default=DEFAULT_BASE_API_URL)
        beta_key = _env("BETA_ACCESS_KEY")
        supported_address = _env("BETA_TEST_SUPPORTED_ADDRESS")
        unsupported_address = _env("BETA_TEST_UNSUPPORTED_ADDRESS")
        client = SmokeClient(base_url=base_url, beta_key=beta_key, timeout=args.timeout)
        return SmokeRunner(client, supported_address, unsupported_address).run()
    except SmokeFailure as exc:
        message = str(exc)
        secret = os.getenv("BETA_ACCESS_KEY", "").strip()
        print(f"Smoke setup failed: {_redact(message, secret)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
