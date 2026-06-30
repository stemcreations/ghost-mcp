"""Image upload for the Ghost Admin API.

The image-upload endpoint doesn't fit the generic resource CRUD shape: it's a
multipart POST that returns a bare ``{"images": [{"url": ...}]}`` envelope. This
helper wraps it on top of :class:`~ghost_mcp.admin.client.GhostAdminClient`.

Uploading is the enabler for putting real images on the blog: ``feature_image``,
the site ``logo``/``icon``, and a newsletter ``header_image`` all take a URL, and
this returns one for a local file or a fetched remote image. Non-file form fields
ride alongside the file as ``(None, value)`` tuples, so no client change is needed.
"""

from __future__ import annotations

from ghost_mcp.admin.client import GhostAdminClient, _single
from ghost_mcp.errors import GhostError

#: The purposes Ghost accepts. ``profile_image`` and ``icon`` must be square; ``icon``
#: also accepts ICO.
ALLOWED_PURPOSES = ("image", "profile_image", "icon")


def upload_image(
    client: GhostAdminClient,
    image_bytes: bytes,
    *,
    filename: str,
    content_type: str = "application/octet-stream",
    purpose: str = "image",
    ref: str | None = None,
) -> str:
    """Upload image bytes and return the hosted URL.

    Args:
        client: An authenticated Admin API client.
        image_bytes: The raw image data.
        filename: The filename to send with the upload; its extension helps Ghost.
        content_type: The image MIME type, e.g. ``image/png``.
        purpose: One of ``image``, ``profile_image``, or ``icon`` (validated here).
        ref: Optional reference echoed back by Ghost (handy for find/replace of
            local paths).

    Returns:
        The hosted image URL.

    Raises:
        GhostError: if ``purpose`` is not one of the allowed values.
        GhostAPIError: if Ghost rejects the upload (bad format, too large, …).
    """
    if purpose not in ALLOWED_PURPOSES:
        raise GhostError(f"purpose must be one of {', '.join(ALLOWED_PURPOSES)}; got {purpose!r}.")
    files: dict = {
        "file": (filename, image_bytes, content_type),
        "purpose": (None, purpose),
    }
    if ref is not None:
        files["ref"] = (None, ref)
    return _single(client.post("/images/upload/", files=files), "images").get("url", "")
