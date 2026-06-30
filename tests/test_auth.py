"""Unit tests for Admin API token signing (no network required)."""

import jwt
import pytest

from ghost_mcp.admin.auth import MAX_TOKEN_TTL, mint_admin_token
from ghost_mcp.errors import ConfigError

# A throwaway token: an arbitrary id and a valid hex secret.
SAMPLE_TOKEN = "1234567890abcdef:" + "ab" * 32


def _decode(token: str) -> tuple[dict, dict]:
    secret = bytes.fromhex(SAMPLE_TOKEN.split(":", 1)[1])
    payload = jwt.decode(token, secret, algorithms=["HS256"], audience="/admin/")
    return jwt.get_unverified_header(token), payload


def test_header_identifies_the_key() -> None:
    header, _ = _decode(mint_admin_token(SAMPLE_TOKEN))
    assert header["kid"] == "1234567890abcdef"
    assert header["alg"] == "HS256"


def test_audience_is_admin() -> None:
    _, payload = _decode(mint_admin_token(SAMPLE_TOKEN))
    assert payload["aud"] == "/admin/"


def test_lifetime_is_capped_at_five_minutes() -> None:
    _, payload = _decode(mint_admin_token(SAMPLE_TOKEN, ttl_seconds=9999))
    assert payload["exp"] - payload["iat"] == MAX_TOKEN_TTL


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(ConfigError):
        mint_admin_token("not-a-valid-token")


def test_non_hex_secret_raises_config_error() -> None:
    # A token with the right id:secret shape but a non-hex secret should surface a
    # clean ConfigError, not a bare ValueError from bytes.fromhex.
    with pytest.raises(ConfigError):
        mint_admin_token("abc123:not-hex-secret!!")
