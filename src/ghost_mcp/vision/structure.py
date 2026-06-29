"""Fetch a Ghost blog's rendered HTML and CSS so a model can target real selectors.

Unlike the rest of the package this module needs no authentication: it requests
the public page exactly as a browser would, then the stylesheets that page links
to. The result is trimmed for size — a full page plus theme CSS is large, and most
of it (editor-card styles, inline scripts, body text) adds nothing to a styling
decision.

Because the URL to fetch is caller-supplied, every request is guarded against SSRF:
only ``http``/``https`` is allowed, private/loopback/link-local/metadata hosts are
refused (including across redirects), and the response size is capped.
"""

from __future__ import annotations

import ipaddress
import socket
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


def _fetch(url: str, *, timeout: float) -> tuple[str, int, str]:
    """Fetch a public URL safely, returning ``(final_url, status_code, text)``.

    Validates every redirect hop, so a public URL can't bounce the request to an
    internal host, and stops reading once the response exceeds the size cap.
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
            data = bytearray()
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > _MAX_RESPONSE_BYTES:
                    raise GhostError(f"response exceeds {_MAX_RESPONSE_BYTES} bytes")
            text = data.decode(response.encoding or "utf-8", errors="replace")
            return str(response.url), response.status_code, text


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
