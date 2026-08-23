"""Tests for libs.utils.http_fetch's SSRF guardrails."""

import httpx
import pytest

from libs.utils.http_fetch import (
    FetchFailedError,
    InvalidUrlError,
    ResponseTooLargeError,
    fetch_url,
    validate_url,
)


def test_validate_url_rejects_disallowed_scheme():
    with pytest.raises(InvalidUrlError):
        validate_url("http://example.com/file.xml", allowed_schemes=["https"])


def test_validate_url_rejects_missing_hostname():
    with pytest.raises(InvalidUrlError):
        validate_url("https:///file.xml", allowed_schemes=["https"])


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "127.0.0.1",
        "169.254.169.254",  # cloud metadata endpoint
        "10.0.0.5",
        "192.168.1.1",
    ],
)
def test_validate_url_rejects_non_public_addresses(hostname: str):
    with pytest.raises(InvalidUrlError):
        validate_url(f"https://{hostname}/file.xml", allowed_schemes=["https"])


def test_validate_url_accepts_public_https_url():
    # A well-known public DNS name; resolving it must not raise.
    validate_url("https://example.com/file.xml", allowed_schemes=["https"])


async def test_fetch_url_raises_on_oversized_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("libs.utils.http_fetch._assert_public_host", lambda hostname: None)

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "application/xml"}

        async def aiter_bytes(self):
            yield b"x" * 1000

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url):
            return _FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    with pytest.raises(ResponseTooLargeError):
        await fetch_url(
            "https://example.com/file.xml",
            allowed_schemes=["https"],
            max_bytes=10,
            timeout_seconds=5.0,
        )


async def test_fetch_url_raises_on_error_status(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("libs.utils.http_fetch._assert_public_host", lambda hostname: None)

    class _FakeResponse:
        status_code = 404
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url):
            return _FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    with pytest.raises(FetchFailedError):
        await fetch_url(
            "https://example.com/file.xml",
            allowed_schemes=["https"],
            max_bytes=1000,
            timeout_seconds=5.0,
        )
