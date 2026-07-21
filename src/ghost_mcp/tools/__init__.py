"""MCP tool definitions.

Each module here exposes a ``register(mcp)`` function that attaches its tools to a
FastMCP server. To add a group of tools, create a module with a ``register``
function and call it from :func:`register_all`.

One group is conditional: the research tools all require ``SERPER_API_KEY``, so they
are registered only when one is configured. Hiding them beats exposing tools that
always fail -- a model shown a tool will call it, and a failure it can't fix reads as
a broken server rather than a missing key.
"""

from fastmcp import FastMCP

from ghost_mcp.config import serper_api_key
from ghost_mcp.tools import (
    images,
    labels,
    members,
    newsletters,
    offers,
    pages,
    posts,
    prompts,
    research,
    settings,
    tags,
    theme,
    tiers,
    users,
    vision,
)


def register_all(mcp: FastMCP) -> None:
    """Attach every tool group to the given server."""
    vision.register(mcp)
    theme.register(mcp)
    settings.register(mcp)
    posts.register(mcp)
    pages.register(mcp)
    images.register(mcp)
    tags.register(mcp)
    members.register(mcp)
    newsletters.register(mcp)
    tiers.register(mcp)
    offers.register(mcp)
    labels.register(mcp)
    users.register(mcp)
    prompts.register(mcp)
    if serper_api_key():
        research.register(mcp)
