"""Tools for managing tags: list, read, create, update, delete.

Tags have no special content handling, so these wrap the generic Admin API client
directly.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import load_settings


def _summary(tag: dict) -> dict:
    return {
        "id": tag.get("id"),
        "name": tag.get("name"),
        "slug": tag.get("slug"),
        "description": tag.get("description"),
        "count": (tag.get("count") or {}).get("posts"),
    }


def _fields(
    name: str | None,
    description: str | None,
    slug: str | None,
    meta_title: str | None,
    meta_description: str | None,
    feature_image: str | None,
) -> dict:
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if slug is not None:
        fields["slug"] = slug
    if meta_title is not None:
        fields["meta_title"] = meta_title
    if meta_description is not None:
        fields["meta_description"] = meta_description
    if feature_image is not None:
        fields["feature_image"] = feature_image
    return fields


def register(mcp: FastMCP) -> None:
    """Register the tag tools on the given server."""

    @mcp.tool
    def list_tags(
        limit: int = 50,
        page: int = 1,
        filter: str | None = None,
        order: str = "name asc",
    ) -> dict:
        """List tags, with how many posts use each.

        Args:
            limit: Tags per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost filter, e.g. ``visibility:public``.
            order: Sort order, e.g. ``name asc`` or ``count.posts desc``.

        Returns:
            A list of tag summaries and the pagination block.
        """
        params: dict = {"limit": limit, "page": page, "order": order, "include": "count.posts"}
        if filter:
            params["filter"] = filter
        with GhostAdminClient(load_settings()) as client:
            result = client.browse("tags", params=params)
        return {
            "tags": [_summary(t) for t in result.get("tags", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_tag(tag_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single tag by id or slug. Provide either ``tag_id`` or ``slug``."""
        if not tag_id and not slug:
            return {"error": "Provide either tag_id or slug."}
        with GhostAdminClient(load_settings()) as client:
            tag = client.read(
                "tags", slug or tag_id, slug=bool(slug), params={"include": "count.posts"}
            )
        return _summary(tag)

    @mcp.tool
    def create_tag(
        name: str,
        description: str | None = None,
        slug: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        feature_image: str | None = None,
    ) -> dict:
        """Create a tag.

        Only ``name`` is required; ``slug`` is derived from it if omitted. Returns the
        created tag's summary.
        """
        fields = _fields(name, description, slug, meta_title, meta_description, feature_image)
        with GhostAdminClient(load_settings()) as client:
            created = client.add("tags", fields)
        return _summary(created)

    @mcp.tool
    def update_tag(
        tag_id: str,
        name: str | None = None,
        description: str | None = None,
        slug: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        feature_image: str | None = None,
    ) -> dict:
        """Update a tag by id; only the fields you pass are changed."""
        fields = _fields(name, description, slug, meta_title, meta_description, feature_image)
        with GhostAdminClient(load_settings()) as client:
            updated = client.edit("tags", tag_id, fields)
        return _summary(updated)

    @mcp.tool
    def delete_tag(tag_id: str) -> dict:
        """Delete a tag by id. Posts keep existing; they just lose the tag."""
        with GhostAdminClient(load_settings()) as client:
            client.delete("tags", tag_id)
        return {"deleted": tag_id}
