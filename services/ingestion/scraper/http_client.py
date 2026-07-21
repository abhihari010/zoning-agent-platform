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

Two transports are supported behind one interface:

- ``httpx`` (default) — the standard path used by every fetcher.
- ``curl_cffi`` (opt-in, ``HttpClientConfig.impersonate``) — routes requests
  through curl-impersonate so the TLS/JA3 handshake matches a real browser
  (Chrome, Safari, ...).  Some hosts (eCode360 behind Cloudflare) block the
  Python/OpenSSL TLS fingerprint outright; presenting Chrome's fingerprint can
  clear that block.  ``curl_cffi`` is an OPTIONAL dependency — it is imported
  lazily, only when ``impersonate`` is set, so the default httpx path and the
  offline test suite never require it.

Both transports share the same retry/backoff/cache/rate-limit and
fail-closed-on-401/403 semantics.
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
    # Opt-in TLS-fingerprint impersonation profile (e.g. ``"chrome"``,
    # ``"chrome131"``, ``"safari"``).  When ``None`` (default) the standard
    # httpx transport is used and ``curl_cffi`` is never imported.
    impersonate: str | None = None


class PoliteHttpClient:
    """Thin wrapper around ``httpx.Client`` adding politeness + caching.

    Use as a context manager so the underlying connection pool is closed::

        with PoliteHttpClient(HttpClientConfig(cache_dir=raw_dir)) as client:
            text = client.get_text(url)
    """

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self.config = config or HttpClientConfig()
        self._last_request_ts: float = 0.0
        # Transport exceptions to treat as transient (retryable); populated per
        # transport so the retry loop stays transport-agnostic.
        self._transport_exceptions: tuple[type[BaseException], ...] = ()
        if self.config.impersonate:
            self._transport = "curl_cffi"
            self._client = self._build_impersonate_client()
        else:
            self._transport = "httpx"
            self._transport_exceptions = (
                httpx.TimeoutException,
                httpx.TransportError,
            )
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

    def _build_impersonate_client(self):
        """Build a curl_cffi session presenting a browser TLS fingerprint.

        ``curl_cffi`` is imported here (and only here) so it stays an optional
        dependency: the default httpx path never touches it.
        """
        try:
            from curl_cffi import requests as cffi_requests
        except ImportError as exc:  # pragma: no cover - exercised via message
            raise ImportError(
                "curl_cffi is required for the impersonation transport. "
                "Install it with: pip install curl_cffi"
            ) from exc

        # Resolve the transport exception base across curl_cffi versions.
        try:
            from curl_cffi.requests.exceptions import RequestException as _CffiError
        except Exception:  # pragma: no cover - older curl_cffi layout
            try:
                from curl_cffi.requests.errors import RequestsError as _CffiError
            except Exception:
                _CffiError = Exception  # type: ignore[assignment]
        self._transport_exceptions = (_CffiError,)

        # The impersonate profile sets a full, browser-consistent header set
        # (User-Agent, Accept, sec-ch-* hints, ...).  We intentionally do NOT
        # override those headers so the fingerprint stays internally consistent.
        return cffi_requests.Session(
            impersonate=self.config.impersonate,
            timeout=self.config.timeout,
            allow_redirects=True,
        )

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
        # Municode doc node ids can encode entire headings, producing suffixes
        # that push the path past Windows' 260-char MAX_PATH — clamp long
        # suffixes to a stable digest-tagged stem (the URL digest already
        # guarantees uniqueness; the suffix is only a human-readable hint).
        if len(suffix) > 80:
            ext = Path(suffix).suffix or ".cache"
            suffix = f".{hashlib.sha256(suffix.encode('utf-8')).hexdigest()[:12]}{ext}"
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
            except self._transport_exceptions as exc:
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
                    last_error = self._status_error(response, status)
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

    def _status_error(self, response: object, status: int) -> Exception:
        """Build a transient-status error for the retry loop's ``last_error``.

        Preserves the exact ``httpx.HTTPStatusError`` for the httpx transport
        (so that path is byte-for-byte unchanged); the curl_cffi transport uses
        a plain RuntimeError since it has no httpx request/response objects.
        """
        if self._transport == "httpx":
            return httpx.HTTPStatusError(
                f"HTTP {status}",
                request=response.request,  # type: ignore[attr-defined]
                response=response,  # type: ignore[arg-type]
            )
        return RuntimeError(f"HTTP {status} (curl_cffi transport)")
