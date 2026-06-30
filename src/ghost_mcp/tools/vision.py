"""Tools that let the model see the blog's structure before styling it."""

from fastmcp import FastMCP

from ghost_mcp.vision import extract_brand as _extract_brand
from ghost_mcp.vision import fetch_theme_structure


def register(mcp: FastMCP) -> None:
    """Register the vision tools on the given server."""

    @mcp.tool
    def extract_brand(site_url: str, path: str = "/") -> dict:
        """Distil a live site's brand into clean tokens to theme against.

        Step one of theming a customer's blog: point this at their public product or
        marketing site and it returns the brand to match, so you design against real
        colours and fonts instead of guessing or hand-reading a stylesheet. Fetches
        the page and its CSS (public http(s) only; private/localhost hosts refused).

        Args:
            site_url: The public site to inspect, e.g. ``https://example.com``.
            path: The page to read; the homepage usually carries the brand.

        Returns:
            A mapping with a frequency-ranked colour ``palette`` (hex), best-guess
            ``fonts`` (``heading``/``body``), a ``logo_url``, and a ``button_style``
            (background + border-radius). Confirm these with the user before building.
        """
        return _extract_brand(site_url, path).to_dict()

    @mcp.tool
    def get_theme_structure(blog_url: str, path: str = "/") -> dict:
        """Inspect a live Ghost page and return its markup and CSS.

        Fetches the public, rendered page at ``path`` along with the stylesheets it
        links to, so styling changes can target selectors that actually exist
        rather than guesses. The homepage and individual posts use different
        templates, so pass the path of the page you intend to restyle.

        Args:
            blog_url: The public base URL of the blog, e.g. ``https://example.com``.
            path: The page path to inspect, such as ``/`` or ``/my-post/``.

        Returns:
            A mapping with the resolved page URL, an indented skeleton of the
            markup, the list of CSS class names in use, and the contents of each
            relevant stylesheet keyed by its URL.
        """
        return fetch_theme_structure(blog_url, path).to_dict()
