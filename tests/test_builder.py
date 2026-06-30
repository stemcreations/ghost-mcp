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


def test_package_json_declares_card_assets_and_image_sizes(tmp_path) -> None:
    # card_assets lets Ghost style Koenig cards on the live blog; image_sizes powers
    # responsive {{img_url size=…}}. Both are part of the Ghost compatibility surface.
    pkg = json.loads((build_theme(ThemeSpec(name="t"), tmp_path) / "package.json").read_text())
    assert pkg["config"]["card_assets"] is True
    assert set(pkg["config"]["image_sizes"]) == {"xs", "s", "m", "l", "xl", "xxl"}


def test_required_koenig_css_present(tmp_path) -> None:
    css = (
        build_theme(ThemeSpec(name="t"), tmp_path) / "assets" / "built" / "screen.css"
    ).read_text()
    assert ".kg-width-wide" in css
    assert ".kg-width-full" in css


def test_base_css_follows_ghost_conventions(tmp_path) -> None:
    # Design tokens on :root, consumption of Ghost's injected accent + font-picker
    # variables, and the grid "canvas" that lets Koenig cards break out.
    css = (
        build_theme(ThemeSpec(name="t"), tmp_path) / "assets" / "built" / "screen.css"
    ).read_text()
    assert "var(--ghost-accent-color" in css
    assert "var(--gh-font-body" in css
    assert "--content-width" in css
    assert "grid-template-columns" in css


def test_custom_styles_are_appended(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="t", styles="body { color: rebeccapurple; }"), tmp_path)
    assert "rebeccapurple" in (theme / "assets" / "built" / "screen.css").read_text()


def test_block_params_template_is_rejected(tmp_path) -> None:
    spec = ThemeSpec(name="t", templates={"index": "{{#foreach posts as |p|}}{{/foreach}}"})
    with pytest.raises(ThemeError):
        build_theme(spec, tmp_path)


def test_from_loop_arg_is_rejected(tmp_path) -> None:
    # 'from=' can't be compiled by the previewer (pybars3 emits invalid Python since
    # 'from' is a keyword), so the builder rejects it at build time with a clear error.
    spec = ThemeSpec(name="t", templates={"index": '{{#foreach posts from="2"}}{{/foreach}}'})
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


def test_default_layout_can_be_overridden(tmp_path) -> None:
    # The default.hbs layout itself is overridable; its content is used verbatim
    # (no {{!< default}} injection, since the layout doesn't inherit itself), and the
    # generated theme still previews.
    custom = (
        "<!DOCTYPE html><html><head>{{ghost_head}}</head>"
        '<body class="custom-shell">{{{body}}}</body></html>'
    )
    theme = build_theme(ThemeSpec(name="t", templates={"default": custom}), tmp_path)
    assert (theme / "default.hbs").read_text() == custom
    assert "custom-shell" in render_theme(theme)["index"]


def test_default_layout_override_without_body_is_rejected(tmp_path) -> None:
    # A layout with no {{{body}}} would render every page empty, so it's rejected.
    spec = ThemeSpec(name="t", templates={"default": "<html><head></head><body></body></html>"})
    with pytest.raises(ThemeError):
        build_theme(spec, tmp_path)


def test_generated_theme_is_previewable(tmp_path) -> None:
    theme = build_theme(ThemeSpec(name="t", styles="body { color: blue; }"), tmp_path)
    pages = render_theme(theme)
    assert set(pages) == {"index", "post", "page"}
    for html in pages.values():
        assert "{{" not in html
