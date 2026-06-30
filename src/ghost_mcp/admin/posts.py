"""Post operations, including the HTML handling Ghost requires.

Posts store their body as Lexical. To work in plain HTML we use Ghost's
``source=html`` conversion when writing and ``formats=html`` when reading. Updates
must include the post's current ``updated_at`` (Ghost uses it to detect conflicting
edits), so :func:`update_post` reads the post first.
"""

from __future__ import annotations

from typing import Any

from ghost_mcp.admin.client import GhostAdminClient, JSONDict
from ghost_mcp.errors import NotFoundError


def browse_posts(
    client: GhostAdminClient,
    *,
    filter: str | None = None,
    limit: int = 15,
    page: int = 1,
    order: str | None = None,
) -> JSONDict:
    """Return a page of posts (the full envelope, including pagination meta)."""
    params: dict[str, Any] = {"limit": limit, "page": page}
    if filter:
        params["filter"] = filter
    if order:
        params["order"] = order
    return client.browse("posts", params=params)


def read_post(client: GhostAdminClient, identifier: str, *, slug: bool = False) -> JSONDict:
    """Return a single post by id (or slug), with its rendered HTML included."""
    post = client.read("posts", identifier, slug=slug, params={"formats": "html"})
    if not post:
        raise NotFoundError(f"post '{identifier}' not found")
    return post


def create_post(client: GhostAdminClient, data: JSONDict, *, html: str | None = None) -> JSONDict:
    """Create a post. When ``html`` is given, Ghost converts it from HTML to Lexical."""
    params = None
    if html is not None:
        data = {**data, "html": html}
        params = {"source": "html"}
    return client.add("posts", data, params=params)


def update_post(
    client: GhostAdminClient,
    post_id: str,
    data: JSONDict,
    *,
    html: str | None = None,
    params: dict[str, Any] | None = None,
) -> JSONDict:
    """Update a post by id.

    Reads the post first to supply the current ``updated_at`` (required by Ghost's
    collision check). Only the fields in ``data`` (plus ``html`` if given) are changed.
    Extra query ``params`` (e.g. ``newsletter``/``email_segment`` to email the post)
    are merged into the request, alongside the ``source=html`` flag when ``html`` is set.
    """
    current = client.read("posts", post_id)
    if not current:
        raise NotFoundError(f"post '{post_id}' not found")
    payload = {**data, "updated_at": current.get("updated_at")}
    query: dict[str, Any] = dict(params or {})
    if html is not None:
        payload["html"] = html
        query["source"] = "html"
    return client.edit("posts", post_id, payload, params=query or None)


def delete_post(client: GhostAdminClient, post_id: str) -> None:
    """Delete a post by id."""
    client.delete("posts", post_id)
