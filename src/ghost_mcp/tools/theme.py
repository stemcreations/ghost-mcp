"""Tools for generating, previewing, and (later) uploading Ghost themes."""

import tempfile

from fastmcp import FastMCP

from ghost_mcp.theme.builder import ThemeSpec, build_theme
from ghost_mcp.theme.preview import serve_preview, write_preview


def register(mcp: FastMCP) -> None:
    """Register the theme tools on the given server."""

    @mcp.tool
    def create_theme(
        name: str,
        styles: str = "",
        description: str = "",
        index_template: str | None = None,
        post_template: str | None = None,
        page_template: str | None = None,
    ) -> dict:
        """Generate a complete, valid, previewable Ghost theme on disk.

        Writes a ready-to-use theme — layout, home/post/page templates, page
        handling, the Koenig CSS classes Ghost requires, and ``package.json`` — to a
        local directory. Supply ``styles`` (CSS) to design the look; the site's brand
        accent colour is available in CSS as ``var(--ghost-accent-color)``, so the
        theme respects the user's existing branding.

        Optionally override the home/post/page templates with your own Handlebars,
        but avoid block params (``as |x|``); they are rejected so the result can
        always be previewed locally.

        After generating, call ``preview_theme`` with the returned path to view it,
        then upload and activate it to publish.

        Args:
            name: Human-readable theme name (slugified for the package name).
            styles: CSS appended to the base stylesheet to design the theme.
            description: Optional theme description.
            index_template: Optional Handlebars override for the home template.
            post_template: Optional Handlebars override for the single-post template.
            page_template: Optional Handlebars override for the page template.

        Returns:
            A mapping with the generated ``theme_path`` and the list of files written.
        """
        overrides = {
            key: value
            for key, value in (
                ("index", index_template),
                ("post", post_template),
                ("page", page_template),
            )
            if value
        }
        spec = ThemeSpec(name=name, styles=styles, description=description, templates=overrides)
        theme_dir = build_theme(spec, tempfile.mkdtemp(prefix="ghost-mcp-theme-"))
        files = sorted(str(p.relative_to(theme_dir)) for p in theme_dir.rglob("*") if p.is_file())
        return {"theme_path": str(theme_dir), "files": files}

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
