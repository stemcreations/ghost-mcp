"""Unit tests for the label tool helpers."""

from ghost_mcp.tools.labels import _fields, _summary


def test_fields_keeps_only_provided() -> None:
    assert _fields("VIP", None) == {"name": "VIP"}
    assert _fields("VIP", "vip") == {"name": "VIP", "slug": "vip"}


def test_summary_picks_id_name_slug() -> None:
    assert _summary({"id": "1", "name": "VIP", "slug": "vip", "extra": "x"}) == {
        "id": "1",
        "name": "VIP",
        "slug": "vip",
    }
