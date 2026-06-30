"""Tools for generating, previewing, uploading, and listing Ghost themes.

Activation is deliberately NOT exposed as a tool: it changes the live site, so it
stays a manual step (Ghost Admin, or the Python helper) for safety.
"""

import atexit
import shutil
import tempfile
from pathlib import Path

from fastmcp import FastMCP

from ghost_mcp.admin import themes
from ghost_mcp.theme.builder import ThemeSpec, build_theme, package_theme
from ghost_mcp.theme.preview import serve_preview, write_preview
from ghost_mcp.tools._client import admin_client

# At most one preview server runs at a time. Each new preview replaces and cleans up
# the previous one (server + rendered files); the active one is also torn down at exit.
_active_preview: dict = {"server": None, "out_dir": None}


def _stop_active_preview() -> None:
    """Shut down the current preview server and remove its rendered files."""
    server = _active_preview.get("server")
    if server is not None:
        server.shutdown()
    out_dir = _active_preview.get("out_dir")
    if out_dir is not None:
        shutil.rmtree(out_dir, ignore_errors=True)
    _active_preview["server"] = None
    _active_preview["out_dir"] = None


atexit.register(_stop_active_preview)


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

        Writes a ready-to-use theme (layout, home/post/page templates, page
        handling, the Koenig CSS classes Ghost requires, and ``package.json``) to a
        local directory. Supply ``styles`` (CSS) to design the look; the site's brand
        accent colour is available in CSS as ``var(--ghost-accent-color)``, so the
        theme respects the user's existing branding.

        Optionally override the home/post/page templates with your own Handlebars,
        but avoid block params (``as |x|``); they are rejected so the result can
        always be previewed locally.

        After generating, call ``preview_theme`` with the returned path to view it,
        then ``upload_theme`` to install it (activation stays manual).

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
        _stop_active_preview()
        out_dir = tempfile.mkdtemp(prefix="ghost-mcp-preview-")
        written = write_preview(theme_path, out_dir)
        url, server = serve_preview(out_dir)
        _active_preview["server"] = server
        _active_preview["out_dir"] = out_dir
        return {
            "preview_url": url,
            "pages": {name: f"{url}{path.name}" for name, path in written.items()},
        }

    @mcp.tool
    def upload_theme(theme_path: str) -> dict:
        """Package a theme directory and upload it to Ghost WITHOUT activating it.

        The live site keeps its current theme; the uploaded theme is installed but
        inactive, so it can be reviewed and activated manually. Ghost validates the
        theme on upload; any errors or warnings are returned.

        Args:
            theme_path: Path to the theme directory to upload.

        Returns:
            The installed theme ``name``, its ``active`` flag (False), and any
            validation ``errors``/``warnings``.
        """
        zip_bytes = package_theme(theme_path)
        uploaded = themes.upload_theme(
            admin_client(), zip_bytes, filename=f"{Path(theme_path).name}.zip"
        )
        return {
            "name": uploaded.get("name"),
            "active": uploaded.get("active"),
            "errors": [e.get("rule") for e in (uploaded.get("errors") or [])],
            "warnings": [w.get("rule") for w in (uploaded.get("warnings") or [])],
            "note": (
                "Uploaded but NOT activated. Activate it in Ghost Admin "
                "(Settings → Design) when ready."
            ),
        }

    @mcp.tool
    def list_themes() -> dict:
        """List the themes installed on the blog and which one is active."""
        installed = themes.list_themes(admin_client())
        return {
            "themes": [{"name": t.get("name"), "active": t.get("active")} for t in installed],
            "active": next((t.get("name") for t in installed if t.get("active")), None),
        }

    @mcp.tool
    def download_theme(name: str) -> dict:
        """Download an installed theme's source as a ZIP to a local temp file.

        Useful for grabbing a theme's assets, branding, or ``package.json`` as a
        reference. Returns the path to the downloaded file and its size.

        Args:
            name: The name of the installed theme to download.
        """
        data = themes.download_theme(admin_client(), name)
        path = Path(tempfile.mkdtemp(prefix="ghost-mcp-download-")) / f"{name}.zip"
        path.write_bytes(data)
        return {"path": str(path), "bytes": len(data)}
