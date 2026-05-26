#!/usr/bin/env python3
"""Check deployed public-beta API configuration without printing secrets."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Response:
    status: int
    body: Any
    headers: dict[str, str]


class CheckFailure(RuntimeError):
    pass


def request(method: str, url: str, *, headers: dict[str, str] | None = None) -> Response:
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
            return Response(response.status, _parse_json(text), dict(response.headers.items()))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return Response(exc.code, _parse_json(text), dict(exc.headers.items()))
    except (TimeoutError, urllib.error.URLError) as exc:
        raise CheckFailure(f"{method} {url} failed to connect: {exc}") from exc


def check(api_url: str, web_origin: str) -> dict[str, Any]:
    base = api_url.rstrip("/")
    health = request("GET", f"{base}/health", headers={"Accept": "application/json"})
    if health.status != 200:
        raise CheckFailure(f"/health returned HTTP {health.status}")
    if not isinstance(health.body, dict):
        raise CheckFailure("/health did not return JSON")

    ready = request("GET", f"{base}/ready", headers={"Accept": "application/json"})
    if ready.status != 200:
        raise CheckFailure(f"/ready returned HTTP {ready.status}")
    if not isinstance(ready.body, dict):
        raise CheckFailure("/ready did not return JSON")

    me = request("GET", f"{base}/api/v1/me", headers={"Accept": "application/json"})
    if me.status != 401:
        raise CheckFailure(
            f"/api/v1/me without auth should return 401 in production, got HTTP {me.status}"
        )

    coverage = request(
        "GET",
        f"{base}/api/v1/jurisdictions/coverage",
        headers={"Accept": "application/json"},
    )
    if coverage.status != 200:
        raise CheckFailure(f"/api/v1/jurisdictions/coverage returned HTTP {coverage.status}")

    preflight = request(
        "OPTIONS",
        f"{base}/api/v1/me",
        headers={
            "Origin": web_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    if preflight.status not in {200, 204}:
        raise CheckFailure(f"CORS preflight returned HTTP {preflight.status}")
    allowed_origin = preflight.headers.get("Access-Control-Allow-Origin", "")
    if allowed_origin not in {web_origin, "*"}:
        raise CheckFailure(
            f"CORS preflight allowed origin {allowed_origin!r}, expected {web_origin!r}"
        )

    return {
        "api_url": base,
        "web_origin": web_origin,
        "health_status": health.body.get("status"),
        "ready_status": ready.body.get("status"),
        "source_index_ready": ready.body.get("source_index_ready"),
        "source_count": ready.body.get("source_count"),
        "chunk_count": ready.body.get("chunk_count"),
        "vector_provider": ready.body.get("vector_provider"),
        "vector_index_ready": ready.body.get("vector_index_ready"),
        "warnings": ready.body.get("warnings", []),
        "auth_required": True,
        "cors_origin": allowed_origin,
    }


def _parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check deployed public-beta configuration.")
    parser.add_argument("--api-url", default="https://zoning-agent-api.onrender.com")
    parser.add_argument("--web-origin", default="https://zoning-agent-platform.vercel.app")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        print(json.dumps(check(args.api_url, args.web_origin), indent=2, sort_keys=True))
        return 0
    except CheckFailure as exc:
        print(f"Production config check failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
