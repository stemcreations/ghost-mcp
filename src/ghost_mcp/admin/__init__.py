"""Authenticated access to the Ghost Admin API."""

from ghost_mcp.admin.auth import mint_admin_token
from ghost_mcp.admin.client import GhostAdminClient

__all__ = ["GhostAdminClient", "mint_admin_token"]
