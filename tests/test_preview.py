"""Unit tests for the local theme previewer (rendering only, no server)."""

from pathlib import Path

import pytest

from ghost_mcp.errors import ThemeError
from ghost_mcp.theme.preview import default_sample, render_theme

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


def test_layout_directive_cannot_traverse_outside_theme(tmp_path) -> None:
    # A file outside the theme dir that a malicious layout directive must NOT read.
    (tmp_path / "secret.hbs").write_text("TRAVERSAL_SECRET_MARKER")
    theme = tmp_path / "mytheme"
    theme.mkdir()
    (theme / "package.json").write_text('{"name": "mytheme"}')
    (theme / "default.hbs").write_text("<html>{{{body}}}</html>")
    (theme / "index.hbs").write_text("{{!< ../secret}}\n<p>body</p>")
    (theme / "post.hbs").write_text("{{#post}}{{title}}{{/post}}")
    (theme / "page.hbs").write_text("{{#post}}{{title}}{{/post}}")

    html = render_theme(theme)["index"]
    assert "TRAVERSAL_SECRET_MARKER" not in html  # traversal blocked, no file read


def _minimal_theme(tmp_path, index_body: str) -> Path:
    theme = tmp_path / "t"
    theme.mkdir()
    (theme / "package.json").write_text('{"name": "t"}')
    (theme / "default.hbs").write_text("{{{body}}}")
    (theme / "index.hbs").write_text("{{!< default}}" + index_body)
    (theme / "post.hbs").write_text("{{#post}}{{title}}{{/post}}")
    (theme / "page.hbs").write_text("{{#post}}{{title}}{{/post}}")
    return theme


def test_foreach_honours_limit_kwarg(tmp_path) -> None:
    # Ghost's foreach limit= hash arg must not crash the previewer, and should
    # actually narrow the loop: 3 sample posts, limit="2" -> two rendered.
    theme = _minimal_theme(tmp_path, '{{#foreach posts limit="2"}}[{{title}}]{{/foreach}}')
    html = render_theme(theme)["index"]
    assert html.count("[") == 2


def test_foreach_exposes_loop_position_data(tmp_path) -> None:
    # Ghost's foreach exposes @index/@number/@first/@last/@even/@odd for loop-position
    # styling. The previewer must surface them too, or themes that style by position
    # render blank locally while working live. Three sample posts -> deterministic data.
    body = (
        "{{#foreach posts}}"
        "[{{@index}}|{{@number}}|{{#if @first}}F{{/if}}|"
        "{{#if @last}}L{{/if}}|{{#if @even}}E{{/if}}|{{#if @odd}}O{{/if}}]"
        "{{/foreach}}"
    )
    theme = _minimal_theme(tmp_path, body)
    html = render_theme(theme)["index"]
    # Fields are [index|number|first|last|even|odd].
    assert "[0|1|F|||O]" in html  # post 1: first, odd
    assert "[1|2|||E|]" in html  # post 2: even
    assert "[2|3||L||O]" in html  # post 3: last, odd


def test_unpreviewable_template_raises_clear_error(tmp_path) -> None:
    # A 'from=' loop arg can't be compiled by pybars3 ('from' is a Python keyword).
    # Rendering such a theme directly should fail with a clear ThemeError, not a raw
    # SyntaxError leaking from the compiler.
    theme = _minimal_theme(tmp_path, '{{#foreach posts from="2"}}{{title}}{{/foreach}}')
    with pytest.raises(ThemeError):
        render_theme(theme)


def test_unknown_helper_with_kwargs_degrades_instead_of_crashing(tmp_path) -> None:
    # {{date … format="MMM D, YYYY"}} and other unimplemented helpers used to crash
    # the whole preview; now they render empty and the rest of the page still renders.
    theme = _minimal_theme(tmp_path, 'X{{date published_at format="MMM D, YYYY"}}Y')
    html = render_theme(theme)["index"]
    assert "XY" in html  # helper rendered empty, surrounding markup intact


def test_foreach_renders_else_block_on_empty_feed(tmp_path) -> None:
    theme = tmp_path / "t"
    theme.mkdir()
    (theme / "package.json").write_text('{"name": "t"}')
    (theme / "default.hbs").write_text("{{{body}}}")
    (theme / "index.hbs").write_text("{{!< default}}{{#foreach posts}}ITEM{{else}}NONE{{/foreach}}")
    (theme / "post.hbs").write_text("{{#post}}{{title}}{{/post}}")
    (theme / "page.hbs").write_text("{{#post}}{{title}}{{/post}}")

    sample = default_sample()
    sample["posts"] = []
    html = render_theme(theme, sample=sample)["index"]
    assert "NONE" in html
    assert "ITEM" not in html
