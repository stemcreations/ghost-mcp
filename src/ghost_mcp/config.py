"""Configuration loaded from the environment.

Configuration is read from environment variables (a local ``.env`` file is loaded
automatically to make development convenient):

``GHOST_ADMIN_URL``
    The base URL of the Ghost site, e.g. ``https://example.com``.

``GHOST_STAFF_ACCESS_TOKEN``
    A staff access token in ``id:secret`` form, copied from a user's profile page
    in Ghost Admin. It is used to sign short-lived Admin API tokens.

``GHOST_API_VERSION`` (optional)
    The Admin API version requested via the ``Accept-Version`` header, e.g.
    ``v6.0``. Defaults to ``v6.0``. This is a client compatibility hint that should
    match your running Ghost major version; it does not change the server's
    behaviour.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from ghost_mcp.errors import ConfigError

#: Admin API version requested via ``Accept-Version`` when none is configured.
DEFAULT_API_VERSION = "v6.0"


@dataclass(frozen=True)
class Settings:
    """Validated server configuration."""

    admin_url: str
    staff_token: str
    api_version: str = DEFAULT_API_VERSION

    @property
    def admin_api_base(self) -> str:
        """The Admin API base URL, e.g. ``https://example.com/ghost/api/admin``."""
        base = self.admin_url.rstrip("/")
        if "/ghost/api/admin" not in base:
            base += "/ghost/api/admin"
        return base

    @property
    def site_url(self) -> str:
        """The public site root, used by the vision tools to fetch rendered pages."""
        return self.admin_url.split("/ghost")[0].rstrip("/")


def load_settings() -> Settings:
    """Read and validate configuration from the environment.

    Raises:
        ConfigError: if a required variable is absent or the token is malformed.
    """
    load_dotenv()
    admin_url = os.environ.get("GHOST_ADMIN_URL", "").strip()
    staff_token = os.environ.get("GHOST_STAFF_ACCESS_TOKEN", "").strip()

    missing = [
        name
        for name, value in (
            ("GHOST_ADMIN_URL", admin_url),
            ("GHOST_STAFF_ACCESS_TOKEN", staff_token),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            'Set them in your MCP client\'s "env" config, or in a local .env file '
            "(see .env.example)."
        )
    if ":" not in staff_token:
        raise ConfigError(
            "GHOST_STAFF_ACCESS_TOKEN must be in 'id:secret' form "
            "(copy it from a user's profile page in Ghost Admin)."
        )
    api_version = _normalize_version(os.environ.get("GHOST_API_VERSION", ""))
    return Settings(admin_url=admin_url, staff_token=staff_token, api_version=api_version)


def _normalize_version(raw: str) -> str:
    """Coerce a user-supplied version into ``v{major}.{minor}`` form.

    Accepts ``6``, ``v6`` and ``v6.0`` alike; an empty value yields the default.
    """
    value = raw.strip().lstrip("vV")
    if not value:
        return DEFAULT_API_VERSION
    if "." not in value:
        value += ".0"
    return f"v{value}"
