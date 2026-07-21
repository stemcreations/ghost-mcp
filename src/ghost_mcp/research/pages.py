"""Read the structure of the pages that already rank for a query.

What a brief needs from a competitor is not its prose but its *shape*: the H2/H3
outline, roughly how long it is, and whether it carries a pricing table or an FAQ.
That is what this module extracts.

These URLs come from a search engine, i.e. they are chosen by a third party rather
than the user, so every fetch reuses the vision package's SSRF guard
(:func:`~ghost_mcp.vision.structure.fetch_public_bytes`): http(s) only, private and
unresolvable hosts refused across redirects, and a hard cap on the response size.
Pages are fetched concurrently because a serial crawl of five sites is several
seconds of dead time inside a single tool call.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ghost_mcp.vision.structure import fetch_public_bytes

#: Elements that surround the content without being part of it.
_CHROME_TAGS = ["script", "style", "nav", "footer", "aside", "noscript", "form"]

#: Headings that are site furniture rather than content structure.
_JUNK_HEADING = re.compile(
    r"^(related|share|comments?|newsletter|subscribe|follow us|categories|"
    r"recent posts|popular posts|you might also|more from|about( the)? author|"
    r"leave a reply|table of contents|sidebar|menu|navigation|footer|search|"
    r"tags?|advertisement|sponsored)\b",
    re.I,
)

_PRICE_HINT = re.compile(r"\$|\bprice|pricing|per month|per session|/mo\b|\bcost", re.I)
_FAQ_HINT = re.compile(r"frequently asked|\bFAQs?\b", re.I)

#: Long strings are almost never real headings; they're mis-tagged paragraphs.
_MAX_HEADING_CHARS = 140


@dataclass
class RankingPage:
    """The structural summary of one page that ranks for a query."""

    url: str
    ok: bool = False
    error: str | None = None
    title: str = ""
    headings: list[tuple[str, str]] = field(default_factory=list)
    word_count: int = 0
    tables: int = 0
    has_price_table: bool = False
    has_faq: bool = False
    lists: int = 0

    def to_dict(self) -> dict:
        """Return a JSON-serialisable view for returning from an MCP tool."""
        return {
            "url": self.url,
            "ok": self.ok,
            "error": self.error,
            "title": self.title,
            "headings": [{"level": level, "text": text} for level, text in self.headings],
            "word_count": self.word_count,
            "tables": self.tables,
            "has_price_table": self.has_price_table,
            "has_faq": self.has_faq,
            "lists": self.lists,
        }


def normalize(text: str) -> str:
    """Collapse runs of whitespace and trim."""
    return re.sub(r"\s+", " ", text or "").strip()


def _decode(body: bytes, content_type: str | None) -> str:
    """Decode a response body using the charset the server declared, if any."""
    charset = "utf-8"
    if content_type and "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def parse_page(url: str, html: str) -> RankingPage:
    """Extract structure from already-fetched HTML.

    Pure, so the parsing rules can be tested without touching the network.
    """
    page = RankingPage(url=url, ok=True)
    soup = BeautifulSoup(html, "html.parser")

    page.title = normalize(soup.title.get_text()) if soup.title else ""

    for chrome in soup(_CHROME_TAGS):
        chrome.decompose()

    for tag in soup.find_all(["h2", "h3"]):
        text = normalize(tag.get_text())
        if not text or len(text) > _MAX_HEADING_CHARS or _JUNK_HEADING.match(text):
            continue
        page.headings.append((tag.name, text))

    body = soup.find("article") or soup.find("main") or soup.body or soup
    body_text = body.get_text(" ")
    page.word_count = len(re.findall(r"\b\w+\b", body_text))

    tables = soup.find_all("table")
    page.tables = len(tables)
    page.has_price_table = any(_PRICE_HINT.search(table.get_text()) for table in tables)
    page.lists = len(soup.find_all(["ul", "ol"]))
    page.has_faq = bool(_FAQ_HINT.search(body_text))
    return page


def fetch_page(url: str, *, timeout: float = 20.0) -> RankingPage:
    """Fetch one ranking page and summarise its structure.

    Never raises for a single bad page: a failure is recorded on the returned
    :class:`RankingPage` as ``ok=False`` plus an ``error``, so one dead competitor
    can't sink an entire brief.
    """
    try:
        final_url, body, content_type = fetch_public_bytes(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - one bad URL must not abort the crawl
        return RankingPage(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
    return parse_page(final_url, _decode(body, content_type))


def fetch_pages(
    urls: list[str], *, timeout: float = 20.0, max_workers: int = 5
) -> list[RankingPage]:
    """Fetch several ranking pages concurrently, preserving input order."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as pool:
        return list(pool.map(lambda url: fetch_page(url, timeout=timeout), urls))
