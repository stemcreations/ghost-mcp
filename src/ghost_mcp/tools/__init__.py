"""MCP tool definitions.

Each module here exposes a ``register(mcp)`` function that attaches its tools to a
FastMCP server. To add a group of tools, create a module with a ``register``
function and call it from :func:`register_all`.
"""

from fastmcp import FastMCP

from ghost_mcp.tools import posts, settings, tags, theme, vision


def register_all(mcp: FastMCP) -> None:
    """Attach every tool group to the given server."""
    vision.register(mcp)
    theme.register(mcp)
    settings.register(mcp)
    posts.register(mcp)
    tags.register(mcp)
