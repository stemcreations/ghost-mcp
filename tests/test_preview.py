"""Unit tests for the local theme previewer (rendering only, no server)."""

from pathlib import Path

from ghost_mcp.theme.preview import render_theme

FIXTURE = Path(__file__).parent / "fixtures" / "ghost-mcp-smoke-test"


def test_renders_home_post_and_page() -> None:
    pages = render_theme(FIXTURE)
    assert set(pages) == {"index", "post", "page"}


def test_layout_applied_and_assets_resolved() -> None:
    html = render_theme(FIXTURE)["index"]
    assert "<!DOCTYPE html>" in html  # default.hbs layout wrapped the page
    assert "/assets/built/screen.css" in html  # asset helper resolved
    assert "Welcome to the preview" in html  # sample posts rendered via foreach


def test_post_content_is_rendered_unescaped() -> None:
    html = render_theme(FIXTURE)["post"]
    assert "<p>This is sample post content" in html  # {{content}} emitted raw HTML


def test_no_unrendered_handlebars() -> None:
    for html in render_theme(FIXTURE).values():
        assert "{{" not in html
