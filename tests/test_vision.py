"""Unit tests for the vision fetcher's SSRF guards (no network)."""

import pytest

from ghost_mcp.errors import GhostError
from ghost_mcp.vision.structure import _validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/resource",
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(GhostError):
        _validate_public_url(url)


def test_allows_public_ip_literals() -> None:
    # Public IP literals resolve without DNS and must pass.
    _validate_public_url("http://8.8.8.8/")
    _validate_public_url("https://1.1.1.1/")
