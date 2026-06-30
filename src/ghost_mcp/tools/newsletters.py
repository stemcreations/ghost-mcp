"""Tools for managing newsletters: list, read, create, update.

Newsletters are the email channels members subscribe to; every site has at least one.
The Admin API supports browse/read/create/update but **not delete** -- a newsletter is
retired by setting its ``status`` to ``archived`` rather than deleted.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ghost_mcp.errors import NotFoundError
from ghost_mcp.tools._client import admin_client


def _summary(newsletter: dict) -> dict:
    return {
        "id": newsletter.get("id"),
        "name": newsletter.get("name"),
        "description": newsletter.get("description"),
        "slug": newsletter.get("slug"),
        "status": newsletter.get("status"),
        "visibility": newsletter.get("visibility"),
        "subscribe_on_signup": newsletter.get("subscribe_on_signup"),
        "sender_name": newsletter.get("sender_name"),
        "sender_email": newsletter.get("sender_email"),
        "sender_reply_to": newsletter.get("sender_reply_to"),
        "sort_order": newsletter.get("sort_order"),
    }


def _fields(
    name: str | None,
    description: str | None,
    status: str | None,
    sender_name: str | None,
    sender_email: str | None,
    sender_reply_to: str | None,
    subscribe_on_signup: bool | None,
    footer_content: str | None,
) -> dict:
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if status is not None:
        fields["status"] = status
    if sender_name is not None:
        fields["sender_name"] = sender_name
    if sender_email is not None:
        fields["sender_email"] = sender_email
    if sender_reply_to is not None:
        fields["sender_reply_to"] = sender_reply_to
    if subscribe_on_signup is not None:
        fields["subscribe_on_signup"] = subscribe_on_signup
    if footer_content is not None:
        fields["footer_content"] = footer_content
    return fields


def register(mcp: FastMCP) -> None:
    """Register the newsletter tools on the given server."""

    @mcp.tool
    def list_newsletters(
        limit: int = 50,
        page: int = 1,
        filter: str | None = None,
        order: str = "sort_order asc",
    ) -> dict:
        """List newsletters (active and archived).

        Args:
            limit: Newsletters per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost NQL filter, e.g. ``status:active``.
            order: Sort order, e.g. ``sort_order asc``.

        Returns:
            A list of newsletter summaries and the pagination block.
        """
        params: dict[str, Any] = {"limit": limit, "page": page, "order": order}
        if filter:
            params["filter"] = filter
        result = admin_client().browse("newsletters", params=params)
        return {
            "newsletters": [_summary(n) for n in result.get("newsletters", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_newsletter(newsletter_id: str) -> dict:
        """Read a single newsletter by id."""
        newsletter = admin_client().read("newsletters", newsletter_id)
        if not newsletter:
            raise NotFoundError(f"newsletter '{newsletter_id}' not found")
        return _summary(newsletter)

    @mcp.tool
    def create_newsletter(
        name: str,
        description: str | None = None,
        sender_name: str | None = None,
        sender_reply_to: str | None = None,
        subscribe_on_signup: bool | None = None,
        opt_in_existing: bool = False,
    ) -> dict:
        """Create a newsletter.

        Only ``name`` is required. ``sender_reply_to`` is either ``"newsletter"`` (use
        the sender address) or ``"support"`` (use the Portal support address). Set
        ``opt_in_existing=true`` to also subscribe existing subscribed members to this
        new newsletter. To set a custom ``sender_email``, create the newsletter first,
        then ``update_newsletter`` (the address needs email verification). Returns the
        created newsletter's summary.
        """
        fields = _fields(
            name, description, None, sender_name, None, sender_reply_to, subscribe_on_signup, None
        )
        params = {"opt_in_existing": "true"} if opt_in_existing else None
        created = admin_client().add("newsletters", fields, params=params)
        return _summary(created)

    @mcp.tool
    def update_newsletter(
        newsletter_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        sender_name: str | None = None,
        sender_email: str | None = None,
        sender_reply_to: str | None = None,
        subscribe_on_signup: bool | None = None,
        footer_content: str | None = None,
    ) -> dict:
        """Update a newsletter by id; only the fields you pass are changed.

        Set ``status="archived"`` to retire a newsletter (there is no delete) or
        ``"active"`` to restore it. Changing ``sender_email`` starts an email
        verification: Ghost emails the new address and it does NOT take effect until
        the link is clicked, so ``sender_email`` may still read as its old value right
        after this call. ``sender_reply_to`` is ``"newsletter"`` or ``"support"``.
        Returns the updated newsletter summary.
        """
        fields = _fields(
            name,
            description,
            status,
            sender_name,
            sender_email,
            sender_reply_to,
            subscribe_on_signup,
            footer_content,
        )
        updated = admin_client().edit("newsletters", newsletter_id, fields)
        result = _summary(updated)
        if sender_email is not None:
            result["note"] = (
                "Changing sender_email requires verification: Ghost emailed the new "
                "address, and it won't take effect until that link is clicked."
            )
        return result
