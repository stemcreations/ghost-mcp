"""Tools for managing labels: list, read, create, update, delete.

Labels segment members (they pair with the members tools). A label is a simple
``{id, name, slug}`` resource that fits the generic envelope, so these wrap the
Admin API client directly. Unlike tiers and offers, labels support delete.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client


def _summary(label: dict) -> dict:
    return {
        "id": label.get("id"),
        "name": label.get("name"),
        "slug": label.get("slug"),
    }


def _fields(name: str | None, slug: str | None) -> dict:
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if slug is not None:
        fields["slug"] = slug
    return fields


def register(mcp: FastMCP) -> None:
    """Register the label tools on the given server."""

    @mcp.tool
    def list_labels(limit: int = 50, page: int = 1, order: str = "name asc") -> dict:
        """List member labels.

        Args:
            limit: Labels per page (Ghost allows up to 100).
            page: Which page of results to return.
            order: Sort order, e.g. ``name asc``.

        Returns:
            A list of label summaries and the pagination block.
        """
        result = admin_client().browse(
            "labels", params={"limit": limit, "page": page, "order": order}
        )
        return {
            "labels": [_summary(label) for label in result.get("labels", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_label(label_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single label by id or slug. Provide either ``label_id`` or ``slug``."""
        if not label_id and not slug:
            raise GhostError("Provide either label_id or slug.")
        label = admin_client().read("labels", slug or label_id, slug=bool(slug))
        return _summary(label)

    @mcp.tool
    def create_label(name: str, slug: str | None = None) -> dict:
        """Create a member label. Only ``name`` is required; ``slug`` is derived if omitted."""
        return _summary(admin_client().add("labels", _fields(name, slug)))

    @mcp.tool
    def update_label(label_id: str, name: str | None = None, slug: str | None = None) -> dict:
        """Update a label by id; only the fields you pass are changed."""
        return _summary(admin_client().edit("labels", label_id, _fields(name, slug)))

    @mcp.tool
    def delete_label(label_id: str) -> dict:
        """Delete a label by id. Members keep existing; they just lose the label."""
        admin_client().delete("labels", label_id)
        return {"deleted": label_id}
