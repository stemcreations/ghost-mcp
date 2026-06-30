"""Tools for managing pages: list, read, create, update, delete.

Pages are standalone content outside the post feed (about, contact, …). They share
posts' fields and HTML handling but have no tags or feed semantics. Like posts they
carry a ``preview_url`` (Ghost's native draft preview, ``{site}/p/{uuid}/``) for
reviewing in the active theme before publishing.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.admin import pages as pages_api
from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client, config


def _summary(page: dict, site_url: str | None = None) -> dict:
    data = {
        "id": page.get("id"),
        "title": page.get("title"),
        "slug": page.get("slug"),
        "status": page.get("status"),
        "url": page.get("url"),
        "updated_at": page.get("updated_at"),
    }
    uuid = page.get("uuid")
    if site_url and uuid:
        data["preview_url"] = f"{site_url}/p/{uuid}/"
    return data


def _detail(page: dict, site_url: str | None = None) -> dict:
    return {
        **_summary(page, site_url),
        "html": page.get("html"),
        "excerpt": page.get("custom_excerpt") or page.get("excerpt"),
        "meta_title": page.get("meta_title"),
        "meta_description": page.get("meta_description"),
    }


def _build_fields(
    title: str | None,
    status: str | None,
    excerpt: str | None,
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
    if feature_image is not None:
        fields["feature_image"] = feature_image
    if meta_title is not None:
        fields["meta_title"] = meta_title
    if meta_description is not None:
        fields["meta_description"] = meta_description
    return fields


def register(mcp: FastMCP) -> None:
    """Register the page tools on the given server."""

    @mcp.tool
    def list_pages(
        limit: int = 15,
        page: int = 1,
        filter: str | None = None,
        order: str = "updated_at desc",
    ) -> dict:
        """List pages (standalone content outside the post feed).

        Args:
            limit: Pages per page of results (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost filter, e.g. ``status:published``.
            order: Sort order, e.g. ``published_at desc``.

        Returns:
            A list of page summaries (each with a ``preview_url``) and the pagination
            block.
        """
        result = pages_api.browse_pages(
            admin_client(), filter=filter, limit=limit, page=page, order=order
        )
        return {
            "pages": [_summary(p, config().site_url) for p in result.get("pages", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_page(page_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single page by id or slug, including its rendered HTML.

        Provide either ``page_id`` or ``slug``. The result includes a ``preview_url``
        for viewing the page in the active theme.
        """
        if not page_id and not slug:
            raise GhostError("Provide either page_id or slug.")
        page = pages_api.read_page(admin_client(), slug or page_id, slug=bool(slug))
        return _detail(page, config().site_url)

    @mcp.tool
    def create_page(
        title: str,
        html: str = "",
        status: str = "draft",
        excerpt: str | None = None,
        feature_image: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
    ) -> dict:
        """Create a page from HTML content.

        Defaults to a **draft**; pass ``status="published"`` to publish immediately.
        Pages are standalone (about, contact, …) with no tags or feed placement.
        ``meta_title``/``meta_description`` set the page's search-snippet metadata.

        Returns the created page's summary, including a ``preview_url`` for reviewing
        the draft in the active theme before publishing.
        """
        fields = _build_fields(title, status, excerpt, feature_image, meta_title, meta_description)
        created = pages_api.create_page(admin_client(), fields, html=html or None)
        return _summary(created, config().site_url)

    @mcp.tool
    def update_page(
        page_id: str,
        title: str | None = None,
        html: str | None = None,
        status: str | None = None,
        excerpt: str | None = None,
        feature_image: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
    ) -> dict:
        """Update an existing page by id; only the fields you pass are changed.

        Pass ``status="published"`` to publish a draft, or ``status="draft"`` to
        unpublish. An empty ``html`` is treated as "leave the body unchanged", so it
        never blanks a page. Returns the updated page summary.
        """
        fields = _build_fields(title, status, excerpt, feature_image, meta_title, meta_description)
        updated = pages_api.update_page(admin_client(), page_id, fields, html=html or None)
        return _summary(updated, config().site_url)

    @mcp.tool
    def delete_page(page_id: str) -> dict:
        """Delete a page by id. This cannot be undone."""
        pages_api.delete_page(admin_client(), page_id)
        return {"deleted": page_id}
