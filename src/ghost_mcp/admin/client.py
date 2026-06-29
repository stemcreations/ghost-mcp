"""An authenticated client for the Ghost Admin API.

The Admin API is uniform: every resource (posts, members, tags, …) supports the
same browse/read/add/edit/delete operations over a consistent JSON envelope. This
client provides those operations generically, plus low-level verb methods for the
few endpoints that don't follow the pattern (such as settings and theme uploads).

A fresh token is signed for every request, so one client instance can be reused
for the lifetime of the server.
"""

from __future__ import annotations

from typing import Any

import httpx

from ghost_mcp.admin.auth import mint_admin_token
from ghost_mcp.config import Settings
from ghost_mcp.errors import GhostAPIError

JSONDict = dict[str, Any]


class GhostAdminClient:
    """Issues authenticated requests against the Ghost Admin API."""

    def __init__(
        self,
        settings: Settings,
        *,
        accept_version: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._accept_version = accept_version or settings.api_version
        self._client = httpx.Client(
            base_url=settings.admin_api_base.rstrip("/") + "/",
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    # -- low-level verbs -----------------------------------------------------

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        token = mint_admin_token(self._settings.staff_token)
        headers = {
            "Authorization": f"Ghost {token}",
            "Accept-Version": self._accept_version,
        }
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: JSONDict | None = None,
        files: dict[str, Any] | None = None,
    ) -> JSONDict:
        """Send an authenticated request and return the decoded JSON body.

        Resource paths are relative to the Admin API base, e.g. ``/posts/``.

        Raises:
            GhostAPIError: if Ghost responds with a 4xx or 5xx status.
        """
        extra = {"Content-Type": "application/json"} if json is not None else None
        response = self._client.request(
            method,
            path.lstrip("/"),
            params=params,
            json=json,
            files=files,
            headers=self._headers(extra),
        )
        if response.is_error:
            raise GhostAPIError.from_response(response)
        return response.json() if response.content else {}

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> JSONDict:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json: JSONDict | None = None,
        files: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> JSONDict:
        return self.request("POST", path, json=json, files=files, params=params)

    def put(
        self,
        path: str,
        *,
        json: JSONDict,
        params: dict[str, Any] | None = None,
    ) -> JSONDict:
        return self.request("PUT", path, json=json, params=params)

    # -- generic resource CRUD ----------------------------------------------

    def browse(self, resource: str, *, params: dict[str, Any] | None = None) -> JSONDict:
        """List a resource. Returns the full envelope including ``meta`` pagination."""
        return self.get(f"/{resource}/", params=params)

    def read(
        self,
        resource: str,
        identifier: str,
        *,
        slug: bool = False,
        params: dict[str, Any] | None = None,
    ) -> JSONDict:
        """Return a single resource by id, or by slug when ``slug=True``."""
        path = f"/{resource}/slug/{identifier}/" if slug else f"/{resource}/{identifier}/"
        return _single(self.get(path, params=params), resource)

    def add(
        self,
        resource: str,
        data: JSONDict,
        *,
        params: dict[str, Any] | None = None,
    ) -> JSONDict:
        """Create a resource from ``data`` and return the created object."""
        return _single(self.post(f"/{resource}/", json={resource: [data]}, params=params), resource)

    def edit(
        self,
        resource: str,
        identifier: str,
        data: JSONDict,
        *,
        params: dict[str, Any] | None = None,
    ) -> JSONDict:
        """Update a resource by id and return the updated object."""
        body = {resource: [data]}
        return _single(self.put(f"/{resource}/{identifier}/", json=body, params=params), resource)

    def delete(self, resource: str, identifier: str) -> None:
        """Delete a resource by id."""
        self.request("DELETE", f"/{resource}/{identifier}/")

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> GhostAdminClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _single(payload: JSONDict, resource: str) -> JSONDict:
    """Unwrap the first item from a ``{resource: [...]}`` envelope."""
    items = payload.get(resource) or []
    return items[0] if items else {}
