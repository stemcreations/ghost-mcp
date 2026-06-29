"""Render a Ghost theme to static HTML for local preview.

Ghost normally renders themes server-side with its own Handlebars helpers and live
data, so a perfectly faithful render needs a running Ghost. This module produces an
approximate *local* render — accurate for layout and styling, with sample content
and stubbed helpers — so a theme can be checked in a browser before it is activated
on the real site.

It covers the home, post, and page templates, emulates Ghost's ``{{!< default}}``
layout inheritance, and stubs the most common theme helpers. Real site/branding
settings can be supplied via ``sample`` to make the preview brand-accurate; by
default a neutral sample is used.
"""

from __future__ import annotations

import functools
import http.server
import re
import shutil
import threading
from pathlib import Path

from pybars import Compiler

try:  # lets helpers emit raw HTML (e.g. post content) without escaping
    from pybars import strlist
except ImportError:  # pragma: no cover - depends on pybars internals
    strlist = None

_LAYOUT_DIRECTIVE = re.compile(r"\{\{!<\s*([\w./-]+)\s*\}\}")
_compiler = Compiler()

#: Templates rendered for preview, each with the context Ghost would give it.
_PREVIEW_PAGES = ("index", "post", "page")


def _safe(html: str):
    """Wrap HTML so pybars3 emits it unescaped from a helper."""
    return strlist([html]) if strlist is not None else html


def default_sample() -> dict:
    """A neutral set of sample data to fill the templates."""
    posts = [
        {
            "title": "Welcome to the preview",
            "url": "/welcome/",
            "excerpt": "A sample post used to fill out the layout while you design.",
            "feature_image": None,
            "html": "<p>This is sample post content rendered by the local preview.</p>",
        },
        {
            "title": "A second sample post",
            "url": "/second/",
            "excerpt": "More sample text so the post feed has something to show.",
            "feature_image": None,
            "html": "<p>More sample body copy for the second post.</p>",
        },
        {
            "title": "A third sample post",
            "url": "/third/",
            "excerpt": "Even more sample text to exercise the feed styling.",
            "feature_image": None,
            "html": "<p>Sample body copy for the third post.</p>",
        },
    ]
    site = {
        "title": "Preview Site",
        "description": "A local preview of your Ghost theme.",
        "locale": "en",
        "accent_color": "#15171a",
        "logo": None,
        "icon": None,
        "url": "/",
    }
    return {
        "site": site,
        "custom": {},
        "posts": posts,
        "post": posts[0],
        "page": {**posts[0], "title": "Sample Page"},
    }


def _base_context(sample: dict) -> dict:
    """Context shared by every template.

    Holds the ``@`` data globals plus Ghost's bare-name helpers. pybars3 only
    invokes a helper when it takes arguments or a block, so bare references like
    ``{{ghost_head}}`` or ``{{content}}`` must be supplied as plain context values.
    """
    return {
        "@site": sample["site"],
        "@custom": sample.get("custom", {}),
        "ghost_head": "",
        "ghost_foot": "",
        "body_class": "preview",
        "post_class": "post",
        "meta_title": sample["site"]["title"],
        "navigation": _safe(""),
    }


def _with_content(post: dict) -> dict:
    """Add a safe ``content`` value so ``{{content}}`` renders its HTML unescaped."""
    return {**post, "content": _safe(post.get("html", ""))}


def _page_contexts(sample: dict) -> dict[str, dict]:
    base = _base_context(sample)
    return {
        "index": {**base, "posts": [_with_content(p) for p in sample["posts"]]},
        "post": {**base, "post": _with_content(sample["post"])},
        "page": {
            **base,
            "post": _with_content(sample["page"]),
            "@page": {"show_title_and_feature_image": True},
        },
    }


def _build_helpers() -> dict:
    """Helpers Ghost invokes with arguments or a block (so pybars3 calls them)."""

    def asset(this, path, **_kw):
        return f"/assets/{path}"

    def img_url(this, value=None, **_kw):
        return value or ""

    def foreach(this, options, items):
        return [options["fn"](item) for item in (items or [])]

    return {"asset": asset, "img_url": img_url, "foreach": foreach}


def _load_partials(theme: Path) -> dict:
    partials = {}
    partials_dir = theme / "partials"
    if partials_dir.is_dir():
        for path in partials_dir.rglob("*.hbs"):
            name = path.relative_to(partials_dir).with_suffix("").as_posix()
            partials[name] = _compiler.compile(path.read_text(encoding="utf-8"))
    return partials


def _render_with_layout(
    source: str, context: dict, helpers: dict, partials: dict, theme: Path
) -> str:
    match = _LAYOUT_DIRECTIVE.search(source)
    body_source = _LAYOUT_DIRECTIVE.sub("", source)
    body_html = str(_compiler.compile(body_source)(context, helpers=helpers, partials=partials))

    if not match:
        return body_html
    layout_file = theme / f"{match.group(1)}.hbs"
    if not layout_file.exists():
        return body_html
    layout_context = {**context, "body": body_html}
    layout = _compiler.compile(layout_file.read_text(encoding="utf-8"))
    return str(layout(layout_context, helpers=helpers, partials=partials))


def render_theme(theme_dir: str | Path, *, sample: dict | None = None) -> dict[str, str]:
    """Render a theme's home, post, and page templates to HTML strings.

    Args:
        theme_dir: Path to the theme directory.
        sample: Optional sample data (see :func:`default_sample`); supply real
            site settings here to make the preview brand-accurate.

    Returns:
        A mapping of page name (``index``/``post``/``page``) to rendered HTML, for
        whichever of those templates the theme defines.
    """
    theme = Path(theme_dir)
    sample = sample or default_sample()
    helpers = _build_helpers()
    partials = _load_partials(theme)
    contexts = _page_contexts(sample)

    pages: dict[str, str] = {}
    for name in _PREVIEW_PAGES:
        template_file = theme / f"{name}.hbs"
        if template_file.exists():
            source = template_file.read_text(encoding="utf-8")
            pages[name] = _render_with_layout(source, contexts[name], helpers, partials, theme)
    return pages


def write_preview(
    theme_dir: str | Path,
    out_dir: str | Path,
    *,
    sample: dict | None = None,
) -> dict[str, Path]:
    """Render a theme and write the HTML plus a copy of its assets to ``out_dir``.

    Returns a mapping of page name to the written HTML file path.
    """
    theme = Path(theme_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    assets = theme / "assets"
    if assets.is_dir():
        shutil.copytree(assets, out / "assets", dirs_exist_ok=True)

    written: dict[str, Path] = {}
    for name, html in render_theme(theme, sample=sample).items():
        path = out / ("index.html" if name == "index" else f"{name}.html")
        path.write_text(html, encoding="utf-8")
        written[name] = path
    return written


def serve_preview(
    out_dir: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[str, http.server.ThreadingHTTPServer]:
    """Serve a rendered preview directory over HTTP on a background thread.

    Returns the base URL and the running server (call ``server.shutdown()`` to stop).
    Port ``0`` picks a free port.
    """
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
    server = http.server.ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://{host}:{server.server_address[1]}/", server
