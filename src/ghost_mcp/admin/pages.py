"""Page operations, mirroring posts.

Pages are posts that live outside the feed (about, contact, …). They store their
body as Lexical exactly like posts, so the same ``source=html`` conversion applies
when writing and ``formats=html`` when reading, and updates must include the page's
current ``updated_at`` for Ghost's collision check. Pages have no tags or feed
semantics, but the endpoint shape is otherwise identical to ``/posts/``.
"""

from __future__ import annotations

from typing import Any

from ghost_mcp.admin.client import GhostAdminClient, JSONDict
from ghost_mcp.errors import NotFoundError


def browse_pages(
    client: GhostAdminClient,
    *,
    filter: str | None = None,
    limit: int = 15,
    page: int = 1,
    order: str | None = None,
) -> JSONDict:
    """Return a page of pages (the full envelope, including pagination meta)."""
    params: dict[str, Any] = {"limit": limit, "page": page}
    if filter:
        params["filter"] = filter
    if order:
        params["order"] = order
    return client.browse("pages", params=params)


def read_page(client: GhostAdminClient, identifier: str, *, slug: bool = False) -> JSONDict:
    """Return a single page by id (or slug), with its rendered HTML included."""
    page = client.read("pages", identifier, slug=slug, params={"formats": "html"})
    if not page:
        raise NotFoundError(f"page '{identifier}' not found")
    return page


def create_page(client: GhostAdminClient, data: JSONDict, *, html: str | None = None) -> JSONDict:
    """Create a page. When ``html`` is given, Ghost converts it from HTML to Lexical."""
    params = None
    if html is not None:
        data = {**data, "html": html}
        params = {"source": "html"}
    return client.add("pages", data, params=params)


def update_page(
    client: GhostAdminClient,
    page_id: str,
    data: JSONDict,
    *,
    html: str | None = None,
) -> JSONDict:
    """Update a page by id.

    Reads the page first to supply the current ``updated_at`` (required by Ghost's
    collision check). Only the fields in ``data`` (plus ``html`` if given) are changed.
    """
    current = client.read("pages", page_id)
    if not current:
        raise NotFoundError(f"page '{page_id}' not found")
    payload = {**data, "updated_at": current.get("updated_at")}
    params = None
    if html is not None:
        payload["html"] = html
        params = {"source": "html"}
    return client.edit("pages", page_id, payload, params=params)


def delete_page(client: GhostAdminClient, page_id: str) -> None:
    """Delete a page by id."""
    client.delete("pages", page_id)
