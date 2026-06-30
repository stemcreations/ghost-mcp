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


# --- navigation extraction ------------------------------------------------------

NAV_HTML = (
    "<html><body>"
    "<header>"
    '<a href="/"><img src="/logo.svg" alt="Acme"></a>'  # logo link -> skipped
    "<nav>"
    '<a href="/">Home</a>'
    '<a href="/">Home</a>'  # duplicate (e.g. mobile menu) -> deduped
    '<a href="/campaigns">Campaigns</a>'
    '<a href="https://partner.example/x">Partner</a>'  # external content link
    '<a href="/login">Login</a>'  # membership
    '<a href="/signup">Sign Up</a>'  # membership
    "</nav>"
    "</header>"
    "<footer>"
    '<a href="/about">About</a>'
    '<a href="https://startplaying.games/gm/abc">StartPlaying</a>'
    '<a href="/account">My Account</a>'  # membership in footer
    "</footer>"
    "</body></html>"
)


def _nav() -> dict:
    return _brand_from_sources(NAV_HTML, "", "https://example.com/").to_dict()["navigation"]


def test_navigation_primary_holds_deduped_header_content_links() -> None:
    primary = _nav()["primary"]
    assert [link["label"] for link in primary] == ["Home", "Campaigns", "Partner"]


def test_navigation_secondary_holds_footer_content_links() -> None:
    secondary = _nav()["secondary"]
    assert [link["label"] for link in secondary] == ["About", "StartPlaying"]


def test_navigation_membership_links_are_split_out_of_the_menus() -> None:
    nav = _nav()
    membership = [link["label"] for link in nav["membership"]]
    assert membership == ["Login", "Sign Up", "My Account"]
    # ...and none of them leak into the content menus.
    in_menus = {link["label"] for link in nav["primary"] + nav["secondary"]}
    assert in_menus.isdisjoint({"Login", "Sign Up", "My Account"})


def test_navigation_flags_external_links() -> None:
    by_label = {link["label"]: link for link in _nav()["primary"] + _nav()["secondary"]}
    assert by_label["Home"]["external"] is False
    assert by_label["Partner"]["external"] is True
    assert by_label["StartPlaying"]["external"] is True


def test_navigation_is_empty_when_no_header_or_footer() -> None:
    nav = _brand_from_sources("<html><body><p>hi</p></body></html>", "", "https://e.com/")
    assert nav.to_dict()["navigation"] == {"primary": [], "secondary": [], "membership": []}
