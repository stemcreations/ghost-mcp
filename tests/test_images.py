"""Unit tests for image upload: multipart shape, purpose validation, SSRF guard."""

import httpx
import pytest

from ghost_mcp.admin import images as images_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.errors import GhostError
from ghost_mcp.tools.images import _content_type
from ghost_mcp.vision.structure import fetch_public_bytes

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def _client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_upload_image_posts_multipart_and_returns_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/images/upload/"
        body = request.content
        # The file rides with its filename and content type; purpose is a plain field.
        assert b'name="file"' in body and b'filename="logo.png"' in body
        assert b"image/png" in body
        assert b'name="purpose"' in body and b"profile_image" in body
        return httpx.Response(201, json={"images": [{"url": "https://blog/logo.png"}]})

    url = images_api.upload_image(
        _client(handler),
        b"\x89PNG\r\n",
        filename="logo.png",
        content_type="image/png",
        purpose="profile_image",
    )
    assert url == "https://blog/logo.png"


def test_upload_image_includes_ref_when_given() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert b'name="ref"' in request.content and b"local/logo.png" in request.content
        return httpx.Response(201, json={"images": [{"url": "https://blog/logo.png"}]})

    images_api.upload_image(
        _client(handler), b"x", filename="logo.png", purpose="image", ref="local/logo.png"
    )


def test_upload_image_rejects_unknown_purpose_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no request should be made for an invalid purpose")

    with pytest.raises(GhostError):
        images_api.upload_image(_client(handler), b"x", filename="a.png", purpose="banner")


def test_content_type_from_extension_and_fallback() -> None:
    assert _content_type("photo.png") == "image/png"
    assert _content_type("photo.jpg") == "image/jpeg"
    assert _content_type("noextension") == "application/octet-stream"


def test_fetch_public_bytes_keeps_ssrf_guard() -> None:
    with pytest.raises(GhostError):
        fetch_public_bytes("http://127.0.0.1/logo.png")
