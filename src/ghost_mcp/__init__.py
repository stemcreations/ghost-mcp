"""Ghost Styling MCP: tools for styling and managing a Ghost blog over MCP.

The package is organised in layers, each with a single responsibility:

* :mod:`ghost_mcp.config`: load and validate configuration from the environment.
* :mod:`ghost_mcp.errors`: the shared exception hierarchy.
* :mod:`ghost_mcp.admin`: authenticated access to the Ghost Admin API.
* :mod:`ghost_mcp.vision`: inspect the public rendered blog (no authentication).
* :mod:`ghost_mcp.tools`: expose the layers above as MCP tools.
* :mod:`ghost_mcp.server`: assemble everything into a runnable server.

The initial focus is the vision and styling tools; the authenticated client is
generic so the remaining Admin API resources (posts, members, tags, …) can be
added as thin tool wrappers later.
"""

__version__ = "0.1.0"
