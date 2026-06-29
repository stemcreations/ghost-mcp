"""Smoke test: mint a JWT from the staff token and hit the Ghost Admin API.

Run with:  uv run python test_connection.py

Validates the full auth chain (token -> JWT -> authenticated request) before any
MCP tools are built on top of it. See CLAUDE.md for the auth details.
"""

import os
import sys
import time

import httpx
import jwt
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("GHOST_STAFF_ACCESS_TOKEN")
admin_url = os.environ.get("GHOST_ADMIN_URL")

if not token or ":" not in token:
    sys.exit("GHOST_STAFF_ACCESS_TOKEN missing or not in 'id:secret' form (check .env)")
if not admin_url:
    sys.exit("GHOST_ADMIN_URL missing (add your Ghost site URL to .env)")


def mint_jwt(staff_token: str) -> str:
    """Build a short-lived (5 min) JWT signed from the staff token."""
    key_id, secret = staff_token.split(":", 1)
    now = int(time.time())
    return jwt.encode(
        {"iat": now, "exp": now + 300, "aud": "/admin/"},
        bytes.fromhex(secret),          # secret is hex -> decode to raw bytes
        algorithm="HS256",
        headers={"kid": key_id},
    )


# Normalize: accept either the site root or a URL that already includes the API path.
base = admin_url.rstrip("/")
if "/ghost/api/admin" not in base:
    base += "/ghost/api/admin"

headers = {
    "Authorization": f"Ghost {mint_jwt(token)}",
    "Accept-Version": "v5.0",
}

for path in ("/site/", "/users/me/", "/posts/?limit=3"):
    url = f"{base}{path}"
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
    except httpx.HTTPError as exc:
        print(f"[ERR ] {path} -> request failed: {exc}")
        continue

    print(f"[{resp.status_code}] {path}")
    if resp.status_code == 200:
        print("       " + resp.text[:300])
    else:
        print("       " + resp.text[:500])
    print()
