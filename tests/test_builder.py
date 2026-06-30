"""Unit tests for theme generation (no network)."""

import json

import pytest

from ghost_mcp.errors import ThemeError
from ghost_mcp.theme.builder import ThemeSpec, build_theme
from ghost_mcp.theme.preview import render_theme

REQUIRED_FILES = (
    "package.json",
    "default.hbs",
    "index.hbs",
    "post.hbs",
    "page.hbs",
    "assets/built/screen.css",
)


def test_build_theme_writes_required_files(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="My Cool Theme"), tmp_path)
    assert theme.name == "my-cool-theme"
    for rel in REQUIRED_FILES:
        assert (theme / rel).exists(), rel


def test_package_json_is_valid_and_has_author_email(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="My Cool Theme"), tmp_path)
    pkg = json.loads((theme / "package.json").read_text())
    assert pkg["name"] == "my-cool-theme"
    assert pkg["author"]["email"]  # gscan requires author.email


def test_required_koenig_css_present(tmp_path) -> None:
    css = (
        build_theme(ThemeSpec(name="t"), tmp_path) / "assets" / "built" / "screen.css"
    ).read_text()
    assert ".kg-width-wide" in css
    assert ".kg-width-full" in css


def test_custom_styles_are_appended(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="t", styles="body { color: rebeccapurple; }"), tmp_path)
    assert "rebeccapurple" in (theme / "assets" / "built" / "screen.css").read_text()


def test_block_params_template_is_rejected(tmp_path) -> None:
    spec = ThemeSpec(name="t", templates={"index": "{{#foreach posts as |p|}}{{/foreach}}"})
    with pytest.raises(ThemeError):
        build_theme(spec, tmp_path)


def test_override_without_layout_directive_still_inherits_layout(tmp_path) -> None:
    # An override that omits {{!< default}} must still be wrapped in the layout,
    # otherwise the preview is a bare fragment with no <head> and the CSS never loads.
    spec = ThemeSpec(
        name="t",
        styles="body { color: blue; }",
        templates={"index": '<section class="feed">no layout directive here</section>'},
    )
    theme = build_theme(spec, tmp_path)
    assert (theme / "index.hbs").read_text().startswith("{{!< default}}")
    html = render_theme(theme)["index"]
    assert "<head>" in html
    assert "screen.css" in html


def test_override_keeps_its_own_layout_directive(tmp_path) -> None:
    # An explicit directive (even a non-default layout) is respected, not duplicated.
    spec = ThemeSpec(name="t", templates={"index": "{{!< default}}\n<section>hi</section>"})
    theme = build_theme(spec, tmp_path)
    assert (theme / "index.hbs").read_text().count("{{!< default}}") == 1


def test_generated_theme_is_previewable(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="t", styles="body { color: blue; }"), tmp_path)
    pages = render_theme(theme)
    assert set(pages) == {"index", "post", "page"}
    for html in pages.values():
        assert "{{" not in html
