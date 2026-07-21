"""A shared, lazily-created Admin API client reused across tool calls.

Building a client and re-reading the environment on every tool call is wasteful:
the HTTP connection pool can't be reused and ``.env`` is parsed each time. The
client is safe to share for the life of the process: it signs a fresh token per
request.
"""

from __future__ import annotations

import atexit
from functools import lru_cache

from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings, load_settings
from ghost_mcp.research.serper import SerperClient


@lru_cache(maxsize=1)
def config() -> Settings:
    """Process-wide configuration, read from the environment once."""
    return load_settings()


@lru_cache(maxsize=1)
def admin_client() -> GhostAdminClient:
    """A single Admin API client reused for the life of the process."""
    client = GhostAdminClient(config())
    atexit.register(client.close)
    return client


@lru_cache(maxsize=1)
def serper_client() -> SerperClient:
    """A single serper.dev client reused for the life of the process.

    Only reachable when the research tools were registered, i.e. when a key exists.
    """
    client = SerperClient()
    atexit.register(client.close)
    return client
