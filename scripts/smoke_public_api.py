#!/usr/bin/env python3
"""Run deployed public-beta API smoke checks without printing secrets."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = os.getenv("PUBLIC_BASE_API_URL", "https://zoning-agent-api.onrender.com").rstrip("/")
AUTH_TOKEN = os.getenv("PUBLIC_AUTH_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("PUBLIC_ADMIN_TOKEN", "").strip()
SUPPORTED_ADDRESS = os.getenv("PUBLIC_TEST_SUPPORTED_ADDRESS", "").strip()
UNSUPPORTED_ADDRESS = os.getenv("PUBLIC_TEST_UNSUPPORTED_ADDRESS", "").strip()
PROJECT_DESCRIPTION = os.getenv(
    "PUBLIC_TEST_PROJECT_DESCRIPTION",
    "Convert an attached garage into a small home bakery with two employees, posted operating hours, and interior renovation plans.",
)


class SmokeFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: Any
    text: str


def request(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    token: str | None = AUTH_TOKEN,
) -> Response:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            text = response.read().decode("utf-8", errors="replace")
            return Response(response.status, _parse_json(text), text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return Response(exc.code, _parse_json(text), text)
    except urllib.error.URLError as exc:
        raise SmokeFailure(f"{method} {path} failed to connect: {exc}") from exc


def main() -> int:
    missing = [
        name
        for name, value in {
            "PUBLIC_AUTH_TOKEN": AUTH_TOKEN,
            "PUBLIC_TEST_SUPPORTED_ADDRESS": SUPPORTED_ADDRESS,
            "PUBLIC_TEST_UNSUPPORTED_ADDRESS": UNSUPPORTED_ADDRESS,
        }.items()
        if not value
    ]
    if missing:
        print(f"Missing required environment variable(s): {', '.join(missing)}")
        return 2

    summary: dict[str, Any] = {"base_url": BASE_URL}
    health = _expect_json(request("GET", "/health", token=None), 200, "GET /health")
    ready = _expect_json(request("GET", "/ready", token=None), 200, "GET /ready")
    if ready.get("source_index_ready") is not True:
        raise SmokeFailure(f"/ready source index is not ready: {_summarize(ready)}")
    if int(ready.get("chunk_count") or 0) <= 0:
        raise SmokeFailure(f"/ready chunk_count must be nonzero: {_summarize(ready)}")

    missing_auth = request("GET", "/api/v1/me", token=None)
    if missing_auth.status != 401:
        raise SmokeFailure(f"GET /api/v1/me without auth expected 401, got {missing_auth.status}")

    me = _expect_json(request("GET", "/api/v1/me"), 200, "GET /api/v1/me")
    if not me.get("user_id"):
        raise SmokeFailure(f"/api/v1/me did not return user_id: {_summarize(me)}")

    projects = _expect_json(request("GET", "/api/v1/projects"), 200, "GET /api/v1/projects")
    if not isinstance(projects.get("projects"), list):
        raise SmokeFailure(f"/api/v1/projects missing projects list: {_summarize(projects)}")

    supported = _run_supported_flow()
    unsupported = _run_unsupported_flow()
    admin = _run_optional_admin_flow()

    summary.update(
        {
            "health": health.get("status"),
            "ready": ready.get("status"),
            "source_count": ready.get("source_count"),
            "chunk_count": ready.get("chunk_count"),
            "vector_provider": ready.get("vector_provider"),
            "user_role": me.get("role"),
            "project_count": len(projects.get("projects", [])),
            "supported": supported,
            "unsupported": unsupported,
            "admin": admin,
        }
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_supported_flow() -> dict[str, Any]:
    session = _expect_json(request("POST", "/api/v1/sessions"), 200, "POST /api/v1/sessions")
    intake = _expect_json(
        request(
            "POST",
            "/api/v1/projects/intake",
            {
                "session_id": session["session_id"],
                "project_description": PROJECT_DESCRIPTION,
                "address": SUPPORTED_ADDRESS,
            },
        ),
        200,
        "POST /api/v1/projects/intake",
    )
    if intake.get("status") != "created":
        raise SmokeFailure(f"supported intake did not create a project: {_summarize(intake)}")
    project_id = intake.get("project_id")
    analysis = _expect_json(
        request(
            "POST",
            f"/api/v1/projects/{project_id}/analyze",
            {"project_id": project_id, "clarification_answers": {}},
        ),
        200,
        "POST /api/v1/projects/{id}/analyze",
    )
    _assert_analysis_payload(analysis)
    feedback = _expect_json(
        request(
            "POST",
            f"/api/v1/projects/{project_id}/feedback",
            {"project_id": project_id, "helpful": True, "comment": "Public smoke check."},
        ),
        200,
        "POST /api/v1/projects/{id}/feedback",
    )
    if feedback.get("status") != "accepted":
        raise SmokeFailure(f"feedback did not return accepted: {_summarize(feedback)}")
    return {
        "project_id": project_id,
        "decision": analysis.get("feasibility", {}).get("decision"),
        "citations": len(analysis.get("citations", [])),
    }


def _run_unsupported_flow() -> dict[str, Any]:
    session = _expect_json(request("POST", "/api/v1/sessions"), 200, "POST /api/v1/sessions")
    response = _expect_json(
        request(
            "POST",
            "/api/v1/projects/intake",
            {
                "session_id": session["session_id"],
                "project_description": PROJECT_DESCRIPTION,
                "address": UNSUPPORTED_ADDRESS,
            },
        ),
        200,
        "POST /api/v1/projects/intake unsupported",
    )
    if response.get("status") == "created" and response.get("support_status") == "supported":
        raise SmokeFailure("unsupported address was treated as public-supported")
    if response.get("support_status") != "unsupported":
        raise SmokeFailure(f"unsupported address did not return unsupported markers: {_summarize(response)}")
    return {
        "jurisdiction_id": response.get("jurisdiction_id"),
        "coverage_status": response.get("coverage_status"),
    }


def _run_optional_admin_flow() -> dict[str, Any]:
    if not ADMIN_TOKEN:
        return {"skipped": True}
    status = _expect_json(
        request("GET", "/api/v1/ingestion/status", token=ADMIN_TOKEN),
        200,
        "GET /api/v1/ingestion/status",
    )
    usage = _expect_json(
        request("GET", "/api/v1/admin/usage", token=ADMIN_TOKEN),
        200,
        "GET /api/v1/admin/usage",
    )
    return {
        "skipped": False,
        "source_count": status.get("source_count"),
        "chunk_count": status.get("chunk_count"),
        "usage_date": usage.get("date"),
    }


def _assert_analysis_payload(body: Any) -> None:
    if not isinstance(body, dict):
        raise SmokeFailure(f"analysis was not JSON: {_summarize(body)}")
    if body.get("status") not in {"success", "needs_clarification", "low_confidence", "error"}:
        raise SmokeFailure(f"analysis returned unexpected status: {_summarize(body)}")
    if not body.get("trace_id"):
        raise SmokeFailure(f"analysis did not include trace_id: {_summarize(body)}")
    if not isinstance(body.get("feasibility"), dict):
        raise SmokeFailure(f"analysis did not include feasibility: {_summarize(body)}")
    checklist = body.get("checklist")
    if not isinstance(checklist, dict) or not isinstance(checklist.get("steps"), list):
        raise SmokeFailure(f"analysis did not include checklist steps: {_summarize(body)}")
    citations = body.get("citations")
    if not isinstance(citations, list) or not citations:
        raise SmokeFailure(f"analysis returned no citations: {_summarize(body)}")


def _expect_json(response: Response, expected_status: int, label: str) -> dict[str, Any]:
    if response.status != expected_status:
        raise SmokeFailure(f"{label} expected HTTP {expected_status}, got {response.status}: {_summarize(response.body)}")
    if not isinstance(response.body, dict):
        raise SmokeFailure(f"{label} did not return a JSON object: {_summarize(response.text)}")
    return response.body


def _parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _summarize(body: Any) -> str:
    text = json.dumps(body, sort_keys=True) if not isinstance(body, str) else body
    collapsed = " ".join(text.split())
    redacted = _redact(collapsed)
    return redacted if len(redacted) <= 500 else f"{redacted[:497]}..."


def _redact(text: str) -> str:
    redacted = text
    for secret in (AUTH_TOKEN, ADMIN_TOKEN):
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"Smoke test failed: {_redact(str(exc))}")
        raise SystemExit(1)
