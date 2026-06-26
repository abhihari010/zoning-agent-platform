"""Offline tests for PoliteHttpClient transport selection.

These assert that the impersonation branch is taken when configured and the
httpx branch otherwise — WITHOUT importing the real ``curl_cffi`` package and
WITHOUT hitting the network.  The default httpx path must keep working even when
``curl_cffi`` is not installed.
"""

from __future__ import annotations

import sys
import types

import httpx
import pytest

from services.ingestion.scraper.http_client import (
    FetchBlockedError,
    HttpClientConfig,
    PoliteHttpClient,
)


def test_default_transport_is_httpx_without_curl_cffi():
    """No impersonate => httpx transport, no curl_cffi import required."""
    config = HttpClientConfig(request_delay=0)
    with PoliteHttpClient(config) as client:
        assert client._transport == "httpx"
        assert isinstance(client._client, httpx.Client)
        # httpx transient exceptions are registered for the retry loop.
        assert httpx.TimeoutException in client._transport_exceptions


def _install_fake_curl_cffi(monkeypatch, recorder):
    """Inject a fake ``curl_cffi`` package into sys.modules (no real dep)."""

    class FakeSession:
        def __init__(self, **kwargs):
            recorder["init_kwargs"] = kwargs

        def get(self, url, **kwargs):
            recorder.setdefault("gets", []).append((url, kwargs))
            return types.SimpleNamespace(status_code=200, text="IMPERSONATED-OK")

        def close(self):
            recorder["closed"] = True

    class RequestException(Exception):
        pass

    exceptions_mod = types.ModuleType("curl_cffi.requests.exceptions")
    exceptions_mod.RequestException = RequestException

    requests_mod = types.ModuleType("curl_cffi.requests")
    requests_mod.Session = FakeSession
    requests_mod.exceptions = exceptions_mod

    root_mod = types.ModuleType("curl_cffi")
    root_mod.requests = requests_mod

    monkeypatch.setitem(sys.modules, "curl_cffi", root_mod)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", requests_mod)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests.exceptions", exceptions_mod)
    return RequestException


def test_impersonate_selects_curl_cffi_transport(monkeypatch):
    recorder: dict = {}
    request_exc = _install_fake_curl_cffi(monkeypatch, recorder)

    config = HttpClientConfig(impersonate="chrome", request_delay=0)
    with PoliteHttpClient(config) as client:
        assert client._transport == "curl_cffi"
        # The impersonate profile is passed through to the curl_cffi session.
        assert recorder["init_kwargs"].get("impersonate") == "chrome"
        # The curl_cffi transport exception is registered for retries.
        assert client._transport_exceptions == (request_exc,)

        text = client.get_text("https://ecode360.com/toc/MI2395")

    assert text == "IMPERSONATED-OK"
    assert recorder["gets"][0][0] == "https://ecode360.com/toc/MI2395"
    assert recorder["closed"] is True


def test_impersonate_transport_still_fails_closed_on_403(monkeypatch):
    """The fail-closed-on-403 contract applies to BOTH transports."""
    recorder: dict = {}

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        def get(self, url, **kwargs):
            return types.SimpleNamespace(status_code=403, text="blocked")

        def close(self):
            pass

    exceptions_mod = types.ModuleType("curl_cffi.requests.exceptions")
    exceptions_mod.RequestException = type("RequestException", (Exception,), {})
    requests_mod = types.ModuleType("curl_cffi.requests")
    requests_mod.Session = FakeSession
    requests_mod.exceptions = exceptions_mod
    root_mod = types.ModuleType("curl_cffi")
    root_mod.requests = requests_mod
    monkeypatch.setitem(sys.modules, "curl_cffi", root_mod)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", requests_mod)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests.exceptions", exceptions_mod)

    config = HttpClientConfig(impersonate="chrome", request_delay=0)
    with PoliteHttpClient(config) as client:
        with pytest.raises(FetchBlockedError):
            client.get_text("https://ecode360.com/toc/MI2395")


def test_missing_curl_cffi_raises_clear_install_hint(monkeypatch):
    """When curl_cffi is absent, the impersonation path gives an actionable error."""
    # Force the import to fail even if curl_cffi happens to be installed.
    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    config = HttpClientConfig(impersonate="chrome", request_delay=0)
    with pytest.raises(ImportError, match="pip install curl_cffi"):
        PoliteHttpClient(config)
