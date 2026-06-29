"""Unit tests for the generic Admin API client, using a mocked transport.

These verify the envelope handling and error parsing without any network access.
"""

import json

import httpx
import pytest

from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.errors import GhostAPIError

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def make_client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_browse_returns_the_full_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/posts/"
        return httpx.Response(200, json={"posts": [{"id": "1"}], "meta": {"pagination": {}}})

    result = make_client(handler).browse("posts")
    assert result["posts"][0]["id"] == "1"
    assert "meta" in result


def test_read_unwraps_a_single_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": [{"id": "1", "title": "Hi"}]})

    post = make_client(handler).read("posts", "1")
    assert post["title"] == "Hi"


def test_add_wraps_the_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"posts": [{"title": "New"}]}
        return httpx.Response(201, json={"posts": [{"id": "1", "title": "New"}]})

    created = make_client(handler).add("posts", {"title": "New"})
    assert created["id"] == "1"


def test_api_errors_become_ghost_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"errors": [{"message": "Validation error"}]})

    with pytest.raises(GhostAPIError) as exc_info:
        make_client(handler).browse("posts")
    assert "Validation error" in str(exc_info.value)
    assert exc_info.value.status_code == 422
