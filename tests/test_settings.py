"""Unit tests for the settings admin helpers, using a mocked transport."""

import json

import httpx

from ghost_mcp.admin import settings as settings_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.tools.settings import _PUBLIC_KEYS

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def _client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_get_settings_flattens_to_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/settings/"
        return httpx.Response(
            200,
            json={
                "settings": [
                    {"key": "title", "value": "My Blog"},
                    {"key": "accent_color", "value": "#4a7c59"},
                ],
                "meta": {},
            },
        )

    result = settings_api.get_settings(_client(handler))
    assert result == {"title": "My Blog", "accent_color": "#4a7c59"}


def test_update_settings_sends_key_value_array() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/ghost/api/admin/settings/"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"settings": [{"key": "title", "value": "New"}]})

    result = settings_api.update_settings(_client(handler), {"title": "New"})
    assert captured["body"] == {"settings": [{"key": "title", "value": "New"}]}
    assert result["title"] == "New"


def test_public_settings_never_expose_secrets() -> None:
    # get_site_settings projects only these keys; none may be a credential.
    secrets = {
        "password",
        "stripe_secret_key",
        "stripe_connect_secret_key",
        "mailgun_api_key",
        "members_secret",
        "public_hash",
    }
    assert not (set(_PUBLIC_KEYS) & secrets)


def test_flatten_skips_malformed_rows() -> None:
    body = {"settings": [{"key": "title", "value": "X"}, {"value": "no key"}, "garbage"]}
    assert settings_api._flatten(body) == {"title": "X"}


def test_flatten_drops_secret_keys() -> None:
    body = {
        "settings": [
            {"key": "title", "value": "X"},
            {"key": "stripe_secret_key", "value": "sk_live_x"},
            {"key": "mailgun_api_key", "value": "abc"},
            {"key": "password", "value": "p"},
            {"key": "public_hash", "value": "h"},
        ]
    }
    assert settings_api._flatten(body) == {"title": "X"}
