"""Build and package Ghost themes.

* :func:`build_theme` assembles a complete, valid, *previewable* theme from a spec.
  The skeleton (layout, home/post/page templates, page handling, required Koenig
  CSS, ``package.json``) is always written so the result passes Ghost's validator;
  the caller supplies the design (CSS, and optionally template bodies).
* :func:`package_theme` zips a theme directory for upload.

Generated themes deliberately stay within the subset the local previewer supports —
in particular, no Handlebars block params (``as |x|``) — so a generated theme can
always be previewed before it is uploaded.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: Detects Handlebars block params, which the local previewer cannot render.
_BLOCK_PARAMS = re.compile(r"\bas\s+\|")

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

#: Base stylesheet. Includes the Koenig width classes Ghost requires, and uses the
#: brand accent Ghost injects as ``--ghost-accent-color`` (with a fallback).
_BASE_CSS = """:root {
    --accent: var(--ghost-accent-color, #15171a);
    --max-width: 720px;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.6;
    color: #15171a;
}

a {
    color: var(--accent);
}

.site-header,
.site-main,
.site-footer {
    max-width: var(--max-width);
    margin: 0 auto;
    padding: 1.5rem;
}

.site-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);
    text-decoration: none;
}

.site-description {
    margin: 0.25rem 0 0;
    color: #626d79;
}

.post-card {
    padding: 1.5rem 0;
    border-bottom: 1px solid #e5eff5;
}

.post-card-title a {
    color: #15171a;
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

.kg-width-wide {
    position: relative;
    width: 85vw;
    min-width: 100%;
    margin-left: 50%;
    transform: translateX(-50%);
}

.kg-width-full {
    position: relative;
    width: 100vw;
    margin-left: 50%;
    transform: translateX(-50%);
}
"""

#: Template names that always make up the skeleton, mapped to their default source.
_SKELETON = {
    "default": _DEFAULT_HBS,
    "index": _INDEX_HBS,
    "post": _POST_HBS,
    "page": _PAGE_HBS,
}


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
        raise ValueError(
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
        ValueError: if an overridden template uses Handlebars block params.
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
        "config": {"posts_per_page": 5},
    }
    (theme / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    templates = dict(_SKELETON)
    for name, source in spec.templates.items():
        _ensure_previewable(name, source)
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
        FileNotFoundError: if the directory does not exist.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"theme directory not found: {source}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                arcname = Path(source.name) / path.relative_to(source)
                archive.write(path, arcname.as_posix())
    return buffer.getvalue()
