"""Unit tests for the member tool helpers."""

from ghost_mcp.tools.members import _fields, _summary


def test_fields_keeps_only_provided() -> None:
    assert _fields("a@b.com", None, None, None, None, None) == {"email": "a@b.com"}


def test_fields_maps_labels_and_newsletters_to_objects() -> None:
    fields = _fields("a@b.com", "Jamie", "vip note", ["VIP", "Beta"], ["nid1", "nid2"], True)
    assert fields["labels"] == [{"name": "VIP"}, {"name": "Beta"}]
    assert fields["newsletters"] == [{"id": "nid1"}, {"id": "nid2"}]
    assert fields["subscribed"] is True


def test_fields_allows_unsubscribe_false() -> None:
    # subscribed=False must be sent (not dropped as falsy).
    assert _fields(None, None, None, None, None, False) == {"subscribed": False}


def test_summary_flattens_labels_and_newsletters() -> None:
    summary = _summary(
        {
            "id": "1",
            "email": "a@b.com",
            "status": "paid",
            "subscribed": True,
            "labels": [{"name": "VIP"}],
            "newsletters": [{"name": "Weekly"}],
        }
    )
    assert summary["labels"] == ["VIP"]
    assert summary["newsletters"] == ["Weekly"]
    assert summary["status"] == "paid"
