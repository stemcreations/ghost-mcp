# Ghost theme conventions

How the theme builder (`ghost_mcp/theme/`) generates themes, the rules an overridden
template must follow, and the Ghost conventions a custom theme should abide by.
Distilled from Ghost's official **Source** theme and the theme/Admin API docs
(`ghost-llms-full.txt`).

A generated theme has to satisfy **two** contracts at once:

1. **Valid on a live Ghost blog** — passes Ghost's `gscan` validator and renders
   correctly once activated.
2. **Renderable by the local previewer** (`theme/preview.py`) — so a theme can be
   checked in a browser *before* it is uploaded.

The second contract is the stricter one. The previewer is an approximation: no
running Ghost, no live data, only a handful of stubbed helpers. Anything it can't
render must stay out of generated templates, even though real Ghost would handle it.
**When in doubt, prefer the smaller, previewable subset.**

---

## Template hierarchy and contexts

Each request resolves to a *context*, which picks a template and the data available.
Ghost falls back down the hierarchy when a template is absent.

| Template | Required? | Context / data | Falls back to |
| --- | --- | --- | --- |
| `default.hbs` | layout | The wrapper (`<html><head><body>`); children inject via `{{{body}}}`. | — |
| `index.hbs` | **yes** | Post list: `posts` array + `pagination`. | — |
| `post.hbs` | **yes** | Single post, inside `{{#post}}`. | — |
| `page.hbs` | no | Single page, inside `{{#post}}` + `@page`. | `post.hbs` |
| `home.hbs` | no | Home page (same data as index). | `index.hbs` |
| `tag.hbs` | no | Tag archive, inside `{{#tag}}` (name, description, feature_image) + `posts`. | `index.hbs` |
| `author.hbs` | no | Author archive, inside `{{#author}}` (name, bio, social, image) + `posts`. | `index.hbs` |
| `error.hbs` / `error-404.hbs` | no | 4xx/5xx errors. **Use only `{{asset}}`** — no other helpers, no `{{!< default}}`. | Ghost default |

Slug/custom variants exist too (`post-:slug.hbs`, `page-about.hbs`, `custom-*.hbs`),
resolved before the generic template.

**The builder generates the minimum:** `default`, `index`, `post`, `page`. That
satisfies `gscan` (which requires `index.hbs` + `post.hbs`) and covers what the
previewer renders. `tag`/`author`/`home`/`error` are conventional add-ons.

---

## Required tags in `default.hbs`

| Tag | Placement | Purpose |
| --- | --- | --- |
| `{{ghost_head}}` | last thing before `</head>` | SEO/meta/structured data, **accent color**, Koenig `cards.min.css`. |
| `{{ghost_foot}}` | last thing before `</body>` | Ghost's functional scripts (members/Portal, etc.). |
| `<link … href="{{asset "built/screen.css"}}">` | in `<head>` | The stylesheet. `{{asset}}` only emits the URL with cache-busting, so it must sit inside a real `<link rel="stylesheet">` — a bare `{{asset …}}` renders as visible text and loads nothing. |
| `{{body_class}}` | on `<body>` | Context classes (`post-template`, `tag-template`, …). |
| `{{{body}}}` | in `<body>` | Where the child template is injected (triple-stache = unescaped). |
| `<html lang="{{@site.locale}}">` | root | Site locale. |

Omitting `{{ghost_head}}` or `{{ghost_foot}}` is a `gscan` error and breaks SEO,
the accent color, members, and card rendering. If a `default_template` override
omits the stylesheet `<link>` entirely, the builder injects one before `</head>`
(the same safety net as the `{{!< default}}` injection for content templates) — but
a `default.hbs` without `{{{body}}}` is rejected at build, since it would render
every page empty.

## Content templates

Every content template (`index`/`post`/`page`/`home`/`tag`/`author`) must start with
the layout directive so it is wrapped in `default.hbs`:

```handlebars
{{!< default}}
```

**This line is load-bearing.** Without it Ghost (and the previewer) renders the
template as a bare fragment with no `<head>`, so the stylesheet never loads — the
symptom looks exactly like "the CSS isn't working." The builder restores it on any
content-template override that omits it, but write it anyway.

Post/page bodies are wrapped in the post block and emitted with `{{content}}`
(renders the post HTML, including Koenig cards, unescaped):

```handlebars
{{!< default}}
{{#post}}
  <article class="post">
    <h1 class="post-title">{{title}}</h1>
    <section class="post-content">{{content}}</section>
  </article>
{{/post}}
```

---

## The previewable helper subset

The previewer (`theme/preview.py`) supports only:

| Construct | Notes |
| --- | --- |
| `{{!< default}}` | Layout inheritance (one bare layout name, no paths). |
| `{{#if x}}` / `{{#unless x}}` | Truthiness blocks, with `{{else}}`. **No `{{else if}}`** (see below). |
| `{{#foreach items}}…{{else}}…{{/foreach}}` | Ghost's loop over a list already in context (`posts`). Honours `limit=`/`to=`. Does **not** expose `@first`/`@last`/`@index` in preview (those are live-only); use `{{#each}}` if you need loop position to preview. |
| `{{#each items}}…{{/each}}` | Core loop; exposes `@index`, `@first`, `@last`, `@key`. Works in preview *and* live. |
| `{{#with obj}}…{{/with}}` | Enter an object's context. |
| `{{#post}}` / `{{#page}}` | Enter the post/page object's context. |
| Paths | `{{a.b.c}}` nested, `{{../x}}` parent, `{{this}}` / `{{.}}` current. |
| `{{> "partials/name"}}` and `{{> "name" obj}}` | Partials from `partials/`, optionally with a **context object**. Passing **hash params** (`key=value`) is rejected (see below). |
| Bare fields | `{{title}}`, `{{url}}`, `{{excerpt}}`, `{{feature_image}}`, `{{content}}`. |
| `{{{x}}}` / `{{&x}}` | Unescaped HTML output. |
| `{{asset "path"}}` | Returns `/assets/path`. |
| `{{img_url x size="m"}}` | Valid on live Ghost; previewer returns the URL unchanged (size/format ignored). |
| `{{lookup obj key}}` | Dynamic property/index lookup. |
| Subexpressions | `{{outer (inner arg)}}`. |
| Comments / whitespace | `{{! … }}`, `{{!-- … --}}`, and `{{~ … ~}}` whitespace control. |
| `@site`, `@custom`, `@page` | Data globals from `default_sample()`. |

The list above is what the **preview** can render. It is **not** the list of what a
theme may use. Two more categories matter, and they are different in kind: one is a
hard "cannot use," the other is "correct and encouraged for the live theme, just
invisible in preview." Do not conflate them — treating a live-only helper as
forbidden is how themes end up hardcoding things Ghost is meant to manage (see
[Navigation](#navigation)).

**Rejected at build (cannot use — `_ensure_previewable` raises with a clear message):**

- **Block params:** `{{#get … as |recent|}}`, `{{#each x as |v|}}`. pybars3 can't parse
  them.
- **`from=` loop argument:** `{{#foreach posts from="5"}}`. pybars3 turns hash args
  into Python keyword arguments and `from` is a Python keyword, so the generated code
  won't compile. Slice with `limit=` / `to=` instead (those work in preview), or
  feature the first item with a CSS `:first-child` rule.
- **`{{else if}}`:** pybars3 compiles it but renders the **wrong branch** (a silent
  bug), so it's rejected. Rewrite as nested
  `{{#if a}}…{{else}}{{#if b}}…{{/if}}{{/if}}`, which previews correctly and is also
  valid live.
- **Partial hash params:** `{{> "header" style="big"}}`. pybars3 can't compile a
  partial with `key=value` args (Source uses these everywhere, so don't copy its
  partials verbatim). Inline the values, or pass a context object (`{{> "header" obj}}`,
  which *is* allowed). Partial params work on the live site.

**Live-only helpers (use them for production themes — they render blank in local
preview, then work once uploaded):** the previewer installs a `helperMissing`
catch-all, so these degrade to empty rather than crashing. They are standard,
correct, and **encouraged** on the live site. Do not avoid one just because the
preview can't show it — style it, then confirm it on the live site.

- `{{navigation}}` / `{{navigation type="secondary"}}` — admin-managed header/footer
  menus. **Prefer this over hardcoding menu links.** See [Navigation](#navigation).
- `{{pagination}}` — move between pages of posts.
- `{{author}}` / `{{authors}}`, `{{date}}` — real author and date data.
- Membership gating inside `{{content}}` (the upgrade/sign-up CTA Ghost outputs for
  gated posts), `{{#get}}` data queries, `{{#match}}` / `{{#is}}` / `{{#has}}` flow
  helpers, `{{social_url}}`, `{{t}}` (i18n), `{{@config.*}}`, `{{recommendations}}`,
  `{{comments}}`, `{{excerpt words=…}}`.
- `{{#foreach}}` loop `@`-data (`@number`, `@first`, `@last`, `@even`, `@odd`):
  live-only with Ghost's `foreach`. If you need loop position to show in preview too,
  use `{{#each}}` (its `@index`/`@first`/`@last` render in both).

(Bare `{{excerpt}}` / `{{title}}` field lookups are unaffected; only the *helper*
forms degrade.) Source uses the live-only helpers throughout, which is why Source
isn't previewable by this tool — read it for structure and class names, but don't
copy-paste its helper usage into a template you intend to preview.

---

## `package.json`

| Field | Value / notes |
| --- | --- |
| `name` | Slug; must match the theme folder name. |
| `engines.ghost-api` | Target Admin API version, e.g. `"v5.0"`. The **spec-canonical** field. Source also sets `engines.ghost` (`">=5.0.0"`); both pass `gscan`. |
| `author.email` | `gscan` requires it. |
| `config.posts_per_page` | Feed page size (Ghost default 5). |
| `config.card_assets` | `true` (default) → Ghost auto-injects Koenig **card** CSS/JS, so editor cards (gallery, bookmark, button, callout, …) are styled on the live blog without you writing that CSS. The builder sets it explicitly. |
| `config.image_sizes` | Named widths (`xs`…`xxl`) powering responsive `{{img_url size=…}}`. Live-blog only; the previewer ignores them. |
| `config.custom` | Theme settings exposed in Ghost's Design panel (`@custom.*`), e.g. font pickers, header styles. Source uses these heavily; optional. |

---

## CSS conventions

The builder's base stylesheet (`_BASE_CSS`) follows these; custom `styles` are
appended after it.

**Design tokens on `:root`.** Semantic custom properties — colors
(`--color-text`, `--color-secondary-text`, `--color-border`), type (`--font-sans`,
`--font-serif`, `--font-mono`), and layout (`--content-width`, `--container-width`,
`--gap`). Source defines a larger palette plus dark-mode overrides via a
`:root.has-light-text` class toggled by an inline luminance script — optional, but
the token approach is the convention.

**Accent color.** Ghost injects `--ghost-accent-color` (from Settings → Brand) via
`{{ghost_head}}`. Consume it with a fallback: `var(--ghost-accent-color, #15171a)`.
Use it for links, buttons, and accents so the theme respects the site's branding.

**Fonts.** Ghost's font picker exposes `--gh-font-heading` and `--gh-font-body`;
consume them with a system-font fallback (`var(--gh-font-body, var(--font-sans))`) so
the Design panel "just works." Custom web fonts are added with `@font-face` +
`<link rel="preload" as="font" crossorigin>` and `font-display: optional` to avoid
layout shift; load only the families actually used.

**Full-width chrome, capped via `.gh-inner` (the outer/inner split).** The base
stylesheet keeps the *structural* chrome classes — `.site-header`, `.site-footer`,
`.post-feed`, and the `.post`/`.page` wrappers — at **full viewport width**, and
centres their *contents* with an inner `.gh-inner` wrapper
(`max-width: var(--content-width)`). This matters most when you write a **custom
layout**: the base CSS is prepended and a custom layout naturally reuses these same
class names, so a base that capped `.site-header` *directly* would silently squeeze
any full-width header you build — and a `max-width` on a child can't escape a capped
parent (a header inner pinned to 1140px still collapses inside a 720px `.site-header`).
The rule of thumb: **structural classes are full-width; cap a region by wrapping its
content in your own inner element (or reuse `.gh-inner`) and set the width there.**
Don't expect the base to cap a structural class for you — and it won't fight you when
you set your own width.

**Content-width "canvas" (the load-bearing layout convention).** Ghost themes use a
CSS grid with *named columns* so editor cards can break out of the reading column:
the article body is a grid whose centre `main` column is the reading width, with
`wide` and `full` columns reaching outward. Body content lands in `main`;
`.kg-width-wide` → `wide`; `.kg-width-full` → `full` (edge-to-edge). The builder
implements this on `.post-content`. (Source names the lines
`full`/`wide`/`main`; the equivalent older pattern is "outer → inner → canvas":
`.gh-outer` pads the viewport edge, `.gh-inner` caps to a max-width, `.gh-canvas`
is the grid.)

**Koenig cards.** `{{content}}` emits markup with `.kg-*` classes. The essential
ones a theme must place are the width classes (`.kg-width-wide`, `.kg-width-full`);
the rest of each card's look comes from Ghost's `card_assets` (default on). Source
additionally hand-styles every card type to match its design — optional polish.

---

## Members and Portal

Ghost's membership UI is driven by data attributes and member globals — a core
convention, all client-side (handled by Ghost's Portal script via `{{ghost_foot}}`).

**Member state (gates):**

- `{{#if @site.members_enabled}}` — membership is on.
- `{{#if @site.paid_members_enabled}}` — paid tiers exist.
- `{{#if @site.members_invite_only}}` — invite-only mode.
- `{{#unless @member}}` … `{{else}}` … — branch on logged-out vs logged-in.
- `{{#if @member.paid}}` — the member is on a paid plan.

**Portal triggers** (any element with `data-portal`):

- `data-portal="signup"` / `"signin"` / `"account"` / `"upgrade"` /
  `"recommendations"` — open the matching Portal screen.

**Inline subscribe form:**

```html
<form data-members-form>
  <input data-members-email type="email" required>
  <button type="submit">Subscribe</button>
  <p data-members-error></p>
</form>
```

---

## Navigation

Ghost has an admin-managed menu system (Settings → Navigation). Use it so the site
owner controls the links, instead of hardcoding `<a>` tags into the layout. This is a
**live-only** helper: it renders blank in local preview, then populates on the live
site. That empty preview is expected, not a bug — style the nav and confirm the menu
in Ghost admin.

The simplest version is the bare helper, which emits a preset `<ul class="nav">`:

```handlebars
{{navigation}}                      {{!-- primary menu --}}
{{navigation type="secondary"}}     {{!-- secondary/footer menu --}}
```

For custom markup, add `partials/navigation.hbs` and loop the items yourself. Each
item exposes `label`, `url`, `slug`, and `current`:

```handlebars
<nav class="site-nav">
  <ul>
    {{#foreach navigation}}
      <li class="nav-{{slug}}{{#if current}} nav-current{{/if}}">
        <a href="{{url}}">{{label}}</a>
      </li>
    {{/foreach}}
  </ul>
</nav>
```

A single `navigation.hbs` styles both menus; branch with `{{#if isSecondary}}…{{/if}}`
to differ. Logo/home links point to `{{@site.url}}`.

**When to hardcode instead.** Admin-managed nav is the default, but fixed links are
sometimes the right call — e.g. a blog whose topbar points at the main marketing site
(`Product`, `Pricing`, `Start free trial`), which the person managing blog posts
should not be able to edit. Hardcode in that case, but make it a deliberate choice,
not an accident of the preview rendering empty. (`create_theme` returns a soft
advisory when a `default_template` has a hardcoded `<nav>` and no `{{navigation}}`.)

## Pagination

- `{{pagination}}` — prev/next links (uses a `pagination.hbs` partial if present).
- `<a href="{{page_url "next"}}">` with `{{@config.posts_per_page}}` for manual
  "next page" links.
- `pagination.pages` / `pagination.page` gate "see all" links.
- Infinite scroll is **optional** JS (see below); the server-rendered `/page/N/`
  links work without it.

## Responsive images

```handlebars
<img
  srcset="{{img_url feature_image size="s"}} 320w,
          {{img_url feature_image size="m"}} 600w,
          {{img_url feature_image size="l"}} 960w,
          {{img_url feature_image size="xl"}} 1200w"
  sizes="(max-width: 1200px) 100vw, 1120px"
  src="{{img_url feature_image size="xl"}}"
  alt="{{#if feature_image_alt}}{{feature_image_alt}}{{else}}{{title}}{{/if}}">
```

The `size=` values must be keys declared in `config.image_sizes`. Add
`format="webp"` for modern formats. The previewer renders `{{img_url}}` as the raw
URL (it ignores `size`/`format`), so this is safe to include.

## Search

- `<button data-ghost-search>` triggers Ghost's built-in search modal (powered by
  Ghost's bundled script). No custom JS needed.

---

## JavaScript

**A valid Ghost theme needs no JavaScript.** Everything in Source's `source.js`
(responsive-video reframing, image lightbox/PhotoSwipe, nav "more" dropdown,
infinite scroll, responsive tables) is progressive enhancement. The builder ships
**no JS**, which is fully compliant. Add scripts only for enhancements, bundled to
`assets/built/source.js` and referenced via `{{asset "built/source.js"}}` before
`{{ghost_foot}}`.

## Validation

Ghost runs `gscan` on every theme upload and blocks fatal errors. To check locally:
`npm install -g gscan` then `gscan /path/to/theme` (or `gscan -z theme.zip`). The
builder's `upload_theme` tool surfaces Ghost's returned `errors`/`warnings`.

---

## Patterns

Small recipes that stay inside the previewable subset and avoid the traps above.

**Featured-first feed (no `from=`).** `from=` is rejected, so you can't run a second
loop that skips the first post. Instead run one loop and style the first card with
CSS `:first-child`:

```handlebars
<section class="post-feed">
{{#foreach posts}}
  <article class="post-card">…</article>
{{/foreach}}
</section>
```
```css
.post-card:first-child { /* hero treatment: larger, full-width, etc. */ }
```

**Feature image with a fallback.** Posts without a `feature_image` shouldn't leave a
broken-looking card. Render the image when present, and a branded solid block (use
the accent token) otherwise:

```handlebars
{{#if feature_image}}
  <img class="post-card-image" src="{{feature_image}}" alt="{{title}}">
{{else}}
  <div class="post-card-image post-card-image--placeholder"></div>
{{/if}}
```
```css
.post-card-image--placeholder { aspect-ratio: 16 / 9; background: var(--accent); }
```

**Custom layout (`default_template`).** Must contain `{{{body}}}` (rejected without
it). The stylesheet `<link>`, `{{ghost_head}}`, and `{{ghost_foot}}` are auto-injected
if you leave them out, but include them yourself for clarity — and remember a bare
`{{asset "built/screen.css"}}` is just a URL, so it must live inside a `<link>`.

## What the builder generates vs. leaves to the model

- **Generates:** `default`/`index`/`post`/`page`, a `package.json` with the fields
  above, and the token + grid-canvas base CSS. Always valid and previewable.
- **Model supplies:** the design (CSS via `styles`) and, optionally, template
  overrides — which must stay inside the previewable subset above. Start by calling
  `extract_brand` on the customer's live site for a palette/fonts/logo to match, and
  use `get_theme_structure` to target real selectors on the rendered page rather than
  guessing.
- **Left to the live blog:** members/Portal, navigation, pagination, search,
  responsive image sizing, and full Koenig card styling (via `card_assets`) — all of
  which work once the theme is activated, even though the local preview can't show
  them.
