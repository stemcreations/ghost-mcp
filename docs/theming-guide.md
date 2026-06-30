# Getting the most out of the Ghost Styling MCP

A best-practices guide for using this server to **theme a Ghost blog to match a brand**,
and to keep its design, colours, and SEO aligned with the rest of your product. Theming
is the primary job; content, tags, members, and newsletters round it out.

> New here? You don't need to read the whole thing. Skim **How you use it** and **The
> golden path**, then just ask your assistant to start. The rest is reference.

---

## How you use it

You don't call these tools yourself. You talk to your AI assistant in plain language,
and it translates your intent into the right tool calls. "Using the MCP" means
*describing what you want done to the blog*:

- *"Theme my blog to match acme.com"* → it runs the whole theming flow below.
- *"Make my blog's accent colour match my site and fix the SEO description"* →
  `update_branding` + `update_site_metadata`.
- *"Show me my latest drafts"* → `list_posts`.

**The one question that shapes everything:** *what should the blog convert readers
toward* — signup, demo, booking, purchase? Decide this first. It drives every
call-to-action in the theme, so answering it up front saves a redesign later.

---

## The golden path (theming a blog end-to-end)

Follow this order unless you have a reason not to. It's the sequence the server is
built around, and each step feeds the next.

1. **Extract the brand.** Point the assistant at your live product or marketing site:
   *"Match my blog to https://yoursite.com."* It calls `extract_brand` to pull the real
   palette, fonts, and logo (and `get_theme_structure` for the full rendered HTML/CSS
   when it needs exact selectors). **Match the brand — never invent a palette.**
2. **Confirm direction before building.** Settle colours, fonts, light vs dark, and the
   conversion goal above. A 30-second confirmation here beats iterating on a built
   theme.
3. **Build the theme** (`create_theme`). Site chrome (nav/header/footer) goes in the
   layout; page bodies in the content templates; the design in CSS.
4. **Preview and iterate** (`preview_theme`). Open the returned URL in a browser and
   refine. This is a faithful *style* mockup — see [What the preview can and can't
   show](#what-the-preview-can-and-cant-show).
5. **Align Ghost's own branding and SEO** (`update_branding`, `update_site_metadata`)
   so the accent colour and metadata match the new theme.
6. **Upload it** (`upload_theme`). It installs **inactive** — your live site is
   untouched. You then activate it yourself in Ghost Admin (**Settings → Design**).
   Activation is deliberately manual; there is no activate tool.

---

## Design & colour best practices

- **Match, don't guess.** Always start from `extract_brand` on the real site. The whole
  point of this server is styling against real brand tokens and real selectors.
- **Accent colour.** Ghost injects `--ghost-accent-color` (from **Settings → Brand**)
  into the theme. Use it for links, buttons, and accents — `var(--ghost-accent-color,
  #15171a)` with a fallback — and set it to the brand colour with `update_branding` so
  Ghost's own UI matches too.
- **Fonts.** Ghost's font picker exposes `--gh-font-heading` and `--gh-font-body`.
  Consume them with system-font fallbacks so the Design panel "just works." Load only
  the web-font families you actually use.
- **Design tokens.** Put colours, type, and layout on `:root` as semantic custom
  properties rather than hardcoding values — it keeps the theme consistent and easy to
  retune.
- **Content-width "canvas."** Article bodies use a grid with `main`/`wide`/`full`
  columns so editor images can break out of the reading column. The builder sets this
  up for you; respect it in custom CSS.
- **Editor cards.** `{{content}}` emits Koenig `.kg-*` card markup; Ghost styles most
  of it automatically (`card_assets`). You only need to place the width classes.

For the complete CSS contract, see [theme-conventions.md](theme-conventions.md).

---

## SEO & metadata best practices

- **Set it with `update_site_metadata`:** site title and description, the search-snippet
  `meta_title`/`meta_description`, and the Open Graph and Twitter-card fields used when
  posts are shared. Good metadata helps the blog present and rank well.
- **Keep the blog aligned with the main site** — same voice, same brand — so it reads as
  part of the same product, not a bolt-on.
- **Theme side:** a valid theme keeps `{{ghost_head}}` in its layout (the builder
  ensures this). That tag is what emits SEO/meta/structured data and the accent colour,
  so never strip it.

---

## The rest of the surface (content, members, newsletters)

Theming is the headline, but the same "just ask" model covers the blog's content and
membership business:

- **Posts** — create/update/read/delete; new posts are **drafts** by default, and you
  get a `preview_url` to review before publishing.
- **Tags** — full CRUD; deleting a tag leaves its posts intact.
- **Members** — add and update members, set labels and newsletter subscriptions; filter
  lists with `status:paid`, `label:vip`, etc.
- **Newsletters** — create and configure them; retire one with `status:archived`.

Two deliberate limits: **members and newsletters have no delete** (the Ghost Admin API
has none — newsletters archive instead), and **themes never auto-activate**.

---

## What the preview can and can't show

`preview_theme` renders structure and CSS faithfully with sample content, but it's a
local approximation, not a running Ghost. Some standard, correct helpers are **live-only**
— they render **blank in preview, then work once the theme is uploaded**. That empty
preview is expected, not a bug. The main ones:

- `{{navigation}}` — the admin-managed header/footer menu (**Settings → Navigation**).
  **Prefer this over hardcoding menu links**, so the site owner controls them. Hardcode
  only when you deliberately want fixed links the post author shouldn't change (e.g.
  links to the main marketing site).
- `{{pagination}}`, `{{author}}`/`{{authors}}`, `{{date}}`, membership gates, and Ghost's
  data/query helpers.

So: style these, then confirm them on the live site after upload — don't avoid one just
because the preview can't display it.

---

## Gotchas worth knowing up front

- **Themes upload inactive.** You activate manually in Ghost Admin — by design.
- **Preview URLs are ephemeral.** Each `preview_theme` call replaces the previous server,
  so only the most recent URL works.
- **Vision is public-only.** `extract_brand`/`get_theme_structure` fetch public http(s)
  pages and refuse localhost/private hosts.
- **Stay in the previewable Handlebars subset** for generated templates — the builder
  rejects unsupported constructs at build time with a clear message and a suggested fix.

---

## Just say this to get started

- *"Theme my Ghost blog to match https://yoursite.com — it should push readers toward
  [signup / a demo / booking]."*
- *"Extract the brand from my site and show me what you found before building."*
- *"Update my blog's accent colour and SEO description to match my main site."*
- *"List my posts and themes so I can see the current state."*

The assistant will pick up from there, confirm direction with you, and walk the golden
path. When in doubt, ask it: *"What's the best way to use this to redesign my blog?"*

---

## Going deeper

- [theme-conventions.md](theme-conventions.md) — the full template hierarchy, required
  tags, previewable helper subset, `package.json`, and CSS conventions. Read this when
  you (or the model) need the authoritative rules for hand-written templates.
- [feature-roadmap.md](feature-roadmap.md) — what's planned next (pages, image upload,
  publishing posts as newsletter emails, tiers/offers/labels, navigation editing).
