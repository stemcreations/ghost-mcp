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

#: Detects a ``from=`` hash argument inside a mustache tag. pybars3 turns hash args
#: into Python keyword arguments, and ``from`` is a Python keyword, so a template
#: using it fails to *compile* for preview (an unfixable pybars3 limitation).
_FROM_HASH_ARG = re.compile(r"\{\{[^}]*\bfrom\s*=")

#: Detects ``{{else if}}``. pybars3 compiles it but renders the WRONG branch (a silent
#: bug), so it is rejected in favour of nested ``{{#if}}…{{else}}{{#if}}…``.
_ELSE_IF = re.compile(r"\{\{\s*else\s+if\b")

#: Detects hash parameters passed to a partial (``{{> name key=value}}``), which
#: pybars3 cannot compile. Passing a context object (``{{> name obj}}``) is fine.
_PARTIAL_HASH_PARAM = re.compile(r"\{\{>\s*[^}]*=")

#: Detects a Handlebars layout directive, e.g. ``{{!< default}}``.
_LAYOUT_DIRECTIVE = re.compile(r"\{\{!<\s*[\w-]+\s*\}\}")

#: Detects the ``{{{body}}}`` (or ``{{body}}``) tag where the layout injects child
#: templates. A ``default.hbs`` without it renders every page empty.
_LAYOUT_BODY = re.compile(r"\{\{\{?\s*body\s*\}?\}\}")

#: Detects a hardcoded ``<nav>`` element and whether the admin-managed navigation
#: system is used, so the builder can advise (not force) ``{{navigation}}``.
_HARDCODED_NAV = re.compile(r"<nav\b", re.IGNORECASE)
_USES_NAVIGATION = re.compile(r"\{\{[^}]*\bnavigation\b")

#: Detects an existing ``<link>`` to the stylesheet, so we don't inject a second one.
_STYLESHEET_LINK = re.compile(r"<link[^>]*screen\.css", re.IGNORECASE)

#: The closing ``</head>``/``</body>`` tags, where missing layout essentials are injected.
_HEAD_CLOSE = re.compile(r"</head>", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body>", re.IGNORECASE)

#: Ghost's required output helpers, detected so we don't inject a duplicate.
_GHOST_HEAD = re.compile(r"\{\{\s*ghost_head\s*\}\}")
_GHOST_FOOT = re.compile(r"\{\{\s*ghost_foot\s*\}\}")

#: The stylesheet link a layout needs. ``{{asset}}`` only emits the URL, so it must
#: live inside a real ``<link>`` to actually load the CSS.
_STYLESHEET_TAG = (
    '    <link rel="stylesheet" type="text/css" href="{{asset "built/screen.css"}}">\n'
)

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
        <div class="gh-inner">
            <a class="site-title" href="{{@site.url}}">{{@site.title}}</a>
            <p class="site-description">{{@site.description}}</p>
        </div>
    </header>
    <main class="site-main">
        {{{body}}}
    </main>
    <footer class="site-footer">
        <div class="gh-inner">
            <p>&copy; {{@site.title}}</p>
        </div>
    </footer>
    {{ghost_foot}}
</body>
</html>
"""

_INDEX_HBS = """{{!< default}}
<div class="gh-inner">
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
</div>
"""

_POST_HBS = """{{!< default}}
{{#post}}
<article class="post">
    <header class="post-header gh-inner">
        <h1 class="post-title">{{title}}</h1>
        {{#if feature_image}}
        <img class="post-image" src="{{feature_image}}" alt="{{title}}">
        {{/if}}
    </header>
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
    <header class="page-header gh-inner">
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
#: reading column. Structural chrome classes (``.site-header``/``.site-footer``/
#: ``.post-feed``/``.post``/``.page``) stay full-width; a ``.gh-inner`` wrapper does
#: the reading-column capping, so a custom layout reusing those classes is never
#: silently width-limited by this base. See ``docs/theme-conventions.md``.
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

/* Site chrome spans the full viewport width; a `.gh-inner` wrapper inside centres
   its contents on the reading column. This outer/inner split (the pattern Ghost's
   own themes use) is deliberate: because the base stylesheet is prepended and a
   custom layout naturally reuses these same class names, capping `.site-header`
   directly would silently squeeze any full-width header a custom theme builds (and
   a `max-width` on a child can't escape a capped parent). So the structural classes
   stay full-width; only `.gh-inner` caps width, and only where a template adds one. */
.site-header,
.site-footer {
    padding: 1.5rem 0;
}

.site-main {
    padding: 1.5rem 0;
}

/* The reading-column wrapper. A full-width element places a `.gh-inner` inside to
   centre and cap its content; a custom layout uses its own wrapper (or none). */
.gh-inner {
    max-width: var(--content-width);
    margin-left: auto;
    margin-right: auto;
    padding-left: var(--gap);
    padding-right: var(--gap);
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

/* Post feed (home, tag, author). Its width comes from the wrapping `.gh-inner`
   (default templates) or a custom layout's own container -- not a cap here -- so a
   wide or multi-column feed that reuses `.post-feed` isn't squeezed to the reading
   column. */
.post-feed {
    margin: 0;
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

/* Single post / page. The header (title + feature image) sits on the reading column
   via a `.gh-inner` wrapper in the template; the content body below is a grid
   "canvas" (see `.post-content`) so Koenig wide/full cards can break outward. The
   base intentionally does NOT cap `.post`/`.page` children directly -- that would
   width-limit any custom post layout that reuses those classes. */
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


def _inject_before(source: str, close: re.Pattern[str], snippet: str) -> str:
    """Insert ``snippet`` immediately before the first match of ``close`` (or no-op)."""
    if not close.search(source):
        return source
    return close.sub(lambda m: snippet + m.group(0), source, count=1)


def _ensure_layout_essentials(source: str) -> str:
    """Inject the bits a custom layout needs to actually work, when they're missing.

    A ``default.hbs`` is easy to write in a way that silently breaks: the stylesheet
    must sit inside a real ``<link>`` (``{{asset …}}`` alone only emits a URL that
    renders as bare text), and Ghost's ``{{ghost_head}}``/``{{ghost_foot}}`` carry
    SEO, the accent colour, members, and card assets. Inject each before the
    matching close tag if absent -- the same safety net as the ``{{!< default}}``
    auto-injection for content templates. (``{{{body}}}`` can't be injected: there's
    no way to know where content belongs, so a layout lacking it is rejected.)
    """
    if not _STYLESHEET_LINK.search(source):
        source = _inject_before(source, _HEAD_CLOSE, _STYLESHEET_TAG)
    if not _GHOST_HEAD.search(source):
        source = _inject_before(source, _HEAD_CLOSE, "    {{ghost_head}}\n")
    if not _GHOST_FOOT.search(source):
        source = _inject_before(source, _BODY_CLOSE, "    {{ghost_foot}}\n")
    return source


def nav_advisory(default_template: str | None) -> str | None:
    """Advise (not force) ``{{navigation}}`` when a custom layout hardcodes its nav.

    Ghost has an admin-managed menu system; a hardcoded ``<nav>`` silently ignores it,
    so menus set in Ghost admin do nothing. That's a quiet quality problem (the theme
    validates and previews fine). This returns a soft warning the caller can surface,
    not an error -- fixed links are sometimes the right call.
    """
    if not default_template:
        return None
    if _HARDCODED_NAV.search(default_template) and not _USES_NAVIGATION.search(default_template):
        return (
            "default_template has a hardcoded <nav> and no {{navigation}}; use "
            "{{navigation}} (or a partials/navigation.hbs loop) so the site owner "
            "manages the menu in Ghost admin, unless you intend fixed links the post "
            "author can't change."
        )
    return None


def _ensure_previewable(name: str, source: str) -> None:
    if _BLOCK_PARAMS.search(source):
        raise ThemeError(
            f"template '{name}' uses Handlebars block params (as |x|), which the local "
            "previewer cannot render; rewrite the loop without block params."
        )
    if _FROM_HASH_ARG.search(source):
        raise ThemeError(
            f"template '{name}' uses a 'from=' loop argument; the local previewer "
            "(pybars3) cannot compile it because 'from' is a Python keyword. Use "
            "'limit='/'to=' to slice the loop, or drop it."
        )
    if _ELSE_IF.search(source):
        raise ThemeError(
            f"template '{name}' uses "
            "{{else if}}, which the local previewer (pybars3) renders incorrectly "
            "(it picks the wrong branch); rewrite as nested "
            "{{#if}}...{{else}}{{#if}}...{{/if}}{{/if}}."
        )
    if _PARTIAL_HASH_PARAM.search(source):
        raise ThemeError(
            f"template '{name}' passes hash parameters to a partial "
            "({{> name key=value}}), which the local previewer cannot compile. Inline "
            "the values into the partial, or pass a context object ({{> name obj}}); "
            "partial parameters work on the live site."
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
        if name == "default":
            # The layout must inject children via {{{body}}}; without it every page
            # renders with no content.
            if not _LAYOUT_BODY.search(source):
                raise ThemeError(
                    "the 'default' layout override must contain a {{{body}}} tag where "
                    "child templates are injected; without it every page renders empty."
                )
            # Inject the stylesheet <link> and ghost_head/ghost_foot if the override
            # left them out, so a hand-written layout can't silently break styling/SEO.
            source = _ensure_layout_essentials(source)
        elif name in _CONTENT_TEMPLATES and not _LAYOUT_DIRECTIVE.search(source):
            # A content template is a body fragment that must inherit the site layout
            # (default.hbs) via a {{!< default}} directive; without it Ghost and the
            # local previewer render it as a bare fragment with no <head>, so the
            # stylesheet never loads. Overrides routinely omit the line, so restore it.
            source = "{{!< default}}\n" + source
        templates[name] = source
    for name, source in templates.items():
        (theme / f"{name}.hbs").write_text(source, encoding="utf-8")

    css = _BASE_CSS
    if spec.styles.strip():
        css += "\n\n/* ----- custom styles ----- */\n" + spec.styles.strip() + "\n"
    (theme / "assets" / "built" / "screen.css").write_text(css, encoding="utf-8")

    return theme


#: The compiled-stylesheet path a Ghost theme serves. Generated themes and Ghost's
#: own Source/Casper all emit to this path; restyle_archive rewrites this entry.
_SCREEN_CSS_SUFFIX = "assets/built/screen.css"


def restyle_archive(zip_bytes: bytes, css: str, *, mode: str = "append") -> bytes:
    """Rewrite a theme ZIP's ``screen.css`` and return the repackaged archive.

    The download-edit-reupload path for iterating an *installed* theme without
    regenerating it: find ``assets/built/screen.css`` inside the archive and either
    append ``css`` after the existing rules (``mode="append"`` -- the safe default,
    since later rules win by source order) or replace the file's contents
    (``mode="replace"``). Every other file is copied through unchanged.

    Args:
        zip_bytes: The theme archive (e.g. from ``download_theme``).
        css: The CSS to append, or to replace the stylesheet with.
        mode: ``"append"`` (default) or ``"replace"``.

    Returns:
        The repackaged ZIP bytes, ready for ``upload_theme``.

    Raises:
        ThemeError: if ``mode`` is invalid, or the archive has no
            ``assets/built/screen.css`` (a theme whose CSS compiles elsewhere can't
            be restyled this way).
    """
    if mode not in ("append", "replace"):
        raise ThemeError(f"mode must be 'append' or 'replace', not {mode!r}.")
    addition = css.strip()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zin:
        target = next((n for n in zin.namelist() if n.endswith(_SCREEN_CSS_SUFFIX)), None)
        if target is None:
            raise ThemeError(
                f"theme archive has no {_SCREEN_CSS_SUFFIX} to restyle; its stylesheet "
                "is compiled elsewhere, so edit and re-upload it manually."
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == target:
                    if mode == "append":
                        existing = data.decode("utf-8", errors="replace").rstrip()
                        new_css = f"{existing}\n\n/* ----- restyle ----- */\n{addition}\n"
                    else:
                        new_css = addition + "\n"
                    data = new_css.encode("utf-8")
                zout.writestr(info, data)
    return buffer.getvalue()


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
