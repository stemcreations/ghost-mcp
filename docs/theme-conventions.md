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
| `{{asset "built/screen.css"}}` | in `<head>` | Stylesheet link, with cache-busting. |
| `{{body_class}}` | on `<body>` | Context classes (`post-template`, `tag-template`, …). |
| `{{{body}}}` | in `<body>` | Where the child template is injected (triple-stache = unescaped). |
| `<html lang="{{@site.locale}}">` | root | Site locale. |

Omitting `{{ghost_head}}` or `{{ghost_foot}}` is a `gscan` error and breaks SEO,
the accent color, members, and card rendering.

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
| `{{#if x}}` / `{{#unless x}}` | Truthiness blocks. |
| `{{#foreach items}}…{{else}}…{{/foreach}}` | Loop over a list already in context (`posts`). |
| `{{#post}}` / `{{#page}}` | Enter the post/page object's context. |
| `{{> "partials/name"}}` | Partials loaded from `partials/`. |
| Bare fields | `{{title}}`, `{{url}}`, `{{excerpt}}`, `{{feature_image}}`, `{{content}}`. |
| `{{asset "path"}}` | Returns `/assets/path`. |
| `{{img_url x size="m"}}` | Valid on live Ghost; previewer returns the URL unchanged (size/format ignored). |
| `@site`, `@custom`, `@page` | Data globals from `default_sample()`. |

**Not supported by the previewer — keep these out of generated templates** (they all
appear throughout Source, which is why Source itself is *not* previewable by this
tool — use it as a reference for structure and class names, never copy-paste):

- **Block params:** `{{#get … as |recent|}}`, `{{#foreach posts as |p|}}`. The
  builder **rejects** block params (`_ensure_previewable`) outright.
- **Server-side data/flow helpers:** `{{#get}}` (DB queries), `{{#match}}`,
  `{{#is}}`, `{{#has}}`, `{{#foreach posts from="5"}}`, `{{date format=…}}`,
  `{{social_url}}`, `{{navigation}}`, `{{pagination}}`, `{{t}}` (i18n),
  `{{@config.*}}`, `{{recommendations}}`, `{{comments}}`.
- **Loop `@`-data not stubbed:** `@number`, `@index`, `@first`, `@last`.

These render fine on a live Ghost but will error or render blank locally. If a theme
needs them, upload and verify on the live site instead of relying on the preview.

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

- `{{navigation}}` — primary menu (Settings → Navigation), rendered from a preset
  partial unless you override `navigation.hbs`.
- `{{navigation type="secondary"}}` — secondary/footer menu.
- Logo/home links point to `{{@site.url}}`.

Both are server-side helpers — not previewable locally.

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

## What the builder generates vs. leaves to the model

- **Generates:** `default`/`index`/`post`/`page`, a `package.json` with the fields
  above, and the token + grid-canvas base CSS. Always valid and previewable.
- **Model supplies:** the design (CSS via `styles`) and, optionally, template
  overrides — which must stay inside the previewable subset above. Use the
  `get_theme_structure` vision tool to target real selectors on the rendered page
  rather than guessing.
- **Left to the live blog:** members/Portal, navigation, pagination, search,
  responsive image sizing, and full Koenig card styling (via `card_assets`) — all of
  which work once the theme is activated, even though the local preview can't show
  them.
