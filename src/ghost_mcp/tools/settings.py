"""Tools for reading and updating site settings: brand, SEO metadata, navigation.

These operate on Ghost's site-wide settings, which are independent of the active
theme, so they let the blog's identity, branding, and SEO/social metadata be kept
cohesive with the rest of the site.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ghost_mcp.admin import settings as settings_api
from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client

#: The brand/SEO subset surfaced to the model (the full table holds ~99 keys,
#: including secrets like Stripe and Mailgun credentials, which stay hidden).
_PUBLIC_KEYS = (
    "title",
    "description",
    "accent_color",
    "logo",
    "icon",
    "cover_image",
    "meta_title",
    "meta_description",
    "og_title",
    "og_description",
    "og_image",
    "twitter_title",
    "twitter_description",
    "twitter_image",
    "locale",
    "navigation",
    "secondary_navigation",
    "codeinjection_head",
)


def _nav_items(raw: list[dict] | None) -> list[dict[str, str]]:
    """Coerce raw menu entries into Ghost's ``[{label, url}]`` navigation value.

    Each entry must carry a ``label`` and a ``url``; any extra keys (e.g. the
    ``external``/``kind`` hints from ``extract_brand``) are dropped, so the output of
    that tool can be passed straight through. Raises ``GhostError`` on a malformed
    entry rather than silently writing a broken menu.
    """
    items: list[dict[str, str]] = []
    for entry in raw or []:
        if not isinstance(entry, dict) or "label" not in entry or "url" not in entry:
            raise GhostError("each navigation item needs a 'label' and a 'url'.")
        items.append({"label": str(entry["label"]), "url": str(entry["url"])})
    return items


def register(mcp: FastMCP) -> None:
    """Register the settings tools on the given server."""

    @mcp.tool
    def get_site_settings() -> dict:
        """Read the blog's brand and SEO settings.

        Returns the site identity (title, description), branding (accent colour,
        logo, icon, cover), and SEO/social metadata (meta title/description and the
        Open Graph and Twitter card fields). Use it to review the current state
        before updating, or to keep the blog aligned with the main site.
        """
        current = settings_api.get_settings(admin_client())
        return {key: current.get(key) for key in _PUBLIC_KEYS}

    @mcp.tool
    def update_site_metadata(
        title: str | None = None,
        description: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        og_title: str | None = None,
        og_description: str | None = None,
        og_image: str | None = None,
        twitter_title: str | None = None,
        twitter_description: str | None = None,
        twitter_image: str | None = None,
    ) -> dict:
        """Update the blog's identity and SEO/social metadata.

        Sets the site title/description, the search-result metadata
        (meta_title/meta_description), and the Open Graph and Twitter card fields
        used when posts are shared. Only the arguments you provide are changed; omit
        the rest. Good ``meta_*`` and social fields help the blog present and rank
        well.

        Returns the fields that were updated, with their new values.
        """
        provided = {
            "title": title,
            "description": description,
            "meta_title": meta_title,
            "meta_description": meta_description,
            "og_title": og_title,
            "og_description": og_description,
            "og_image": og_image,
            "twitter_title": twitter_title,
            "twitter_description": twitter_description,
            "twitter_image": twitter_image,
        }
        changes = {key: value for key, value in provided.items() if value is not None}
        if not changes:
            return {"updated": {}, "note": "No fields provided. Nothing changed."}
        updated = settings_api.update_settings(admin_client(), changes)
        return {"updated": {key: updated.get(key) for key in changes}}

    @mcp.tool
    def update_branding(accent_color: str | None = None) -> dict:
        """Update the blog's brand accent colour.

        ``accent_color`` is a hex value such as ``#4a7c59``. Keeping it aligned with
        the main site's brand makes the blog feel like part of the same product.

        Returns the fields that were updated.
        """
        changes = {}
        if accent_color is not None:
            changes["accent_color"] = accent_color
        if not changes:
            return {"updated": {}, "note": "No fields provided. Nothing changed."}
        updated = settings_api.update_settings(admin_client(), changes)
        return {"updated": {key: updated.get(key) for key in changes}}

    @mcp.tool
    def update_navigation(
        primary: list[dict] | None = None,
        secondary: list[dict] | None = None,
    ) -> dict:
        """Set the blog's navigation menus (primary header and secondary/footer).

        Each menu is a list of ``{"label": ..., "url": ...}`` items. The whole menu
        is REPLACED, not appended to, so send the complete set you want; pass only the
        menu(s) you mean to change and the other is left untouched. URLs are usually
        site-relative (``/about/``) or absolute. Extra keys on an item (such as the
        ``external``/``kind`` hints from ``extract_brand``) are ignored, so links read
        from a site can be passed straight through.

        Membership actions (login/sign-up/account) belong in the theme as Ghost Portal
        buttons (``data-portal``), not here -- don't add them as menu links. Confirm
        the menus with the user before calling this; it changes the live site.

        Args:
            primary: The primary (header) menu, or ``None`` to leave it unchanged.
            secondary: The secondary (footer) menu, or ``None`` to leave it unchanged.

        Returns:
            The menus that were updated, with their new values.
        """
        changes: dict[str, Any] = {}
        if primary is not None:
            changes["navigation"] = _nav_items(primary)
        if secondary is not None:
            changes["secondary_navigation"] = _nav_items(secondary)
        if not changes:
            return {"updated": {}, "note": "No menus provided. Nothing changed."}
        updated = settings_api.update_settings(admin_client(), changes)
        return {"updated": {key: updated.get(key) for key in changes}}
