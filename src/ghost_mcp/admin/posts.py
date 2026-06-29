"""Post operations, including the HTML handling Ghost requires.

Posts store their body as Lexical. To work in plain HTML we use Ghost's
``source=html`` conversion when writing and ``formats=html`` when reading. Updates
must include the post's current ``updated_at`` — Ghost uses it to detect conflicting
edits — so :func:`update_post` reads the post first.
"""

from __future__ import annotations

from typing import Any

from ghost_mcp.admin.client import GhostAdminClient, JSONDict


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
    return client.read("posts", identifier, slug=slug, params={"formats": "html"})


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
) -> JSONDict:
    """Update a post by id.

    Reads the post first to supply the current ``updated_at`` (required by Ghost's
    collision check). Only the fields in ``data`` (plus ``html`` if given) are changed.
    """
    current = client.read("posts", post_id)
    payload = {**data, "updated_at": current.get("updated_at")}
    params = None
    if html is not None:
        payload["html"] = html
        params = {"source": "html"}
    return client.edit("posts", post_id, payload, params=params)


def delete_post(client: GhostAdminClient, post_id: str) -> None:
    """Delete a post by id."""
    client.delete("posts", post_id)
