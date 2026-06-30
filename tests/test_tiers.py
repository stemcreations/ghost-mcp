"""Unit tests for the tier tool helpers."""

from ghost_mcp.tools.tiers import _fields, _summary


def test_fields_keeps_only_provided() -> None:
    assert _fields("Gold", None, None, None, None, None, None, None, None, None) == {"name": "Gold"}


def test_fields_includes_prices_benefits_and_active() -> None:
    fields = _fields(
        "Gold", "desc", 1000, 10000, "usd", ["B1", "B2"], "public", "/welcome", 7, False
    )
    assert fields == {
        "name": "Gold",
        "description": "desc",
        "monthly_price": 1000,
        "yearly_price": 10000,
        "currency": "usd",
        "benefits": ["B1", "B2"],
        "visibility": "public",
        "welcome_page_url": "/welcome",
        "trial_days": 7,
        "active": False,  # False is a real value, not "omit"
    }


def test_summary_picks_relevant_fields() -> None:
    summary = _summary(
        {"id": "1", "name": "Gold", "monthly_price": 1000, "benefits": ["B"], "extra": "x"}
    )
    assert summary["id"] == "1"
    assert summary["monthly_price"] == 1000
    assert summary["benefits"] == ["B"]
    assert "extra" not in summary
