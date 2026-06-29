"""Read and update Ghost site settings (brand, SEO metadata, navigation, …).

The ``/settings/`` endpoint returns and accepts a list of ``{key, value}`` objects
rather than the resource envelope the rest of the API uses, so it gets its own
helpers. Reads are exposed as a flat ``{key: value}`` mapping; updates are partial —
only the keys you pass are changed. Requires a staff token with the Owner or Admin
role.
"""

from __future__ import annotations

from typing import Any

from ghost_mcp.admin.client import GhostAdminClient


def _flatten(body: dict[str, Any]) -> dict[str, Any]:
    """Turn the ``{settings: [{key, value}]}`` envelope into a ``{key: value}`` map.

    Rows without a ``key`` (or that aren't objects) are skipped, so a single
    malformed entry can't abort the whole read or update.
    """
    return {
        item["key"]: item.get("value")
        for item in body.get("settings", [])
        if isinstance(item, dict) and "key" in item
    }


def get_settings(client: GhostAdminClient) -> dict[str, Any]:
    """Return all site settings as a flat ``{key: value}`` mapping."""
    return _flatten(client.get("/settings/"))


def update_settings(client: GhostAdminClient, values: dict[str, Any]) -> dict[str, Any]:
    """Update the given settings by key and return the full updated mapping.

    Only the keys in ``values`` are changed; other settings are left untouched.
    """
    payload = {"settings": [{"key": key, "value": value} for key, value in values.items()]}
    return _flatten(client.put("/settings/", json=payload))
