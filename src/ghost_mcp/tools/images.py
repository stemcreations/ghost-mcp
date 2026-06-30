"""Tools for uploading images to the blog.

Today ``feature_image``, the site ``logo``/``icon`` (via update_branding), and a
newsletter ``header_image`` can only point at an existing URL. These tools upload a
local file or a public remote image and return the hosted URL to use for those fields.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from fastmcp import FastMCP

from ghost_mcp.admin import images as images_api
from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client
from ghost_mcp.vision.structure import fetch_public_bytes


def _content_type(filename: str) -> str:
    """Best-effort MIME type from a filename, defaulting to a generic binary type."""
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def register(mcp: FastMCP) -> None:
    """Register the image tools on the given server."""

    @mcp.tool
    def upload_image(file_path: str, purpose: str = "image") -> dict:
        """Upload a local image file to the blog and return its hosted URL.

        Use the returned URL for a post's ``feature_image``, the site ``logo``/``icon``
        (via update_branding), or a newsletter ``header_image``.

        Args:
            file_path: Path to a local image (WEBP, JPEG, GIF, PNG, SVG; ICO for icons).
            purpose: ``image`` (default), ``profile_image``, or ``icon``. The latter
                two must be square images.

        Returns:
            ``{"url": "<hosted image url>"}``.
        """
        path = Path(file_path)
        if not path.is_file():
            raise GhostError(f"image file not found: {file_path!r}")
        url = images_api.upload_image(
            admin_client(),
            path.read_bytes(),
            filename=path.name,
            content_type=_content_type(path.name),
            purpose=purpose,
        )
        return {"url": url}

    @mcp.tool
    def upload_image_from_url(source_url: str, purpose: str = "image") -> dict:
        """Fetch a public image by URL and re-upload it to the blog, returning the URL.

        The source is fetched under the same SSRF guard as the vision tools (public
        http(s) only; private/localhost hosts and oversized responses are refused),
        then uploaded to Ghost so the image is served from the blog itself.

        Args:
            source_url: A public image URL.
            purpose: ``image`` (default), ``profile_image``, or ``icon``.

        Returns:
            ``{"url": "<hosted image url>"}``.
        """
        final_url, body, content_type = fetch_public_bytes(source_url)
        filename = Path(urlsplit(final_url).path).name or "image"
        url = images_api.upload_image(
            admin_client(),
            body,
            filename=filename,
            content_type=content_type or _content_type(filename),
            purpose=purpose,
        )
        return {"url": url}
