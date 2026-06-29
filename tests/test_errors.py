"""Unit tests for the error hierarchy and response parsing."""

import httpx

from ghost_mcp.errors import GhostAPIError


def test_from_response_extracts_messages() -> None:
    err = GhostAPIError.from_response(httpx.Response(422, json={"errors": [{"message": "Bad"}]}))
    assert "Bad" in str(err)
    assert err.status_code == 422


def test_from_response_tolerates_non_dict_error_entries() -> None:
    # Error entries that aren't objects must not crash the parser.
    err = GhostAPIError.from_response(httpx.Response(500, json={"errors": ["oops", None]}))
    assert err.status_code == 500


def test_from_response_tolerates_non_dict_body() -> None:
    err = GhostAPIError.from_response(httpx.Response(502, json=["gateway", "error"]))
    assert err.status_code == 502
