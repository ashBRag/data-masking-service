"""SSRF-guarded HTTPS fetch for downloading a document from a caller-supplied URL.

Generic and reusable: takes every limit as a parameter, no settings/app
dependency. Callers that fetch a URL supplied by a request body (as opposed
to one they constructed themselves) should always go through this rather
than calling httpx directly - see claude.md's "Validate user-controlled
URLs before making outbound requests. Protect URL fetching against SSRF."

Defends against SSRF by, before ever opening a connection:
  - only allowing schemes the caller explicitly opts into (typically just "https")
  - resolving the hostname and rejecting any resolved IP that is private,
    loopback, link-local, or otherwise not globally routable (blocks
    "https://internal-host", "https://169.254.169.254" cloud metadata
    endpoints, DNS rebinding to 127.0.0.1, etc.)

Streams the response body and aborts as soon as it exceeds `max_bytes`,
so a malicious/huge response can't exhaust memory before the size check
would otherwise fire.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class UrlFetchError(Exception):
    """Base class for errors raised while validating/fetching a caller-supplied URL."""


class InvalidUrlError(UrlFetchError):
    """The URL is malformed, uses a disallowed scheme, or resolves to a blocked address."""


class ResponseTooLargeError(UrlFetchError):
    """The response body exceeded the configured size limit."""


class FetchFailedError(UrlFetchError):
    """The request itself failed (network error, non-2xx status, timeout)."""


@dataclass(frozen=True)
class FetchedDocument:
    """The result of a successful fetch_url() call."""

    content: bytes
    content_type: str | None


def _assert_public_host(hostname: str) -> None:
    """Resolve `hostname` and raise InvalidUrlError if any resolved address is non-public.

    Checked against every address a hostname resolves to (not just the
    first) since a name can resolve to multiple IPs and only one needs to be
    internal for SSRF to succeed.
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise InvalidUrlError(f"Could not resolve host: {hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise InvalidUrlError(f"Host {hostname} resolves to a non-public address")


def validate_url(url: str, allowed_schemes: list[str]) -> None:
    """Validate `url`'s scheme and resolved address before it is ever fetched.

    Args:
        url: The caller-supplied URL to validate.
        allowed_schemes: Schemes permitted (e.g. `["https"]`); anything else is rejected.

    Raises:
        InvalidUrlError: If the URL is malformed, uses a disallowed scheme,
            has no hostname, or resolves to a private/loopback/link-local/
            reserved address.
    """
    parsed = urlparse(url)

    if parsed.scheme not in allowed_schemes:
        raise InvalidUrlError(f"URL scheme must be one of {allowed_schemes}, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise InvalidUrlError("URL has no hostname")

    _assert_public_host(parsed.hostname)


async def fetch_url(
    url: str,
    *,
    allowed_schemes: list[str],
    max_bytes: int,
    timeout_seconds: float,
) -> FetchedDocument:
    """Validate and fetch `url`, enforcing SSRF guardrails and a response-size cap.

    Args:
        url: The caller-supplied URL to fetch.
        allowed_schemes: Schemes permitted for `url` (e.g. `["https"]`).
        max_bytes: Maximum response body size; the download is aborted as
            soon as this is exceeded, without buffering the full response.
        timeout_seconds: Total request timeout.

    Raises:
        InvalidUrlError: `url` fails validation (see `validate_url`).
        ResponseTooLargeError: The response body exceeds `max_bytes`.
        FetchFailedError: The request fails (network error, timeout, non-2xx status).

    Returns:
        FetchedDocument: The downloaded bytes and the response's Content-Type, if any.
    """
    validate_url(url, allowed_schemes)

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise FetchFailedError(f"Fetching {url} failed with status {response.status_code}")

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ResponseTooLargeError(f"Response exceeded {max_bytes} bytes")
                    chunks.append(chunk)

                return FetchedDocument(content=b"".join(chunks), content_type=response.headers.get("content-type"))
    except httpx.HTTPError as exc:
        raise FetchFailedError(f"Fetching {url} failed: {exc}") from exc
