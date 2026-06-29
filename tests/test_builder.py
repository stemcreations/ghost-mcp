"""Unit tests for theme generation (no network)."""

import json

import pytest

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
    with pytest.raises(ValueError):
        build_theme(spec, tmp_path)


def test_generated_theme_is_previewable(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="t", styles="body { color: blue; }"), tmp_path)
    pages = render_theme(theme)
    assert set(pages) == {"index", "post", "page"}
    for html in pages.values():
        assert "{{" not in html
