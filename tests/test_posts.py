"""Unit tests for the post helpers, focusing on Ghost's HTML/update nuances."""

import json

import httpx
import pytest

from ghost_mcp.admin import posts as posts_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.errors import NotFoundError
from ghost_mcp.tools.posts import _summary

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def _client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_create_post_sends_source_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/posts/"
        assert request.url.params.get("source") == "html"
        body = json.loads(request.content)
        assert body["posts"][0]["html"] == "<p>hi</p>"
        return httpx.Response(201, json={"posts": [{"id": "1", "status": "draft"}]})

    post = posts_api.create_post(
        _client(handler), {"title": "T", "status": "draft"}, html="<p>hi</p>"
    )
    assert post["id"] == "1"


def test_create_post_without_html_omits_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "source" not in request.url.params
        return httpx.Response(201, json={"posts": [{"id": "1"}]})

    posts_api.create_post(_client(handler), {"title": "T"})


def test_read_post_requests_html_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("formats") == "html"
        return httpx.Response(200, json={"posts": [{"id": "1", "html": "<p>x</p>"}]})

    post = posts_api.read_post(_client(handler), "1")
    assert post["html"] == "<p>x</p>"


def test_update_post_reads_updated_at_then_puts() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200, json={"posts": [{"id": "1", "updated_at": "2026-01-01T00:00:00.000Z"}]}
            )
        body = json.loads(request.content)
        assert body["posts"][0]["updated_at"] == "2026-01-01T00:00:00.000Z"
        assert body["posts"][0]["title"] == "New"
        return httpx.Response(200, json={"posts": [{"id": "1", "title": "New"}]})

    post = posts_api.update_post(_client(handler), "1", {"title": "New"})
    assert post["title"] == "New"
    assert calls == ["GET", "PUT"]


def test_summary_includes_native_preview_url() -> None:
    summary = _summary({"id": "1", "uuid": "abc", "title": "T"}, "https://blog.example.com")
    assert summary["preview_url"] == "https://blog.example.com/p/abc/"


def test_summary_omits_preview_url_without_site() -> None:
    assert "preview_url" not in _summary({"id": "1", "uuid": "abc"})


def test_read_post_raises_when_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": []})

    with pytest.raises(NotFoundError):
        posts_api.read_post(_client(handler), "missing")


def test_update_post_raises_when_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": []})

    with pytest.raises(NotFoundError):
        posts_api.update_post(_client(handler), "missing", {"title": "x"})
