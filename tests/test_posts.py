"""Unit tests for the post helpers, focusing on Ghost's HTML/update nuances."""

import json

import httpx
import pytest

from ghost_mcp.admin import posts as posts_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.errors import NotFoundError
from ghost_mcp.tools.posts import _build_fields, _detail, _summary

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


def test_update_post_threads_newsletter_params_into_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"posts": [{"id": "1", "updated_at": "T"}]})
        # Publishing as email: newsletter + segment ride as query params, not body fields.
        assert request.url.params.get("newsletter") == "weekly"
        assert request.url.params.get("email_segment") == "status:-free"
        assert "source" not in request.url.params  # no html change, so no source flag
        return httpx.Response(200, json={"posts": [{"id": "1", "status": "published"}]})

    post = posts_api.update_post(
        _client(handler),
        "1",
        {"status": "published"},
        params={"newsletter": "weekly", "email_segment": "status:-free"},
    )
    assert post["status"] == "published"


def test_update_post_merges_source_flag_with_extra_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"posts": [{"id": "1", "updated_at": "T"}]})
        assert request.url.params.get("source") == "html"
        assert request.url.params.get("newsletter") == "weekly"
        return httpx.Response(200, json={"posts": [{"id": "1"}]})

    posts_api.update_post(
        _client(handler), "1", {}, html="<p>x</p>", params={"newsletter": "weekly"}
    )


def _fields(**overrides) -> dict:
    base = dict(
        title=None,
        status=None,
        excerpt=None,
        tags=None,
        feature_image=None,
        meta_title=None,
        meta_description=None,
        codeinjection_head=None,
        codeinjection_foot=None,
    )
    base.update(overrides)
    return _build_fields(**base)


def test_build_fields_includes_code_injection() -> None:
    fields = _fields(
        codeinjection_head='<script type="application/ld+json">{}</script>',
        codeinjection_foot="<!-- foot -->",
    )
    assert fields["codeinjection_head"] == '<script type="application/ld+json">{}</script>'
    assert fields["codeinjection_foot"] == "<!-- foot -->"


def test_build_fields_omits_untouched_code_injection() -> None:
    # None means "leave unchanged", so the field must not appear in the payload...
    assert "codeinjection_head" not in _fields()
    # ...but an empty string is a real value (clears an existing injection).
    assert _fields(codeinjection_foot="")["codeinjection_foot"] == ""


def test_detail_surfaces_code_injection() -> None:
    detail = _detail({"id": "1", "codeinjection_head": "<script></script>"})
    assert detail["codeinjection_head"] == "<script></script>"
    assert detail["codeinjection_foot"] is None


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
