"""The exception hierarchy shared across the package.

Every error raised by ``ghost_mcp`` derives from :class:`GhostError`, so callers
can catch one type to handle anything the server throws.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


class GhostError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(GhostError):
    """Configuration is missing or malformed."""


class ThemeError(GhostError):
    """A theme could not be built, packaged, or previewed."""


class NotFoundError(GhostError):
    """A requested resource was not found."""


class ResearchError(GhostError):
    """A search-research request failed (bad key, exhausted credits, bad response)."""


class GhostAPIError(GhostError):
    """The Ghost Admin API returned an error response.

    Attributes:
        status_code: The HTTP status code of the failed response, if known.
        errors: The list of error objects Ghost returned, each typically with a
            ``message`` and ``type``.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errors: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []

    @classmethod
    def from_response(cls, response: httpx.Response) -> GhostAPIError:
        """Build an error from a failed Admin API response.

        Ghost returns failures as ``{"errors": [{"message": ...}, ...]}``; this
        pulls those messages out so the raised error reads clearly. It tolerates
        malformed bodies (a non-dict body, or error entries that aren't dicts).
        """
        errors: list[dict] = []
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            errors = [e for e in (body.get("errors") or []) if isinstance(e, dict)]
        detail = "; ".join(e["message"] for e in errors if e.get("message"))
        message = detail or f"Ghost API request failed with status {response.status_code}"
        return cls(message, status_code=response.status_code, errors=errors)
