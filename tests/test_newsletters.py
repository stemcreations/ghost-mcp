"""Unit tests for the newsletter tool helpers."""

from ghost_mcp.tools.newsletters import _fields, _summary


def test_fields_keeps_only_provided() -> None:
    assert _fields("Weekly", None, None, None, None, None, None, None) == {"name": "Weekly"}


def test_fields_includes_all_provided() -> None:
    assert _fields(
        "Weekly", "desc", "archived", "Sender", "s@e.com", "support", True, "<p>foot</p>"
    ) == {
        "name": "Weekly",
        "description": "desc",
        "status": "archived",
        "sender_name": "Sender",
        "sender_email": "s@e.com",
        "sender_reply_to": "support",
        "subscribe_on_signup": True,
        "footer_content": "<p>foot</p>",
    }


def test_fields_allows_subscribe_on_signup_false() -> None:
    assert _fields("Weekly", None, None, None, None, None, False, None) == {
        "name": "Weekly",
        "subscribe_on_signup": False,
    }


def test_summary_picks_key_fields() -> None:
    summary = _summary(
        {
            "id": "1",
            "name": "Weekly",
            "slug": "weekly",
            "status": "active",
            "subscribe_on_signup": True,
            "sender_email": None,
        }
    )
    assert summary["id"] == "1"
    assert summary["status"] == "active"
    assert summary["subscribe_on_signup"] is True
