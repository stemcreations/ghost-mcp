"""Tools for managing members: list, read, create, update.

Members are the blog's audience (free, paid, comped, or gift). The Admin API supports
browse/read/create/update but **not delete**, so no delete tool is exposed. A member
needs at least an email; labels are given as names (created if new) and newsletters as
ids, both linked as needed.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ghost_mcp.errors import NotFoundError
from ghost_mcp.tools._client import admin_client

#: Resolve labels + subscribed newsletters so a member summary is complete.
_WITH_RELATIONS = {"include": "newsletters,labels"}


def _summary(member: dict) -> dict:
    return {
        "id": member.get("id"),
        "email": member.get("email"),
        "name": member.get("name"),
        "status": member.get("status"),
        "subscribed": member.get("subscribed"),
        "labels": [label.get("name") for label in (member.get("labels") or [])],
        "newsletters": [nl.get("name") for nl in (member.get("newsletters") or [])],
        "created_at": member.get("created_at"),
    }


def _fields(
    email: str | None,
    name: str | None,
    note: str | None,
    labels: list[str] | None,
    newsletter_ids: list[str] | None,
    subscribed: bool | None,
) -> dict:
    fields: dict = {}
    if email is not None:
        fields["email"] = email
    if name is not None:
        fields["name"] = name
    if note is not None:
        fields["note"] = note
    if labels is not None:
        fields["labels"] = [{"name": label} for label in labels]
    if newsletter_ids is not None:
        fields["newsletters"] = [{"id": nid} for nid in newsletter_ids]
    if subscribed is not None:
        fields["subscribed"] = subscribed
    return fields


def register(mcp: FastMCP) -> None:
    """Register the member tools on the given server."""

    @mcp.tool
    def list_members(
        limit: int = 15,
        page: int = 1,
        filter: str | None = None,
        order: str = "created_at desc",
    ) -> dict:
        """List members (newest first), with their labels and subscribed newsletters.

        Args:
            limit: Members per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost NQL filter, e.g. ``status:paid``, ``status:free``,
                ``label:vip``, or ``subscribed:true``.
            order: Sort order, e.g. ``created_at desc`` or ``email asc``.

        Returns:
            A list of member summaries and the pagination block.
        """
        params: dict[str, Any] = {"limit": limit, "page": page, "order": order, **_WITH_RELATIONS}
        if filter:
            params["filter"] = filter
        result = admin_client().browse("members", params=params)
        return {
            "members": [_summary(m) for m in result.get("members", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_member(member_id: str) -> dict:
        """Read a single member by id, including labels, newsletters, and tiers."""
        member = admin_client().read(
            "members", member_id, params={"include": "newsletters,labels,tiers"}
        )
        if not member:
            raise NotFoundError(f"member '{member_id}' not found")
        return _summary(member)

    @mcp.tool
    def create_member(
        email: str,
        name: str | None = None,
        note: str | None = None,
        labels: list[str] | None = None,
        newsletter_ids: list[str] | None = None,
    ) -> dict:
        """Create a member from an email address.

        Only ``email`` is required; the member is created as a free member. ``labels``
        are given as names (created if new); ``newsletter_ids`` subscribe the member to
        those newsletters (get the ids from ``list_newsletters``). Creating a member
        sends no email. Returns the created member's summary.

        Args:
            email: The member's email address (required).
            name: Optional display name.
            note: Optional internal note (max 2000 chars).
            labels: Optional label names to attach.
            newsletter_ids: Optional newsletter ids to subscribe the member to.
        """
        fields = _fields(email, name, note, labels, newsletter_ids, None)
        created = admin_client().add("members", fields, params=_WITH_RELATIONS)
        return _summary(created)

    @mcp.tool
    def update_member(
        member_id: str,
        email: str | None = None,
        name: str | None = None,
        note: str | None = None,
        labels: list[str] | None = None,
        newsletter_ids: list[str] | None = None,
        subscribed: bool | None = None,
    ) -> dict:
        """Update a member by id; only the fields you pass are changed.

        ``labels`` and ``newsletter_ids`` REPLACE the member's current sets, so pass
        the full list you want to keep. ``subscribed=false`` unsubscribes the member
        from all newsletters. Returns the updated member summary.
        """
        fields = _fields(email, name, note, labels, newsletter_ids, subscribed)
        updated = admin_client().edit("members", member_id, fields, params=_WITH_RELATIONS)
        return _summary(updated)
