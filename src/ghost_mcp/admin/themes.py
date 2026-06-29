"""Theme upload, activation, and listing for the Ghost Admin API.

Themes are the one Admin API area that doesn't fit the generic resource CRUD shape:
uploads are multipart and activation is an action on a named theme. These helpers
wrap those endpoints on top of :class:`~ghost_mcp.admin.client.GhostAdminClient`.

Upload and activation are deliberately separate. Uploading installs a theme without
changing the live site, so a theme can be staged and validated before anyone chooses
to activate it.
"""

from __future__ import annotations

from ghost_mcp.admin.client import GhostAdminClient, JSONDict


def list_themes(client: GhostAdminClient) -> list[JSONDict]:
    """Return metadata for every installed theme."""
    return client.get("/themes/").get("themes", [])


def upload_theme(
    client: GhostAdminClient,
    zip_bytes: bytes,
    *,
    filename: str = "theme.zip",
) -> JSONDict:
    """Upload a theme ZIP without activating it.

    The live site keeps its current theme until :func:`activate_theme` is called.

    Args:
        client: An authenticated Admin API client.
        zip_bytes: The packaged theme archive.
        filename: The filename to send with the upload.

    Returns:
        The uploaded theme object, including its ``name`` and any validation
        warnings Ghost reports for the theme.
    """
    files = {"file": (filename, zip_bytes, "application/zip")}
    return _single(client.post("/themes/upload/", files=files))


def activate_theme(client: GhostAdminClient, name: str) -> JSONDict:
    """Activate an installed theme by name, making it the live theme."""
    return _single(client.request("PUT", f"/themes/{name}/activate/"))


def delete_theme(client: GhostAdminClient, name: str) -> None:
    """Delete an installed theme by name. The active theme cannot be deleted."""
    client.request("DELETE", f"/themes/{name}/")


def download_theme(client: GhostAdminClient, name: str) -> bytes:
    """Download an installed theme's source as ZIP bytes.

    Uses Ghost's theme-download endpoint (the one the Admin UI's download button
    calls). Useful for grabbing a theme's assets, branding, or ``package.json`` as a
    reference.
    """
    return client.get_bytes(f"/themes/{name}/download/")


def _single(payload: JSONDict) -> JSONDict:
    themes = payload.get("themes") or []
    return themes[0] if themes else {}
