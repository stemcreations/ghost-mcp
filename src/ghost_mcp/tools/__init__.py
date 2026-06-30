"""MCP tool definitions.

Each module here exposes a ``register(mcp)`` function that attaches its tools to a
FastMCP server. To add a group of tools, create a module with a ``register``
function and call it from :func:`register_all`.
"""

from fastmcp import FastMCP

from ghost_mcp.tools import (
    images,
    labels,
    members,
    newsletters,
    offers,
    pages,
    posts,
    prompts,
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
