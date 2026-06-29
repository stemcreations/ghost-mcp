"""Tools for previewing Ghost themes (packaging/upload tools land here too)."""

import tempfile

from fastmcp import FastMCP

from ghost_mcp.theme.preview import serve_preview, write_preview


def register(mcp: FastMCP) -> None:
    """Register the theme tools on the given server."""

    @mcp.tool
    def preview_theme(theme_path: str) -> dict:
        """Render a Ghost theme locally and serve it for preview in a browser.

        Builds a static render of the theme's home, post, and page templates using
        sample content, then serves it on localhost. Open the returned URL in a
        browser to check layout and styling before activating the theme on the live
        site. The render is a style-focused mockup: structure and CSS are faithful,
        while content is sampled and some dynamic helpers are stubbed.

        Args:
            theme_path: Path to the theme directory to preview.

        Returns:
            A mapping with the base ``preview_url`` and the URL of each rendered page.
        """
        out_dir = tempfile.mkdtemp(prefix="ghost-mcp-preview-")
        written = write_preview(theme_path, out_dir)
        url, _server = serve_preview(out_dir)
        return {
            "preview_url": url,
            "pages": {name: f"{url}{path.name}" for name, path in written.items()},
        }
