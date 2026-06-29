"""Tools for managing blog posts: list, read, create, update, delete, and preview.

Posts carry a ``preview_url`` — Ghost's native draft preview (``{site}/p/{uuid}/``),
which renders the post in the active theme exactly as it will look when published.
It works for drafts and is shareable, so it's the way to review a post before it
goes live.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.admin import posts as posts_api
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import load_settings


def _summary(post: dict, site_url: str | None = None) -> dict:
    data = {
        "id": post.get("id"),
        "title": post.get("title"),
        "slug": post.get("slug"),
        "status": post.get("status"),
        "url": post.get("url"),
        "updated_at": post.get("updated_at"),
    }
    uuid = post.get("uuid")
    if site_url and uuid:
        data["preview_url"] = f"{site_url}/p/{uuid}/"
    return data


def _detail(post: dict, site_url: str | None = None) -> dict:
    return {
        **_summary(post, site_url),
        "html": post.get("html"),
        "excerpt": post.get("custom_excerpt") or post.get("excerpt"),
        "meta_title": post.get("meta_title"),
        "meta_description": post.get("meta_description"),
        "tags": [tag.get("name") for tag in (post.get("tags") or [])],
    }


def _build_fields(
    title: str | None,
    status: str | None,
    excerpt: str | None,
    tags: list[str] | None,
    feature_image: str | None,
    meta_title: str | None,
    meta_description: str | None,
) -> dict:
    fields: dict = {}
    if title is not None:
        fields["title"] = title
    if status is not None:
        fields["status"] = status
    if excerpt is not None:
        fields["custom_excerpt"] = excerpt
    if tags is not None:
        fields["tags"] = [{"name": name} for name in tags]
    if feature_image is not None:
        fields["feature_image"] = feature_image
    if meta_title is not None:
        fields["meta_title"] = meta_title
    if meta_description is not None:
        fields["meta_description"] = meta_description
    return fields


def register(mcp: FastMCP) -> None:
    """Register the post tools on the given server."""

    @mcp.tool
    def list_posts(
        limit: int = 15,
        page: int = 1,
        filter: str | None = None,
        order: str = "updated_at desc",
    ) -> dict:
        """List blog posts.

        Args:
            limit: Posts per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost filter, e.g. ``status:published`` or ``tag:news``.
            order: Sort order, e.g. ``published_at desc``.

        Returns:
            A list of post summaries (each with a ``preview_url``) and the pagination
            block.
        """
        settings = load_settings()
        with GhostAdminClient(settings) as client:
            result = posts_api.browse_posts(
                client, filter=filter, limit=limit, page=page, order=order
            )
        return {
            "posts": [_summary(p, settings.site_url) for p in result.get("posts", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_post(post_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single post by id or slug, including its rendered HTML.

        Provide either ``post_id`` or ``slug``. The result includes a ``preview_url``
        for viewing the post in the active theme.
        """
        if not post_id and not slug:
            return {"error": "Provide either post_id or slug."}
        settings = load_settings()
        with GhostAdminClient(settings) as client:
            post = posts_api.read_post(client, slug or post_id, slug=bool(slug))
        return _detail(post, settings.site_url)

    @mcp.tool
    def create_post(
        title: str,
        html: str = "",
        status: str = "draft",
        excerpt: str | None = None,
        tags: list[str] | None = None,
        feature_image: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
    ) -> dict:
        """Create a blog post from HTML content.

        Defaults to a **draft** — pass ``status="published"`` to publish immediately.
        ``tags`` are given as names and created if they don't already exist.
        ``meta_title``/``meta_description`` set the post's search-snippet metadata.

        Returns the created post's summary, including a ``preview_url`` for reviewing
        the draft in the active theme before publishing.
        """
        fields = _build_fields(
            title, status, excerpt, tags, feature_image, meta_title, meta_description
        )
        settings = load_settings()
        with GhostAdminClient(settings) as client:
            created = posts_api.create_post(client, fields, html=html or None)
        return _summary(created, settings.site_url)

    @mcp.tool
    def update_post(
        post_id: str,
        title: str | None = None,
        html: str | None = None,
        status: str | None = None,
        excerpt: str | None = None,
        tags: list[str] | None = None,
        feature_image: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
    ) -> dict:
        """Update an existing post by id; only the fields you pass are changed.

        Pass ``status="published"`` to publish a draft, or ``status="draft"`` to
        unpublish. Returns the updated post summary, including its ``preview_url``.
        """
        fields = _build_fields(
            title, status, excerpt, tags, feature_image, meta_title, meta_description
        )
        settings = load_settings()
        with GhostAdminClient(settings) as client:
            updated = posts_api.update_post(client, post_id, fields, html=html)
        return _summary(updated, settings.site_url)

    @mcp.tool
    def delete_post(post_id: str) -> dict:
        """Delete a post by id. This cannot be undone."""
        with GhostAdminClient(load_settings()) as client:
            posts_api.delete_post(client, post_id)
        return {"deleted": post_id}
