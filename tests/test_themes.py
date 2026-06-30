"""Unit tests for theme packaging and the Admin API theme helpers (no network)."""

import io
import re
import zipfile

import httpx

from ghost_mcp.admin import themes
from ghost_mcp.admin.client import GhostAdminClient
from ghost_mcp.config import Settings
from ghost_mcp.theme.builder import ThemeSpec, build_theme, package_theme

SETTINGS = Settings(admin_url="https://example.com", staff_token="abc:" + "ab" * 32)


def _rule_body(css: str, selector_regex: str) -> str:
    """Return the declaration block for the first rule whose selector matches."""
    match = re.search(selector_regex + r"\s*\{([^}]*)\}", css)
    return match.group(1) if match else ""


def _client(handler) -> GhostAdminClient:
    return GhostAdminClient(SETTINGS, transport=httpx.MockTransport(handler))


def test_base_css_uses_outer_inner_split_not_chrome_width_caps(tmp_path) -> None:
    # The base stylesheet must NOT cap the structural chrome classes to the reading
    # column -- doing so silently squeezed full-width headers in custom layouts (the
    # "smushed nav" bug). Width capping lives on the .gh-inner wrapper instead.
    theme = build_theme(ThemeSpec(name="My Theme"), tmp_path)
    css = (theme / "assets" / "built" / "screen.css").read_text(encoding="utf-8")

    assert "max-width" not in _rule_body(css, r"\.site-header,\s*\.site-footer")
    assert "max-width" not in _rule_body(css, r"\.post-feed")
    # The reading-column cap moved to the inner wrapper.
    assert "max-width: var(--content-width)" in _rule_body(css, r"\.gh-inner")
    # And the old blanket cap on post/page children is gone.
    assert _rule_body(css, r"\.post > \*,\s*\.page > \*") == ""


def test_default_templates_wrap_content_in_gh_inner(tmp_path) -> None:
    # The default layout/templates supply the .gh-inner wrapper so the default theme
    # still renders as a centred reading column despite the full-width chrome classes.
    theme = build_theme(ThemeSpec(name="My Theme"), tmp_path)
    assert 'class="gh-inner"' in (theme / "default.hbs").read_text(encoding="utf-8")
    assert 'class="gh-inner"' in (theme / "index.hbs").read_text(encoding="utf-8")


def test_package_theme_roots_under_named_folder(tmp_path) -> None:
    src = tmp_path / "mytheme"
    src.mkdir()
    (src / "package.json").write_text('{"name": "mytheme"}')
    (src / "index.hbs").write_text("hello")

    with zipfile.ZipFile(io.BytesIO(package_theme(src))) as archive:
        names = set(archive.namelist())

    assert names == {"mytheme/package.json", "mytheme/index.hbs"}


def test_upload_sends_multipart_and_returns_theme() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/ghost/api/admin/themes/upload/"
        assert request.headers["content-type"].startswith("multipart/form-data")
        return httpx.Response(201, json={"themes": [{"name": "my-theme", "active": False}]})

    theme = themes.upload_theme(_client(handler), b"zip-bytes", filename="my-theme.zip")
    assert theme["name"] == "my-theme"
    assert theme["active"] is False


def test_activate_puts_to_activate_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/ghost/api/admin/themes/my-theme/activate/"
        return httpx.Response(200, json={"themes": [{"name": "my-theme", "active": True}]})

    theme = themes.activate_theme(_client(handler), "my-theme")
    assert theme["active"] is True


def test_download_returns_raw_zip_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ghost/api/admin/themes/source/download/"
        return httpx.Response(200, content=b"PK\x03\x04 zip-bytes")

    data = themes.download_theme(_client(handler), "source")
    assert data.startswith(b"PK")
