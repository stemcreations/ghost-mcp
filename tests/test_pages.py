"""Unit tests for the page helpers (pages mirror posts; no tags)."""

import json

import httpx
import pytest

from ghost_mcp.admin import pages as pages_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.errors import NotFoundError
from ghost_mcp.tools.pages import _build_fields, _summary

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def _client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_create_page_sends_source_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/pages/"
        assert request.url.params.get("source") == "html"
        body = json.loads(request.content)
        assert body["pages"][0]["html"] == "<p>hi</p>"
        return httpx.Response(201, json={"pages": [{"id": "1", "status": "draft"}]})

    page = pages_api.create_page(
        _client(handler), {"title": "T", "status": "draft"}, html="<p>hi</p>"
    )
    assert page["id"] == "1"


def test_read_page_requests_html_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/pages/1/"
        assert request.url.params.get("formats") == "html"
        return httpx.Response(200, json={"pages": [{"id": "1", "html": "<p>x</p>"}]})

    page = pages_api.read_page(_client(handler), "1")
    assert page["html"] == "<p>x</p>"


def test_update_page_reads_updated_at_then_puts() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200, json={"pages": [{"id": "1", "updated_at": "2026-01-01T00:00:00.000Z"}]}
            )
        body = json.loads(request.content)
        assert body["pages"][0]["updated_at"] == "2026-01-01T00:00:00.000Z"
        assert body["pages"][0]["title"] == "New"
        return httpx.Response(200, json={"pages": [{"id": "1", "title": "New"}]})

    page = pages_api.update_page(_client(handler), "1", {"title": "New"})
    assert page["title"] == "New"
    assert calls == ["GET", "PUT"]


def test_read_page_raises_when_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"pages": []})

    with pytest.raises(NotFoundError):
        pages_api.read_page(_client(handler), "missing")


def test_build_fields_keeps_only_provided() -> None:
    assert _build_fields("About", None, None, None, None, None) == {"title": "About"}


def test_build_fields_maps_excerpt_to_custom_excerpt() -> None:
    fields = _build_fields("About", "published", "blurb", "img.png", "MT", "MD")
    assert fields == {
        "title": "About",
        "status": "published",
        "custom_excerpt": "blurb",
        "feature_image": "img.png",
        "meta_title": "MT",
        "meta_description": "MD",
    }


def test_summary_includes_native_preview_url() -> None:
    summary = _summary({"id": "1", "uuid": "abc", "title": "About"}, "https://blog.example.com")
    assert summary["preview_url"] == "https://blog.example.com/p/abc/"


def test_summary_omits_preview_url_without_site() -> None:
    assert "preview_url" not in _summary({"id": "1", "uuid": "abc"})
