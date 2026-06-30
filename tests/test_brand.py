"""Unit tests for brand extraction (pure parsing, no network)."""

from ghost_mcp.vision.structure import _brand_from_sources

HTML = (
    "<html><head>"
    '<meta property="og:image" content="/img/og.png">'
    '<link rel="icon" href="/favicon.ico">'
    "</head><body>"
    '<img class="site-logo" src="/assets/logo.svg" alt="Acme logo">'
    "<h1>Hello</h1></body></html>"
)
CSS = """
:root { --accent: #3a5a40; }
body { font-family: Inter, system-ui, sans-serif; color: #2b2b2b; }
h1, h2 { font-family: "EB Garamond", Georgia, serif; }
a { color: #3a5a40; }
.tag { color: #3a5a40; }
.hero { background: rgb(58, 90, 64); }
.btn { background: #3a5a40; border-radius: 8px; padding: 12px; }
"""


def _brand() -> dict:
    return _brand_from_sources(HTML, CSS, "https://example.com/").to_dict()


def test_palette_is_frequency_ranked_hex() -> None:
    palette = _brand()["palette"]
    # #3a5a40 appears most (hex + rgb forms both normalise to it).
    assert palette[0] == "#3a5a40"
    assert "#2b2b2b" in palette


def test_fonts_distinguish_heading_from_body() -> None:
    fonts = _brand()["fonts"]
    assert fonts["heading"] == "EB Garamond"
    assert fonts["body"] == "Inter"


def test_logo_prefers_a_logo_image_resolved_to_absolute() -> None:
    assert _brand()["logo_url"] == "https://example.com/assets/logo.svg"


def test_button_style_reads_background_and_radius() -> None:
    button = _brand()["button_style"]
    assert button["background"] == "#3a5a40"
    assert button["border_radius"] == "8px"


def test_rgb_colors_are_converted_to_hex() -> None:
    palette = _brand_from_sources("<html></html>", ".x{color: rgb(58, 90, 64)}", "https://e.com/")
    assert "#3a5a40" in palette.to_dict()["palette"]


def test_logo_falls_back_to_og_image_then_icon() -> None:
    no_logo_img = (
        '<html><head><meta property="og:image" content="/og.png"></head><body></body></html>'
    )
    brand = _brand_from_sources(no_logo_img, "", "https://example.com/").to_dict()
    assert brand["logo_url"] == "https://example.com/og.png"
