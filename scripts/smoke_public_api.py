from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.getenv("PUBLIC_BASE_API_URL", "https://zoning-agent-api.onrender.com").rstrip("/")
AUTH_TOKEN = os.getenv("PUBLIC_AUTH_TOKEN", "").strip()
SUPPORTED_ADDRESS = os.getenv("PUBLIC_TEST_SUPPORTED_ADDRESS", "").strip()
PROJECT_DESCRIPTION = os.getenv(
    "PUBLIC_TEST_PROJECT_DESCRIPTION",
    "Convert an attached garage into a small home bakery with two employees, posted operating hours, and interior renovation plans.",
)


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    if not AUTH_TOKEN:
        print("PUBLIC_AUTH_TOKEN is required; it will not be printed.")
        return 2

    health_status, health = request("GET", "/health")
    require(health_status == 200, f"/health returned {health_status}")
    require(health.get("status") in {"ok", "warning"}, "/health missing status")

    me_status, me = request("GET", "/api/v1/me")
    require(me_status == 200, f"/api/v1/me returned {me_status}")
    require(me.get("user_id"), "/api/v1/me did not return user_id")

    source_status, sources = request("GET", "/api/v1/ingestion/status")
    require(source_status == 200, f"/api/v1/ingestion/status returned {source_status}")
    require(sources.get("source_count", 0) > 0, "source_count is zero")
    require(sources.get("chunk_count", 0) > 0, "chunk_count is zero")

    projects_status, projects = request("GET", "/api/v1/projects")
    require(projects_status == 200, f"/api/v1/projects returned {projects_status}")
    require("projects" in projects, "/api/v1/projects missing projects")

    analysis_summary: dict[str, object] = {"skipped": True}
    if SUPPORTED_ADDRESS:
        session_status, session = request("POST", "/api/v1/sessions")
        require(session_status == 200, f"/api/v1/sessions returned {session_status}")
        intake_status, intake = request(
            "POST",
            "/api/v1/projects/intake",
            {
                "session_id": session["session_id"],
                "project_description": PROJECT_DESCRIPTION,
                "address": SUPPORTED_ADDRESS,
            },
        )
        require(intake_status == 200, f"/api/v1/projects/intake returned {intake_status}")
        require(intake.get("status") == "created", f"intake status was {intake.get('status')}")

        analyze_status, analysis = request(
            "POST",
            f"/api/v1/projects/{intake['project_id']}/analyze",
            {
                "project_id": intake["project_id"],
                "clarification_answers": {},
            },
        )
        require(analyze_status == 200, f"/api/v1/projects/{{id}}/analyze returned {analyze_status}")
        require(analysis.get("citations"), "analysis did not return citations")
        analysis_summary = {
            "skipped": False,
            "decision": analysis.get("feasibility", {}).get("decision"),
            "confidence": analysis.get("feasibility", {}).get("confidence"),
            "citations": len(analysis.get("citations", [])),
            "warnings": len(analysis.get("warnings", [])),
        }

    print(
        json.dumps(
            {
                "base_url": BASE_URL,
                "health": health.get("status"),
                "source_count": sources.get("source_count"),
                "chunk_count": sources.get("chunk_count"),
                "user_role": me.get("role"),
                "project_count": len(projects.get("projects", [])),
                "analysis": analysis_summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"Smoke test failed: {exc}")
        raise SystemExit(1)
