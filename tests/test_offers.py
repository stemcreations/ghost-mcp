"""Unit tests for the offer tool helpers."""

import pytest

from ghost_mcp.errors import GhostError
from ghost_mcp.tools.offers import _create_fields, _edit_fields, _summary


def test_create_fields_nests_tier_id() -> None:
    fields = _create_fields(
        "BF", "bf", "tier1", "percent", 10, "year", "once", None, None, None, None
    )
    assert fields["tier"] == {"id": "tier1"}
    assert fields["type"] == "percent"
    assert fields["amount"] == 10
    assert "currency" not in fields


def test_create_fields_requires_currency_for_fixed() -> None:
    with pytest.raises(GhostError):
        _create_fields("BF", "bf", "tier1", "fixed", 500, "year", "once", None, None, None, None)


def test_create_fields_allows_fixed_with_currency() -> None:
    fields = _create_fields("BF", "bf", "tier1", "fixed", 500, "year", "once", "usd", "T", "D", 3)
    assert fields["currency"] == "usd"
    assert fields["display_title"] == "T"
    assert fields["duration_in_months"] == 3


def test_edit_fields_keeps_only_editable() -> None:
    assert _edit_fields(None, "newcode", None, None) == {"code": "newcode"}


def test_summary_flattens_tier() -> None:
    summary = _summary({"id": "1", "name": "BF", "tier": {"id": "t1", "name": "Gold"}})
    assert summary["tier"] == {"id": "t1", "name": "Gold"}
