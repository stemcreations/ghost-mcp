"""Tools for reading users (authors): list and read only.

Users are the staff/authors who write posts. The Admin API exposes them **read-only**
to integrations, so there is no create/update/delete here — only browse and read, to
attribute posts and inspect authors. ``include=count.posts,roles`` enriches each user
with their role names and how many posts they've written.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client

#: Enrich users with their roles and post counts (omitted from the base response).
_WITH_INFO = {"include": "count.posts,roles"}


def _summary(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "slug": user.get("slug"),
        "email": user.get("email"),
        "roles": [role.get("name") for role in (user.get("roles") or [])],
        "count": (user.get("count") or {}).get("posts"),
    }


def register(mcp: FastMCP) -> None:
    """Register the read-only user tools on the given server."""

    @mcp.tool
    def list_users(limit: int = 50, page: int = 1, order: str = "name asc") -> dict:
        """List users (authors/staff). Read-only: the Admin API forbids integrations
        from writing users.

        Args:
            limit: Users per page (Ghost allows up to 100).
            page: Which page of results to return.
            order: Sort order, e.g. ``name asc``.

        Returns:
            A list of user summaries (name, slug, email, roles, post count) and the
            pagination block.
        """
        params: dict = {"limit": limit, "page": page, "order": order, **_WITH_INFO}
        result = admin_client().browse("users", params=params)
        return {
            "users": [_summary(u) for u in result.get("users", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_user(user_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single user by id or slug. Provide either ``user_id`` or ``slug``."""
        if not user_id and not slug:
            raise GhostError("Provide either user_id or slug.")
        user = admin_client().read("users", slug or user_id, slug=bool(slug), params=_WITH_INFO)
        return _summary(user)
