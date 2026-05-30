"""Polite, cached HTTP client shared by the fetchers.

Responsibilities:
- Descriptive ``User-Agent`` identifying the project.
- Configurable per-host rate limiting (a minimum delay between requests).
- Retry of transient failures (timeouts, connection errors, 5xx, 429) with
  exponential backoff.
- On-disk caching of raw responses under the pack's ``raw/`` directory, keyed by
  a hash of the URL, so re-runs do not re-hit the network.

This deliberately avoids any third-party retry library — ``httpx`` is already a
dependency and the backoff loop here is small and explicit.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_USER_AGENT = (
    "ZoningAgentIngestion/0.1 "
    "(+https://github.com/abhihari010/Zoning-Agent-App; research; contact via repo)"
)

# HTTP status codes worth retrying.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchBlockedError(RuntimeError):
    """Raised when a host appears to block automated access.

    The caller is expected to fail gracefully and surface this message rather
    than retrying aggressively.
    """


@dataclass(slots=True)
class HttpClientConfig:
    user_agent: str = DEFAULT_USER_AGENT
    request_delay: float = 1.0
    timeout: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    cache_dir: Path | None = None


class PoliteHttpClient:
    """Thin wrapper around ``httpx.Client`` adding politeness + caching.

    Use as a context manager so the underlying connection pool is closed::

        with PoliteHttpClient(HttpClientConfig(cache_dir=raw_dir)) as client:
            text = client.get_text(url)
    """

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self.config = config or HttpClientConfig()
        self._last_request_ts: float = 0.0
        self._client = httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
            },
        )
        if self.config.cache_dir is not None:
            self.config.cache_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self) -> "PoliteHttpClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- caching ----------------------------------------------------------

    def _cache_path(self, url: str, suffix: str) -> Path | None:
        if self.config.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.config.cache_dir / f"{digest}{suffix}"

    def _read_cache(self, path: Path | None) -> str | None:
        if path is not None and path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _write_cache(self, path: Path | None, text: str) -> None:
        if path is not None:
            path.write_text(text, encoding="utf-8")

    # -- politeness -------------------------------------------------------

    def _respect_rate_limit(self) -> None:
        if self.config.request_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_ts
        wait = self.config.request_delay - elapsed
        if wait > 0:
            time.sleep(wait)

    # -- fetching ---------------------------------------------------------

    def get_text(self, url: str, *, cache_suffix: str = ".cache") -> str:
        """GET ``url`` returning the body text, using the on-disk cache first."""
        cache_path = self._cache_path(url, cache_suffix)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        text = self._get_with_retries(url)
        self._write_cache(cache_path, text)
        return text

    def _get_with_retries(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            self._respect_rate_limit()
            try:
                response = self._client.get(url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            else:
                self._last_request_ts = time.monotonic()
                status = response.status_code
                if status in (401, 403):
                    raise FetchBlockedError(
                        f"Host returned HTTP {status} for {url!r}; automated access "
                        "appears to be blocked. Stopping rather than retrying."
                    )
                if status in _RETRYABLE_STATUS:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {status}", request=response.request, response=response
                    )
                elif status >= 400:
                    response.raise_for_status()
                else:
                    return response.text
            finally:
                self._last_request_ts = time.monotonic()

            if attempt < self.config.max_retries - 1:
                sleep_for = self.config.backoff_factor ** (attempt + 1)
                time.sleep(min(sleep_for, 10.0))

        raise RuntimeError(
            f"Failed to fetch {url!r} after {self.config.max_retries} attempts: {last_error}"
        )
