# Feature roadmap

Implementation-ready specs for features not yet built, grounded in the Ghost Admin
API (`ghost-llms-full.txt`). Each entry lists the endpoint, the request/response
shape, the tools to add, and the gotchas.

Work order: **bugs before features.** The "Bugs / fixes" section below tracks defects
in already-shipped code (fixes to existing functions, not new capabilities) and is
cleared first. The feature tiers are then top-down: Tier 1 completes the content
workflow, Tier 2 adds the membership business, Tier 3 deepens the styling/vision
differentiator.

---

# Bugs / fixes (do first)

Defects in **already-shipped** code — fixes to existing functions, not new
capabilities. Distinct from the feature tiers below; clear these first. New bugs land
here as they're found.

## 1. Previewer `foreach` dropped Ghost's loop-position `@`-data — ✅ Fixed 2026-06-30

The `foreach` helper in `theme/preview.py` rendered each item with no loop-position
data, so `{{@index}}` / `{{@number}}` / `{{@first}}` / `{{@last}}` / `{{@even}}` /
`{{@odd}}` came out **blank in preview** even though they render live. A theme that
styles by loop position (a class on the first/last card, zebra striping) looked broken
locally while being correct on the real site. The prior workaround was to author the
loop with `{{#each}}`, whose `@`-data pybars3 does provide.

- **Fix:** wrap each rendered item in a pybars3 `Scope` carrying the `@`-data —
  `@index`/`@first`/`@last` natively, `@number`/`@even`/`@odd` via `overrides` —
  mirroring how pybars3's own `{{#each}}` works. (`@even` is true for 1-based even
  items, i.e. odd 0-based index, matching Ghost.)
- **Verified:** pybars3's `options["fn"]` accepts a `Scope` and `options["root"]` is
  present for block helpers (`Compiler` sets both); the limit/`to` slicing still
  applies, and `@last` is computed against the rendered slice. Covered by
  `tests/test_preview.py::test_foreach_exposes_loop_position_data`.

---

## How to add a tool group (recap)

Per `CLAUDE.md`: put logic in a service function, expose it through a thin
`tools/<name>.py` with a `register(mcp)`, and call it from `register_all` in
`tools/__init__.py`. For simple resources that fit the uniform envelope, follow
`tools/tags.py` / `tools/members.py`: a `register(mcp)` plus pure `_fields`/`_summary`
helpers, wrapping `admin_client().browse/read/add/edit/delete`. Unit-test the pure
helpers (see `tests/test_members.py`). For endpoints that break the envelope (images,
post-as-email), add a service function in `admin/` like `admin/themes.py`.

The capability table (`ghost-llms-full.txt` line 442) is authoritative for which verbs
an endpoint supports. Do not expose a verb the table omits.

---

# Tier 1 — completes the content workflow

✅ **Implemented 2026-06-30.** Pages (`admin/pages.py` + `tools/pages.py`), image upload
(`admin/images.py` + `tools/images.py`), and `publish_post` (post-as-newsletter-email,
extending `admin/posts.py` + `tools/posts.py`) all shipped with unit tests. The specs
below are kept for reference.

## 1. Pages (`tools/pages.py`)

Pages are posts that live outside the feed (about, contact, …). `/pages/` supports
Browse/Read/Edit/Add/Copy/Delete and uses the **identical** shape to posts, including
`?source=html` for HTML bodies and `updated_at` collision checks on edit.

- **Endpoint:** `/pages/` (same envelope as `/posts/`).
- **Build:** copy `admin/posts.py` to `admin/pages.py` and `tools/posts.py` to
  `tools/pages.py`, swapping the resource name `posts` -> `pages`. The previewer
  already renders `page.hbs`, so themed pages and managed pages line up.
- **Tools:** `list_pages`, `get_page`, `create_page`, `update_page`, `delete_page`.
- **Gotchas:** pages have no `tags`/feed semantics but otherwise share post fields
  (`title`, `html`, `status`, `feature_image`, `meta_*`, `slug`). Reuse the post
  field builder; just drop `tags` if you want a tighter surface.
- **Effort:** trivial (mechanical copy of an existing, tested module).

## 2. Image upload (`admin/images.py` + `tools/images.py`)

The single biggest enabler: today `feature_image`, `logo`, `icon`, and newsletter
`header_image` can only point at an existing URL. Upload lets the model put real
images on posts and into branding.

- **Endpoint:** `POST /admin/images/upload/` (multipart; line 467).
- **Form fields:**
  - `file`: the image bytes (WEBP, JPEG, GIF, PNG, SVG; ICO also for icons).
  - `purpose` (optional, default `image`): `image` | `profile_image` | `icon`.
    `profile_image` and `icon` must be square; `icon` also accepts ICO.
  - `ref` (optional): echoed back as-is; handy for find/replace of local paths.
- **Response:** `{ "images": [ { "url": "...", "ref": "..." } ] }` (note the `images`
  envelope; unwrap the first item with `_single`).
- **Client note:** `GhostAdminClient.post` accepts `files=`. Send the non-file fields
  as multipart form fields by giving them a `(None, value)` tuple, no client change
  needed:
  ```python
  files = {
      "file": (filename, image_bytes, content_type),
      "purpose": (None, purpose),
      "ref": (None, ref),
  }
  client.post("/images/upload/", files=files)
  ```
- **Service:** `admin/images.py::upload_image(client, image_bytes, *, filename, purpose="image", ref=None) -> str` returning the URL (unwrap via `_single(..., "images")["url"]`).
- **Tools (`tools/images.py`):**
  - `upload_image(file_path, purpose="image")` -> `{ "url": ... }`. Read the bytes,
    sniff content type from the extension.
  - `upload_image_from_url(source_url, purpose="image")` -> `{ "url": ... }`. Fetch
    the source under the **same SSRF guard** as vision (`_validate_public_url`,
    size cap), then upload. Reuse `ghost_mcp.vision.structure` helpers.
- **Follow-on:** once this lands, `create_post`/`update_post`, `update_branding`
  (logo/icon), and `update_newsletter` (header_image) can accept a local path and
  upload it, instead of requiring a hosted URL.
- **Gotchas:** validate `purpose` against the three allowed values; surface Ghost's
  format/size errors (`GhostAPIError`) verbatim.

## 3. Publish a post as a newsletter email (extend `tools/posts.py`)

Connects posts + newsletters + members into the actual act of publishing. A post is
emailed **iff** an active newsletter is named when it is published or scheduled.

- **Endpoint:** `PUT /admin/posts/{id}/?newsletter=<slug>&email_segment=<nql>`
  (line 1923). The body is the normal post update (set `status` to `published` or
  `scheduled`).
- **Params:**
  - `newsletter`: the newsletter **slug** (from `list_newsletters`). Required to send.
  - `email_segment` (optional, default `all`): NQL over members. Common values:
    `status:free`, `status:-free` (paid), `all`.
- **Build:** thread two optional args through `admin/posts.py::update_post` into the
  `params` it already passes to `client.edit`, e.g.
  `params={"source": "html", "newsletter": slug, "email_segment": segment}`.
- **Tools:** add `newsletter_slug` and `email_segment` params to `update_post` (and
  optionally `create_post`), or add a dedicated `publish_post(post_id, newsletter_slug, email_segment="all")` that sets `status="published"` and passes the params. A
  dedicated tool reads more clearly and is safer (explicit intent to send email).
- **Scheduling:** set `status="scheduled"` + a future `published_at` (line 1888);
  Ghost sends the email automatically at that time. `update_post` already supplies
  `updated_at` for the collision check, so this is just two more fields.
- **Gotchas:** sending email is **outward-facing and irreversible** — gate it behind
  explicit user intent (a separate `publish_post` tool, not a silent side effect of
  `update_post`). An archived/invalid newsletter slug means no email is sent.

---

# Tier 2 — membership business

✅ **Implemented 2026-06-30.** Tiers, offers, labels, and users (read-only) shipped as
`tools/tiers.py`, `tools/offers.py`, `tools/labels.py`, and `tools/users.py`, each with
unit tests. The specs below are kept for reference.

Simple envelope resources; build like `tools/tags.py`. The capability table allows
Browse/Read/Edit/Add for tiers and offers (no delete), and adds Delete for labels.

- **Tiers** (`/tiers/`): paid plans. Fields include `name`, `description`,
  `monthly_price`, `yearly_price`, `currency`, `benefits` (list), `visibility`,
  `welcome_page_url`, `trial_days`, `active`. Tools: `list_tiers`, `get_tier`,
  `create_tier`, `update_tier`. No delete (archive via `active:false`).
- **Offers** (`/offers/`): discount codes against a tier. Required fields (line 1296):
  `name`, `code`, `cadence`, `duration`, `amount`, `tier.id`, `type`
  (`percent`|`fixed`). Tools: `list_offers`, `get_offer`, `create_offer`,
  `update_offer`.
- **Labels** (`/labels/`): member segmentation, pairs with the members tools. Shape is
  `{id, name, slug}`. Browse/Read/Edit/Add/**Delete**. Tools: full CRUD.
- **Users / authors** (`/users/`): **read-only** (Browse/Read). Needed to attribute
  posts. Tools: `list_users`, `get_user`. Do not attempt write (the API forbids it
  for integrations).

---

# Tier 3 — deepen the styling / vision differentiator

✅ **Mostly implemented 2026-06-30.** Navigation editing, restyle, contrast checks, and
guarded activation shipped with unit tests; only preview screenshots remain (deferred,
see below). The specs are kept for reference.

- **Navigation editing.** ✅ Done. `update_navigation(primary, secondary)` in
  `tools/settings.py` writes the `navigation`/`secondary_navigation` settings via
  `settings_api.update_settings`, and `extract_brand` reads a source site's menus
  (splitting membership links out). Closes the loop: the theme styles the nav, this
  sets its items.
- **Restyle the active theme.** ✅ Done. `restyle_theme(name, css, mode="append")` in
  `tools/theme.py` downloads the named theme, rewrites its
  `assets/built/screen.css` (append, or `mode="replace"`), and re-uploads it. The pure
  zip-rewrite is `theme/builder.py::restyle_archive` (unit-tested). Re-upload doesn't
  activate, but restyling the *active* theme changes the live look.
- **Palette contrast checks.** ✅ Done. `vision/contrast.py` computes the pure-Python
  WCAG contrast ratio and AA/AAA levels; exposed as `check_contrast(foreground,
  background)` in `tools/vision.py` so generated themes don't ship unreadable
  text-on-accent.
- **Guarded theme activation.** ✅ Done. `activate_theme(name)` in `tools/theme.py` is a
  distinct, clearly-labelled tool over `admin/themes.py::activate_theme`; its docstring
  instructs the model to call it only on explicit user instruction, never as a
  follow-on to generate/upload/restyle (mirrors the post-email caution).
- **Preview screenshots (architectural decision).** ⏳ Deferred. Render the local
  preview to a PNG so the model can *see* layout/spacing/contrast instead of building
  blind. High impact, but needs a headless browser (Playwright/Chromium), which departs
  from this repo's deliberate pure-Python, no-binaries stance. Decide that tradeoff
  before building; if adopted, isolate it behind an optional extra so the core stays
  pure.

---

# Out of scope / deliberate constraints

- **No delete for members or newsletters** — the Admin API has none (capability table
  lines 448, 450). Newsletters retire via `status:archived`.
- **No *auto*-activation of themes** — activation is exposed as a distinct, guarded
  `activate_theme` tool (Tier 3), but it must only run on explicit user instruction,
  never as a silent follow-on to generate/upload/restyle. Upload still installs
  inactive.
- **Outward-facing actions** (sending a post email, activating a theme, publishing)
  require explicit user intent, never a silent side effect of an edit tool.
- **Pure Python** — prefer solutions that don't pull in Node or browser binaries; if
  one truly needs them (screenshots), gate it behind an optional install.
