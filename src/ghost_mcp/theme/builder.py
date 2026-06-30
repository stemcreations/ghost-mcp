"""Build and package Ghost themes.

* :func:`build_theme` assembles a complete, valid, *previewable* theme from a spec.
  The skeleton (layout, home/post/page templates, page handling, required Koenig
  CSS, ``package.json``) is always written so the result passes Ghost's validator;
  the caller supplies the design (CSS, and optionally template bodies).
* :func:`package_theme` zips a theme directory for upload.

Generated themes deliberately stay within the subset the local previewer supports,
in particular no Handlebars block params (``as |x|``), so a generated theme can
always be previewed before it is uploaded.

See ``docs/theme-conventions.md`` for the full contract a template must satisfy
(required tags, the previewable helper subset, ``package.json`` fields).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ghost_mcp.errors import ThemeError

#: Detects Handlebars block params, which the local previewer cannot render.
_BLOCK_PARAMS = re.compile(r"\bas\s+\|")

#: Detects a Handlebars layout directive, e.g. ``{{!< default}}``.
_LAYOUT_DIRECTIVE = re.compile(r"\{\{!<\s*[\w-]+\s*\}\}")

_DEFAULT_HBS = """<!DOCTYPE html>
<html lang="{{@site.locale}}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{meta_title}}</title>
    <link rel="stylesheet" type="text/css" href="{{asset "built/screen.css"}}">
    {{ghost_head}}
</head>
<body class="{{body_class}}">
    <header class="site-header">
        <a class="site-title" href="{{@site.url}}">{{@site.title}}</a>
        <p class="site-description">{{@site.description}}</p>
    </header>
    <main class="site-main">
        {{{body}}}
    </main>
    <footer class="site-footer">
        <p>&copy; {{@site.title}}</p>
    </footer>
    {{ghost_foot}}
</body>
</html>
"""

_INDEX_HBS = """{{!< default}}
<section class="post-feed">
{{#foreach posts}}
    <article class="post-card">
        {{#if feature_image}}
        <a class="post-card-image-link" href="{{url}}">
            <img class="post-card-image" src="{{feature_image}}" alt="{{title}}">
        </a>
        {{/if}}
        <h2 class="post-card-title"><a href="{{url}}">{{title}}</a></h2>
        <p class="post-card-excerpt">{{excerpt}}</p>
    </article>
{{/foreach}}
</section>
"""

_POST_HBS = """{{!< default}}
{{#post}}
<article class="post">
    <h1 class="post-title">{{title}}</h1>
    {{#if feature_image}}
    <img class="post-image" src="{{feature_image}}" alt="{{title}}">
    {{/if}}
    <section class="post-content">
        {{content}}
    </section>
</article>
{{/post}}
"""

_PAGE_HBS = """{{!< default}}
{{#post}}
<article class="page">
    {{#if @page.show_title_and_feature_image}}
    <header class="page-header">
        <h1 class="page-title">{{title}}</h1>
        {{#if feature_image}}
        <img class="page-image" src="{{feature_image}}" alt="{{title}}">
        {{/if}}
    </header>
    {{/if}}
    <section class="post-content">
        {{content}}
    </section>
</article>
{{/post}}
"""

#: Base stylesheet. Follows Ghost theme conventions: semantic design tokens on
#: ``:root``, the brand accent Ghost injects as ``--ghost-accent-color``, Ghost's
#: font-picker variables (``--gh-font-heading``/``--gh-font-body``), and the
#: grid-based content "canvas" that lets Koenig wide/full cards break out of the
#: reading column. See ``docs/theme-conventions.md``.
_BASE_CSS = """:root {
    /* Brand accent: Ghost injects --ghost-accent-color from the site's setting. */
    --accent: var(--ghost-accent-color, #15171a);

    /* Colour tokens (semantic names, the Ghost theme convention). */
    --color-bg: #ffffff;
    --color-text: #15171a;
    --color-secondary-text: rgb(0 0 0 / 0.55);
    --color-border: rgb(0 0 0 / 0.1);

    /* Type tokens. Ghost's font picker exposes --gh-font-heading/--gh-font-body;
       we consume them with a system-font fallback so the design panel just works. */
    --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --font-serif: Georgia, "Times New Roman", serif;
    --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

    /* Layout tokens. --content-width is the reading column; --container-width caps
       wide/full breakouts and the post feed; --gap is the responsive edge gutter. */
    --content-width: 720px;
    --container-width: 1200px;
    --gap: clamp(20px, 5vw, 64px);
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--color-bg);
    font-family: var(--gh-font-body, var(--font-sans));
    line-height: 1.6;
    color: var(--color-text);
}

a {
    color: var(--accent);
}

/* Site chrome is centred on the reading column. */
.site-header,
.site-footer {
    max-width: var(--content-width);
    margin: 0 auto;
    padding: 1.5rem var(--gap);
}

.site-main {
    padding: 1.5rem 0;
}

.site-title {
    font-family: var(--gh-font-heading, var(--font-sans));
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);
    text-decoration: none;
}

.site-description {
    margin: 0.25rem 0 0;
    color: var(--color-secondary-text);
}

/* Post feed (home, tag, author) — a centred reading column. */
.post-feed {
    max-width: var(--content-width);
    margin: 0 auto;
    padding: 0 var(--gap);
}

.post-card {
    padding: 1.5rem 0;
    border-bottom: 1px solid var(--color-border);
}

.post-card-title a {
    color: var(--color-text);
    text-decoration: none;
}

.post-card-title a:hover {
    color: var(--accent);
}

.post-image,
.post-card-image {
    width: 100%;
    height: auto;
    border-radius: 6px;
}

/* Single post / page. Header elements sit on the reading column; the content body
   is a grid "canvas" so Koenig wide/full cards can break outward. */
.post > *,
.page > * {
    max-width: var(--content-width);
    margin-left: auto;
    margin-right: auto;
    padding-left: var(--gap);
    padding-right: var(--gap);
}

.post-title,
.page-title {
    font-family: var(--gh-font-heading, var(--font-sans));
}

/* The content canvas: a grid keyed to named lines. Body elements land in the centre
   "main" column; .kg-width-wide and .kg-width-full break outward toward the edges.
   This is the technique Ghost's own themes use for editor-card width. */
.post-content {
    display: grid;
    max-width: none;
    padding: 0;
    grid-template-columns:
        [full-start] minmax(var(--gap), 1fr)
        [wide-start] minmax(0, calc((var(--container-width) - var(--content-width)) / 2))
        [main-start] min(var(--content-width), 100% - var(--gap) * 2) [main-end]
        minmax(0, calc((var(--container-width) - var(--content-width)) / 2)) [wide-end]
        minmax(var(--gap), 1fr) [full-end];
}

.post-content > * {
    grid-column: main;
}

.post-content > .kg-width-wide {
    grid-column: wide;
}

.post-content > .kg-width-full {
    grid-column: full;
}

.post-content > .kg-width-full img {
    width: 100%;
}
"""

#: Template names that always make up the skeleton, mapped to their default source.
_SKELETON = {
    "default": _DEFAULT_HBS,
    "index": _INDEX_HBS,
    "post": _POST_HBS,
    "page": _PAGE_HBS,
}

#: Content templates that are body fragments and must inherit the site layout.
_CONTENT_TEMPLATES = frozenset({"index", "post", "page"})


@dataclass
class ThemeSpec:
    """A description of a theme to generate.

    The skeleton templates are used unless overridden via ``templates`` (keyed by
    template name, e.g. ``"index"``). ``styles`` is appended to the base stylesheet.
    """

    name: str
    styles: str = ""
    description: str = ""
    author_name: str = "ghost-mcp"
    author_email: str = "noreply@example.com"
    templates: dict[str, str] = field(default_factory=dict)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "ghost-mcp-theme"


def _ensure_previewable(name: str, source: str) -> None:
    if _BLOCK_PARAMS.search(source):
        raise ThemeError(
            f"template '{name}' uses Handlebars block params (as |x|), which the local "
            "previewer cannot render; rewrite the loop without block params."
        )


def build_theme(spec: ThemeSpec, out_dir: str | Path) -> Path:
    """Assemble a complete theme directory from ``spec`` and return its path.

    Args:
        spec: The theme to build.
        out_dir: Directory to create the theme inside; the theme is written to a
            subdirectory named after the slugified theme name.

    Returns:
        The path to the generated theme directory.

    Raises:
        ThemeError: if an overridden template uses Handlebars block params.
    """
    slug = _slugify(spec.name)
    theme = Path(out_dir) / slug
    (theme / "assets" / "built").mkdir(parents=True, exist_ok=True)

    package = {
        "name": slug,
        "description": spec.description or "A theme generated by ghost-mcp.",
        "version": "0.1.0",
        "engines": {"ghost-api": "v5.0"},
        "license": "MIT",
        "author": {"name": spec.author_name, "email": spec.author_email},
        "config": {
            "posts_per_page": 5,
            # Let Ghost auto-inject its Koenig editor-card styles/scripts on the live
            # blog (galleries, bookmarks, buttons, …); true is Ghost's default, set
            # here so the behaviour is explicit. The previewer adds the kg-width
            # classes itself since it has no Ghost to inject them.
            "card_assets": True,
            # Named widths that power responsive images via {{img_url … size=…}} on
            # the live blog. Mirrors Source; ignored by the local previewer.
            "image_sizes": {
                "xs": {"width": 160},
                "s": {"width": 320},
                "m": {"width": 600},
                "l": {"width": 960},
                "xl": {"width": 1200},
                "xxl": {"width": 2000},
            },
        },
    }
    (theme / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    templates = dict(_SKELETON)
    for name, source in spec.templates.items():
        _ensure_previewable(name, source)
        # A content template is a body fragment that must inherit the site layout
        # (default.hbs) via a {{!< default}} directive; without it Ghost and the
        # local previewer render it as a bare fragment with no <head>, so the
        # stylesheet never loads. Overrides routinely omit the line, so restore it.
        if name in _CONTENT_TEMPLATES and not _LAYOUT_DIRECTIVE.search(source):
            source = "{{!< default}}\n" + source
        templates[name] = source
    for name, source in templates.items():
        (theme / f"{name}.hbs").write_text(source, encoding="utf-8")

    css = _BASE_CSS
    if spec.styles.strip():
        css += "\n\n/* ----- custom styles ----- */\n" + spec.styles.strip() + "\n"
    (theme / "assets" / "built" / "screen.css").write_text(css, encoding="utf-8")

    return theme


def package_theme(source_dir: str | Path) -> bytes:
    """Package a theme directory into ZIP bytes ready for upload.

    The archive is rooted at a single top-level folder named after the source
    directory, matching the layout Ghost expects.

    Args:
        source_dir: Path to the directory containing the theme's files.

    Returns:
        The ZIP archive as bytes.

    Raises:
        ThemeError: if the directory does not exist.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise ThemeError(f"theme directory not found: {source}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                arcname = Path(source.name) / path.relative_to(source)
                archive.write(path, arcname.as_posix())
    return buffer.getvalue()
