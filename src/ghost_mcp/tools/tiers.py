"""Tools for managing tiers: list, read, create, update (no delete).

Tiers are the paid plans members subscribe to. They fit the generic Admin API
envelope, so these wrap the client directly. Two quirks: there is **no delete**
(retire a tier with ``active=False``), and Ghost omits prices/benefits from
responses unless asked, so browse/read/write pass
``include=monthly_price,yearly_price,benefits``.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.tools._client import admin_client

#: Tiers omit prices and benefits from responses unless explicitly included.
_WITH_PRICES = {"include": "monthly_price,yearly_price,benefits"}


def _summary(tier: dict) -> dict:
    return {
        "id": tier.get("id"),
        "name": tier.get("name"),
        "slug": tier.get("slug"),
        "type": tier.get("type"),
        "active": tier.get("active"),
        "visibility": tier.get("visibility"),
        "monthly_price": tier.get("monthly_price"),
        "yearly_price": tier.get("yearly_price"),
        "currency": tier.get("currency"),
        "benefits": tier.get("benefits"),
    }


def _fields(
    name: str | None,
    description: str | None,
    monthly_price: int | None,
    yearly_price: int | None,
    currency: str | None,
    benefits: list[str] | None,
    visibility: str | None,
    welcome_page_url: str | None,
    trial_days: int | None,
    active: bool | None,
) -> dict:
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if monthly_price is not None:
        fields["monthly_price"] = monthly_price
    if yearly_price is not None:
        fields["yearly_price"] = yearly_price
    if currency is not None:
        fields["currency"] = currency
    if benefits is not None:
        fields["benefits"] = benefits
    if visibility is not None:
        fields["visibility"] = visibility
    if welcome_page_url is not None:
        fields["welcome_page_url"] = welcome_page_url
    if trial_days is not None:
        fields["trial_days"] = trial_days
    if active is not None:
        fields["active"] = active
    return fields


def register(mcp: FastMCP) -> None:
    """Register the tier tools on the given server."""

    @mcp.tool
    def list_tiers(
        limit: int = 50,
        page: int = 1,
        filter: str | None = None,
        order: str = "created_at asc",
    ) -> dict:
        """List tiers (paid plans), including their prices and benefits.

        Args:
            limit: Tiers per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost filter, e.g. ``type:paid`` or ``active:true``.
            order: Sort order, e.g. ``created_at asc``.

        Returns:
            A list of tier summaries and the pagination block.
        """
        params: dict = {"limit": limit, "page": page, "order": order, **_WITH_PRICES}
        if filter:
            params["filter"] = filter
        result = admin_client().browse("tiers", params=params)
        return {
            "tiers": [_summary(t) for t in result.get("tiers", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_tier(tier_id: str) -> dict:
        """Read a single tier by id, including its prices and benefits."""
        return _summary(admin_client().read("tiers", tier_id, params=_WITH_PRICES))

    @mcp.tool
    def create_tier(
        name: str,
        description: str | None = None,
        monthly_price: int | None = None,
        yearly_price: int | None = None,
        currency: str | None = None,
        benefits: list[str] | None = None,
        visibility: str | None = None,
        welcome_page_url: str | None = None,
        trial_days: int | None = None,
    ) -> dict:
        """Create a tier (paid plan).

        Only ``name`` is required. Prices are in the smallest currency unit (e.g.
        ``1000`` = $10.00) and pair with a ``currency`` (three-letter ISO code).
        ``benefits`` is a list of short strings shown on the tier. Returns the created
        tier summary.
        """
        fields = _fields(
            name,
            description,
            monthly_price,
            yearly_price,
            currency,
            benefits,
            visibility,
            welcome_page_url,
            trial_days,
            None,
        )
        return _summary(admin_client().add("tiers", fields, params=_WITH_PRICES))

    @mcp.tool
    def update_tier(
        tier_id: str,
        name: str | None = None,
        description: str | None = None,
        monthly_price: int | None = None,
        yearly_price: int | None = None,
        currency: str | None = None,
        benefits: list[str] | None = None,
        visibility: str | None = None,
        welcome_page_url: str | None = None,
        trial_days: int | None = None,
        active: bool | None = None,
    ) -> dict:
        """Update a tier by id; only the fields you pass are changed.

        There is no delete for tiers; retire one with ``active=False`` instead.
        Returns the updated tier summary.
        """
        fields = _fields(
            name,
            description,
            monthly_price,
            yearly_price,
            currency,
            benefits,
            visibility,
            welcome_page_url,
            trial_days,
            active,
        )
        return _summary(admin_client().edit("tiers", tier_id, fields, params=_WITH_PRICES))
