"""Signing tokens for the Ghost Admin API.

The Admin API does not accept the staff access token directly. Each request must
carry a short-lived JSON Web Token signed from that token; this module performs
that signing.
"""

from __future__ import annotations

import time

import jwt

from ghost_mcp.errors import ConfigError

#: Maximum token lifetime Ghost will accept, in seconds.
MAX_TOKEN_TTL = 300


def mint_admin_token(staff_token: str, *, ttl_seconds: int = MAX_TOKEN_TTL) -> str:
    """Sign a short-lived Admin API token from a staff access token.

    Args:
        staff_token: A staff access token in ``id:secret`` form. The secret half
            is a hex string and is decoded to raw bytes before signing.
        ttl_seconds: How long the token stays valid, capped at five minutes.

    Returns:
        A signed JWT for use in the ``Authorization: Ghost <token>`` header.

    Raises:
        ConfigError: if the staff token is not in ``id:secret`` form.
    """
    if ":" not in staff_token:
        raise ConfigError("staff token must be in 'id:secret' form")
    key_id, secret = staff_token.split(":", 1)
    try:
        secret_bytes = bytes.fromhex(secret)
    except ValueError as exc:
        raise ConfigError(
            "staff token secret is not valid hex; copy the token exactly from the "
            "user's profile page in Ghost Admin"
        ) from exc
    issued_at = int(time.time())
    return jwt.encode(
        {
            "iat": issued_at,
            "exp": issued_at + min(ttl_seconds, MAX_TOKEN_TTL),
            "aud": "/admin/",
        },
        secret_bytes,
        algorithm="HS256",
        headers={"kid": key_id},
    )
