"""Unit tests for the user tool helpers (read-only)."""

from ghost_mcp.tools.users import _summary


def test_summary_flattens_roles_and_post_count() -> None:
    summary = _summary(
        {
            "id": "1",
            "name": "Jo",
            "slug": "jo",
            "email": "jo@example.com",
            "roles": [{"name": "Author"}, {"name": "Editor"}],
            "count": {"posts": 5},
        }
    )
    assert summary["roles"] == ["Author", "Editor"]
    assert summary["count"] == 5
    assert summary["email"] == "jo@example.com"


def test_summary_handles_missing_roles_and_count() -> None:
    summary = _summary({"id": "1", "name": "Jo"})
    assert summary["roles"] == []
    assert summary["count"] is None
