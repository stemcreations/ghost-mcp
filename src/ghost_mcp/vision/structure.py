"""Fetch a Ghost blog's rendered HTML and CSS so a model can target real selectors.

Unlike the rest of the package this module needs no authentication: it requests
the public page exactly as a browser would, then the stylesheets that page links
to. The result is trimmed for size — a full page plus theme CSS is large, and most
of it (editor-card styles, inline scripts, body text) adds nothing to a styling
decision.

The markup is returned as a *skeleton*: an indented outline of tags with their ids
and classes, text and scripts stripped. That is what lets the model write CSS
against selectors that actually exist instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

#: Elements whose contents carry no styling signal; dropped from the skeleton.
_SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "template", "link", "meta"}

#: Stylesheets matching these fragments are Ghost's editor-card styles, which only
#: apply to posts using Koenig cards. Skipped unless such cards appear on the page.
_CARD_CSS_MARKERS = ("cards.min.css", "/public/cards")


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
    """
    root = blog_url if blog_url.endswith("/") else blog_url + "/"
    page_url = urljoin(root, path.lstrip("/"))
    response = httpx.get(page_url, timeout=timeout, follow_redirects=True)
    soup = BeautifulSoup(response.text, "html.parser")

    class_names = _collect_class_names(soup)
    uses_cards = any(name.startswith("kg-") for name in class_names)
    skeleton = _build_skeleton(soup.body or soup)

    stylesheets: list[Stylesheet] = []
    for href in _stylesheet_hrefs(soup):
        if not include_card_css and not uses_cards and _is_card_css(href):
            continue
        sheet_url = urljoin(str(response.url), href)
        try:
            css = httpx.get(sheet_url, timeout=timeout, follow_redirects=True).text
        except httpx.HTTPError:
            continue
        stylesheets.append(Stylesheet(url=sheet_url, css=css))

    return ThemeStructure(
        url=str(response.url),
        status_code=response.status_code,
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
