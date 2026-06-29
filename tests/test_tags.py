"""Unit tests for the tag tool helpers."""

from ghost_mcp.tools.tags import _fields, _summary


def test_fields_keeps_only_provided() -> None:
    assert _fields("News", None, None, None, None, None) == {"name": "News"}


def test_fields_includes_all_provided() -> None:
    assert _fields("News", "desc", "news", "MT", "MD", "img.png") == {
        "name": "News",
        "description": "desc",
        "slug": "news",
        "meta_title": "MT",
        "meta_description": "MD",
        "feature_image": "img.png",
    }


def test_summary_flattens_post_count() -> None:
    summary = _summary(
        {"id": "1", "name": "News", "slug": "news", "description": "d", "count": {"posts": 3}}
    )
    assert summary == {"id": "1", "name": "News", "slug": "news", "description": "d", "count": 3}
