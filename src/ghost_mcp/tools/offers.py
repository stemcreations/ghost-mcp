"""Tools for managing offers: list, read, create, update (no delete).

Offers are discount codes applied to a tier. Creating one needs the full required
set (name, code, type, cadence, duration, amount, and a tier id); a ``fixed`` offer
also needs a ``currency`` matching the tier. On update Ghost only accepts
name/code/display_title/display_description — pricing is locked once created. There
is no delete; archive via ``update_offer`` is not exposed, mirroring the API.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client


def _summary(offer: dict) -> dict:
    tier = offer.get("tier") or {}
    return {
        "id": offer.get("id"),
        "name": offer.get("name"),
        "code": offer.get("code"),
        "type": offer.get("type"),
        "amount": offer.get("amount"),
        "cadence": offer.get("cadence"),
        "duration": offer.get("duration"),
        "status": offer.get("status"),
        "currency": offer.get("currency"),
        "redemption_count": offer.get("redemption_count"),
        "tier": {"id": tier.get("id"), "name": tier.get("name")},
        "display_title": offer.get("display_title"),
        "display_description": offer.get("display_description"),
    }


def _create_fields(
    name: str,
    code: str,
    tier_id: str,
    type: str,
    amount: int,
    cadence: str,
    duration: str,
    currency: str | None,
    display_title: str | None,
    display_description: str | None,
    duration_in_months: int | None,
) -> dict:
    """Build the create payload, validating the fixed-offer currency requirement."""
    if type == "fixed" and not currency:
        raise GhostError(
            "currency is required for a fixed offer; it must match the tier's currency."
        )
    fields: dict = {
        "name": name,
        "code": code,
        "type": type,
        "amount": amount,
        "cadence": cadence,
        "duration": duration,
        "tier": {"id": tier_id},
    }
    if currency is not None:
        fields["currency"] = currency
    if display_title is not None:
        fields["display_title"] = display_title
    if display_description is not None:
        fields["display_description"] = display_description
    if duration_in_months is not None:
        fields["duration_in_months"] = duration_in_months
    return fields


def _edit_fields(
    name: str | None,
    code: str | None,
    display_title: str | None,
    display_description: str | None,
) -> dict:
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if code is not None:
        fields["code"] = code
    if display_title is not None:
        fields["display_title"] = display_title
    if display_description is not None:
        fields["display_description"] = display_description
    return fields


def register(mcp: FastMCP) -> None:
    """Register the offer tools on the given server."""

    @mcp.tool
    def list_offers(limit: int = 50, page: int = 1) -> dict:
        """List discount offers, each with its linked tier.

        Args:
            limit: Offers per page (Ghost allows up to 100).
            page: Which page of results to return.

        Returns:
            A list of offer summaries and the pagination block.
        """
        result = admin_client().browse("offers", params={"limit": limit, "page": page})
        return {
            "offers": [_summary(o) for o in result.get("offers", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_offer(offer_id: str) -> dict:
        """Read a single offer by id, including its linked tier."""
        return _summary(admin_client().read("offers", offer_id))

    @mcp.tool
    def create_offer(
        name: str,
        code: str,
        tier_id: str,
        type: str,
        amount: int,
        cadence: str,
        duration: str = "once",
        currency: str | None = None,
        display_title: str | None = None,
        display_description: str | None = None,
        duration_in_months: int | None = None,
    ) -> dict:
        """Create a discount offer against a tier.

        Args:
            name: Internal name (must be unique).
            code: Shortcode for the offer URL (yoursite.com/<code>).
            tier_id: The tier the offer applies to (from ``list_tiers``).
            type: ``percent`` or ``fixed`` — whether ``amount`` is a percentage or a
                fixed value.
            amount: The discount, in percent or the smallest currency unit per ``type``.
            cadence: ``month`` or ``year`` — which of the tier's prices the offer applies to.
            duration: ``once``, ``forever``, or ``repeating`` (``repeating`` needs
                ``cadence="month"``).
            currency: Required when ``type="fixed"``; must match the tier's currency.
            display_title: Title shown in the offer window.
            display_description: Text shown in the offer window.
            duration_in_months: Months to repeat when ``duration="repeating"``.

        Returns the created offer summary.
        """
        fields = _create_fields(
            name,
            code,
            tier_id,
            type,
            amount,
            cadence,
            duration,
            currency,
            display_title,
            display_description,
            duration_in_months,
        )
        return _summary(admin_client().add("offers", fields))

    @mcp.tool
    def update_offer(
        offer_id: str,
        name: str | None = None,
        code: str | None = None,
        display_title: str | None = None,
        display_description: str | None = None,
    ) -> dict:
        """Update an offer by id.

        Ghost only allows editing ``name``, ``code``, and the display title/description
        of an existing offer; the pricing terms are fixed once created. Returns the
        updated offer summary.
        """
        fields = _edit_fields(name, code, display_title, display_description)
        return _summary(admin_client().edit("offers", offer_id, fields))
