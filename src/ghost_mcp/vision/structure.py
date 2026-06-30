"""Fetch a Ghost blog's rendered HTML and CSS so a model can target real selectors.

Unlike the rest of the package this module needs no authentication: it requests
the public page exactly as a browser would, then the stylesheets that page links
to. The result is trimmed for size: a full page plus theme CSS is large, and most
of it (editor-card styles, inline scripts, body text) adds nothing to a styling
decision.

Because the URL to fetch is caller-supplied, every request is guarded against SSRF:
only ``http``/``https`` is allowed, private/loopback/link-local/metadata hosts are
refused (including across redirects), and the response size is capped.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from ghost_mcp.errors import GhostError

#: Elements whose contents carry no styling signal; dropped from the skeleton.
_SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "template", "link", "meta"}

#: Stylesheets matching these fragments are Ghost's editor-card styles, which only
#: apply to posts using Koenig cards. Skipped unless such cards appear on the page.
_CARD_CSS_MARKERS = ("cards.min.css", "/public/cards")

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_RESPONSE_BYTES = 5_000_000
_MAX_REDIRECTS = 5


@dataclass
class Stylesheet:
    """A single stylesheet fetched from the page."""

    url: str
    css: str

    @property
    def byte_size(self) -> int:
        return len(self.css)


@dataclass
class ThemeStructure:
    """The structural and stylistic surface of a rendered blog page."""

    url: str
    status_code: int
    skeleton: str
    class_names: list[str]
    stylesheets: list[Stylesheet] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable view for returning from an MCP tool."""
        return {
            "url": self.url,
            "status_code": self.status_code,
            "skeleton": self.skeleton,
            "class_names": self.class_names,
            "stylesheets": {sheet.url: sheet.css for sheet in self.stylesheets},
        }


def _host_is_blocked(host: str) -> bool:
    """True if a hostname resolves to a private/loopback/link-local/reserved address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True  # unresolvable → refuse
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def _validate_public_url(url: str) -> None:
    """Refuse non-http(s) schemes and private/unresolvable hosts (SSRF guard)."""
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise GhostError(f"refusing to fetch non-http(s) URL: {url!r}")
    if not parts.hostname or _host_is_blocked(parts.hostname):
        raise GhostError(f"refusing to fetch a private or unresolvable host: {url!r}")


@contextmanager
def _open_public_stream(url: str, *, timeout: float) -> Iterator[httpx.Response]:
    """Open an SSRF-guarded streaming GET and yield the final response.

    Validates the URL and every redirect hop, so a public URL can't bounce the
    request to an internal host (redirects are followed manually). The body is
    streamed, so the caller must read it before the context exits.
    """
    redirects = 0
    while True:
        _validate_public_url(url)
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                redirects += 1
                if not location or redirects > _MAX_REDIRECTS:
                    raise GhostError(f"too many or invalid redirects fetching {url!r}")
                url = urljoin(url, location)
                continue
            yield response
            return


def _read_capped(response: httpx.Response) -> bytes:
    """Read a streamed response body, stopping once it exceeds the size cap."""
    data = bytearray()
    for chunk in response.iter_bytes():
        data += chunk
        if len(data) > _MAX_RESPONSE_BYTES:
            raise GhostError(f"response exceeds {_MAX_RESPONSE_BYTES} bytes")
    return bytes(data)


def _fetch(url: str, *, timeout: float) -> tuple[str, int, str]:
    """Fetch a public URL safely, returning ``(final_url, status_code, text)``."""
    with _open_public_stream(url, timeout=timeout) as response:
        data = _read_capped(response)
        text = data.decode(response.encoding or "utf-8", errors="replace")
        return str(response.url), response.status_code, text


def fetch_public_bytes(url: str, *, timeout: float = 30.0) -> tuple[str, bytes, str | None]:
    """Fetch a public URL's raw bytes under the SSRF guard.

    Returns ``(final_url, body, content_type)``. Like :func:`_fetch` but returns
    undecoded bytes, for binary resources such as images that must not be text-decoded.

    Raises:
        GhostError: if the URL (or a redirect target) is non-http(s), points at a
            private/unresolvable host, or the response exceeds the size cap.
    """
    with _open_public_stream(url, timeout=timeout) as response:
        return str(response.url), _read_capped(response), response.headers.get("content-type")


def fetch_theme_structure(
    blog_url: str,
    path: str = "/",
    *,
    include_card_css: bool = False,
    timeout: float = 30.0,
) -> ThemeStructure:
    """Fetch a rendered page and its linked CSS.

    Args:
        blog_url: The public base URL of the blog, e.g. ``https://example.com``.
        path: The page to inspect. The homepage and a single post use different
            templates, so pass e.g. ``/`` or ``/my-post/`` accordingly.
        include_card_css: Include Ghost's editor-card stylesheet even when the page
            uses no cards. Off by default to save space.
        timeout: Per-request timeout in seconds.

    Returns:
        A :class:`ThemeStructure` describing the page's markup skeleton, the class
        names in use, and the relevant stylesheets.

    Raises:
        GhostError: if the URL (or a redirect target) is non-http(s), points at a
            private/unresolvable host, or the response is too large.
    """
    root = blog_url if blog_url.endswith("/") else blog_url + "/"
    page_url = urljoin(root, path.lstrip("/"))
    final_url, status_code, text = _fetch(page_url, timeout=timeout)
    soup = BeautifulSoup(text, "html.parser")

    class_names = _collect_class_names(soup)
    uses_cards = any(name.startswith("kg-") for name in class_names)
    skeleton = _build_skeleton(soup.body or soup)

    stylesheets: list[Stylesheet] = []
    for href in _stylesheet_hrefs(soup):
        if not include_card_css and not uses_cards and _is_card_css(href):
            continue
        sheet_url = urljoin(final_url, href)
        try:
            _, _, css = _fetch(sheet_url, timeout=timeout)
        except (httpx.HTTPError, GhostError):
            continue
        stylesheets.append(Stylesheet(url=sheet_url, css=css))

    return ThemeStructure(
        url=final_url,
        status_code=status_code,
        skeleton=skeleton,
        class_names=class_names,
        stylesheets=stylesheets,
    )


def _collect_class_names(soup: BeautifulSoup) -> list[str]:
    names: set[str] = set()
    for element in soup.find_all(class_=True):
        names.update(element.get("class", []))
    return sorted(names)


def _stylesheet_hrefs(soup: BeautifulSoup) -> list[str]:
    hrefs: list[str] = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            hrefs.append(href)
    return hrefs


def _is_card_css(href: str) -> bool:
    return any(marker in href for marker in _CARD_CSS_MARKERS)


def _build_skeleton(root: Tag, *, max_lines: int = 400) -> str:
    """Render an indented tag/class outline with text and noise stripped."""
    lines: list[str] = []

    def visit(node: Tag, depth: int) -> None:
        for child in node.children:
            if not isinstance(child, Tag) or child.name in _SKIP_TAGS:
                continue
            if len(lines) >= max_lines:
                return
            lines.append("  " * depth + _describe(child))
            visit(child, depth + 1)

    visit(root, 0)
    if len(lines) >= max_lines:
        lines.append("… (truncated)")
    return "\n".join(lines)


def _describe(tag: Tag) -> str:
    descriptor = tag.name
    element_id = tag.get("id")
    if element_id:
        descriptor += f"#{element_id}"
    classes = tag.get("class")
    if classes:
        descriptor += "." + ".".join(classes)
    return descriptor


# --- brand extraction ------------------------------------------------------

#: A CSS rule: ``selector { declarations }``.
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_RGB_COLOR = re.compile(r"rgba?\(([^)]*)\)", re.IGNORECASE)
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;{}]+)", re.IGNORECASE)
#: Selectors that style headings/titles, used to tell heading font from body font.
_HEADING_SELECTOR = re.compile(r"\b(h[1-6]|heading|title|display)\b", re.IGNORECASE)
#: Selectors that look like buttons, used to read the brand's button style.
_BUTTON_SELECTOR = re.compile(
    r"\.btn\b|\.button\b|\bbutton\b|\[class[*^$|~]?=[\"']?button", re.IGNORECASE
)


@dataclass
class Brand:
    """A site's brand tokens, extracted from its rendered HTML and CSS."""

    url: str
    palette: list[str]
    fonts: dict[str, str | None]
    logo_url: str | None
    button_style: dict[str, str]

    def to_dict(self) -> dict:
        """Return a JSON-serialisable view for returning from an MCP tool."""
        return {
            "url": self.url,
            "palette": self.palette,
            "fonts": self.fonts,
            "logo_url": self.logo_url,
            "button_style": self.button_style,
        }


def _normalize_hex(value: str) -> str | None:
    """Coerce a hex colour to lowercase ``#rrggbb`` (alpha dropped); None if invalid."""
    digits = value.lstrip("#").lower()
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits[:3])
    elif len(digits) in (6, 8):
        digits = digits[:6]
    else:
        return None
    return f"#{digits}"


def _rgb_to_hex(body: str) -> str | None:
    """Convert the inside of an ``rgb()``/``rgba()`` to ``#rrggbb``; None if malformed."""
    nums = re.findall(r"[\d.]+", body)
    if len(nums) < 3:
        return None
    r, g, b = (max(0, min(255, round(float(n)))) for n in nums[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _collect_palette(css: str, limit: int = 6) -> list[str]:
    """Rank the colours used in the CSS by frequency and return the top few."""
    counts: Counter[str] = Counter()
    for match in _HEX_COLOR.findall(css):
        if (hexed := _normalize_hex(match)) is not None:
            counts[hexed] += 1
    for body in _RGB_COLOR.findall(css):
        if (hexed := _rgb_to_hex(body)) is not None:
            counts[hexed] += 1
    return [color for color, _ in counts.most_common(limit)]


def _first_family(declaration: str) -> str | None:
    """The first concrete family in a ``font-family`` stack (quotes stripped)."""
    family = declaration.split(",")[0].strip().strip("'\"")
    return family or None


def _collect_fonts(rules: list[tuple[str, str]]) -> dict[str, str | None]:
    """Guess the heading and body font families from the parsed CSS rules."""
    body_counts: Counter[str] = Counter()
    heading: str | None = None
    for selector, declarations in rules:
        match = _FONT_FAMILY.search(declarations)
        if not match:
            continue
        family = _first_family(match.group(1))
        if family is None:
            continue
        body_counts[family] += 1
        if heading is None and _HEADING_SELECTOR.search(selector):
            heading = family
    body = body_counts.most_common(1)[0][0] if body_counts else None
    return {"heading": heading or body, "body": body}


def _find_logo(soup: BeautifulSoup, base_url: str) -> str | None:
    """Find the site's logo: a logo <img>, else og:image, else a touch/icon link."""
    for img in soup.find_all("img"):
        hint = " ".join(
            filter(None, [img.get("alt", ""), " ".join(img.get("class", [])), img.get("src", "")])
        ).lower()
        if "logo" in hint and img.get("src"):
            return urljoin(base_url, img["src"])
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return urljoin(base_url, og["content"])
    for rel in ("apple-touch-icon", "icon"):
        link = soup.find("link", rel=lambda v, r=rel: bool(v) and r in v)
        if link and link.get("href"):
            return urljoin(base_url, link["href"])
    return None


def _button_style(rules: list[tuple[str, str]]) -> dict[str, str]:
    """Read the brand's button look (background + radius) from the first button rule."""
    for selector, declarations in rules:
        if not _BUTTON_SELECTOR.search(selector):
            continue
        style: dict[str, str] = {}
        if bg := re.search(r"background(?:-color)?\s*:\s*([^;{}]+)", declarations, re.IGNORECASE):
            style["background"] = bg.group(1).strip()
        if br := re.search(r"border-radius\s*:\s*([^;{}]+)", declarations, re.IGNORECASE):
            style["border_radius"] = br.group(1).strip()
        if style:
            return style
    return {}


def _brand_from_sources(html: str, css: str, base_url: str) -> Brand:
    """Extract brand tokens from a page's HTML and concatenated CSS (no network).

    Pure so it can be unit-tested without fetching anything.
    """
    rules = [(sel.strip(), decl) for sel, decl in _CSS_RULE.findall(css)]
    soup = BeautifulSoup(html, "html.parser")
    return Brand(
        url=base_url,
        palette=_collect_palette(css),
        fonts=_collect_fonts(rules),
        logo_url=_find_logo(soup, base_url),
        button_style=_button_style(rules),
    )


def extract_brand(site_url: str, path: str = "/", *, timeout: float = 30.0) -> Brand:
    """Fetch a public site and distil its brand tokens (palette, fonts, logo, button).

    Step one of any theming job: instead of hand-reading a stylesheet, this returns
    clean tokens to match. Fetches the page plus its linked and inline CSS, under the
    same SSRF guards as :func:`fetch_theme_structure` (http(s) only, no private hosts).

    Args:
        site_url: The public site to inspect, e.g. ``https://example.com``.
        path: The page to read; the homepage usually carries the brand.
        timeout: Per-request timeout in seconds.

    Returns:
        A :class:`Brand` with a frequency-ranked colour ``palette``, best-guess
        ``fonts`` (heading/body), a ``logo_url``, and a ``button_style``.

    Raises:
        GhostError: if the URL (or a redirect target) is non-http(s), points at a
            private/unresolvable host, or the response is too large.
    """
    root = site_url if site_url.endswith("/") else site_url + "/"
    page_url = urljoin(root, path.lstrip("/"))
    final_url, _status, html = _fetch(page_url, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    css_parts = [tag.get_text() for tag in soup.find_all("style")]
    for href in _stylesheet_hrefs(soup):
        sheet_url = urljoin(final_url, href)
        try:
            _, _, css = _fetch(sheet_url, timeout=timeout)
        except (httpx.HTTPError, GhostError):
            continue
        css_parts.append(css)

    return _brand_from_sources(html, "\n".join(css_parts), final_url)
