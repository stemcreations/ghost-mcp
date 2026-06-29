"""The runnable Ghost Styling MCP server.

Run it interactively during development::

    uv run fastmcp dev src/ghost_mcp/server.py

or over stdio via the installed entry point::

    uv run ghost-mcp
"""

from fastmcp import FastMCP

from ghost_mcp.tools import register_all


def create_server() -> FastMCP:
    """Build a fully wired server instance."""
    mcp = FastMCP(name="Ghost Styling MCP")
    register_all(mcp)
    return mcp


#: Module-level server so ``fastmcp run`` / ``fastmcp dev`` can discover it.
mcp = create_server()


def main() -> None:
    """Entry point for the ``ghost-mcp`` command; serves over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
