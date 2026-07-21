"""A thin client for the serper.dev Google Search API.

Serper is *optional*. When ``SERPER_API_KEY`` is unset the research tools are never
registered (see :func:`ghost_mcp.config.serper_api_key`), so this module is only
reached once a key exists. Constructing a client without one is still an error
rather than a silent no-op, as a backstop.

Every call costs an API credit, which is why the tool layer above splits work by
cost: a plain search is one credit, while a full content brief is one credit plus
a handful of (free) page fetches.
"""

from __future__ import annotations

from typing import Any

import httpx

from ghost_mcp.config import serper_api_key
from ghost_mcp.errors import ConfigError, ResearchError

SEARCH_URL = "https://google.serper.dev/search"
AUTOCOMPLETE_URL = "https://google.serper.dev/autocomplete"

JSONDict = dict[str, Any]


def _error_message(response: httpx.Response) -> str:
    """Turn a failed Serper response into an actionable message."""
    if response.status_code in (401, 403):
        return "Serper rejected the API key (401/403). Check SERPER_API_KEY."
    if response.status_code == 429:
        return "Serper credits are exhausted or rate-limited (429). Try again later."
    detail = response.text.strip()[:200]
    return f"Serper request failed with status {response.status_code}" + (
        f": {detail}" if detail else ""
    )


class SerperClient:
    """Issues requests against the serper.dev API."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = api_key or serper_api_key()
        if not key:
            raise ConfigError(
                "SERPER_API_KEY is not set, so the search-research tools are unavailable. "
                'Set it in your MCP client\'s "env" config, or in a local .env file '
                "(see .env.example), then restart the server."
            )
        self._api_key = key
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport)

    def _post(self, url: str, payload: JSONDict) -> JSONDict:
        """POST a JSON payload and return the decoded body.

        Raises:
            ResearchError: on a transport failure, an error status, or a non-JSON body.
        """
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        try:
            response = self._client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ResearchError(f"Serper request failed: {exc}") from exc
        if response.is_error:
            raise ResearchError(_error_message(response))
        try:
            body = response.json()
        except ValueError as exc:
            raise ResearchError("Serper returned a body that is not valid JSON.") from exc
        return body if isinstance(body, dict) else {"results": body}

    def search(
        self,
        query: str,
        *,
        num: int = 10,
        gl: str = "us",
        hl: str = "en",
        location: str | None = None,
    ) -> JSONDict:
        """Run one Google search. Costs one credit.

        Args:
            query: The search query.
            num: How many organic results to request.
            gl: Country code biasing the results, e.g. ``us``.
            hl: Interface language code, e.g. ``en``.
            location: Optional locality to search from, e.g. ``Denver, Colorado,
                United States``. Strongly affects whether a local pack appears, so
                pass it when researching a query with local intent.

        Returns:
            Serper's raw response: ``organic``, and optionally ``peopleAlsoAsk``,
            ``relatedSearches``, ``places``, and ``knowledgeGraph``.
        """
        payload: JSONDict = {"q": query, "num": num, "gl": gl, "hl": hl}
        if location:
            payload["location"] = location
        return self._post(SEARCH_URL, payload)

    def autocomplete(self, query: str, *, gl: str = "us", hl: str = "en") -> list[str]:
        """Return Google's autocomplete suggestions for a prefix. Costs one credit."""
        body = self._post(AUTOCOMPLETE_URL, {"q": query, "gl": gl, "hl": hl})
        suggestions = body.get("suggestions") or []
        return [
            value
            for item in suggestions
            if (value := (item.get("value") if isinstance(item, dict) else item))
        ]

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> SerperClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
