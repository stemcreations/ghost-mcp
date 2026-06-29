# Ghost Styling MCP

An [MCP](https://modelcontextprotocol.io) server for **styling and managing a
Ghost blog**.

Most Ghost integrations manage content. This one starts somewhere no other public
Ghost MCP does — changing how the blog *looks* — and solves the problem that makes
AI-driven styling hard: the model can't see the rendered page. The server gives it
**structural sight** (the live markup and CSS) so it can write CSS that targets
real selectors instead of guessing.

Styling and vision come first. The authenticated client underneath is generic, so
the rest of the Ghost Admin API (posts, members, tags, and the other resources)
will follow as thin tool wrappers, growing this into a full management server.

## Status

Working: auth, vision, theme generation/preview/upload, and site settings. Roadmap:

- [x] Authenticated Admin API client (generic browse/read/add/edit/delete)
- [x] **Vision** — `get_theme_structure` fetches the live page's markup + CSS
- [x] **Themes** — generate, preview locally, upload, list, and download themes
- [x] **Site settings** — read/update brand + SEO metadata (title, description, accent, meta/OG/Twitter)
- [ ] **Management** — posts, members, newsletters, tags, … as CRUD tools (next)

## Tools

The server exposes these tools to the model:

**Vision**
- `get_theme_structure` — fetch a live page's HTML skeleton and linked CSS, so styling targets selectors that actually exist.

**Themes**
- `create_theme` — generate a complete, valid, previewable theme from a CSS design (and optional template overrides).
- `preview_theme` — render a theme locally and serve it on localhost to review before publishing.
- `upload_theme` — package and upload a theme; it installs **inactive**, so the live site is untouched.
- `list_themes` — list installed themes and which one is active.
- `download_theme` — download an installed theme's source as a zip.

**Site settings**
- `get_site_settings` — read brand and SEO settings.
- `update_site_metadata` — site title/description plus SEO and social metadata (`meta_*`, Open Graph, Twitter cards).
- `update_branding` — the brand accent colour.

Activating a theme is intentionally **not** a tool — it changes the live site, so it stays a manual step.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A Ghost site and a **staff access token** (from your user profile page in Ghost
  Admin). Site-wide styling and management need a token with the **Owner or Admin**
  role.

## Setup

```bash
git clone https://github.com/stemcreations/ghost-mcp.git && cd ghost-mcp
uv sync                  # creates .venv and installs everything
```

The server reads its configuration from environment variables:

| Variable | Required | Example |
|----------|----------|---------|
| `GHOST_ADMIN_URL` | yes | `https://yourblog.example.com` |
| `GHOST_STAFF_ACCESS_TOKEN` | yes | `<id>:<secret>` (from your Ghost user profile) |
| `GHOST_API_VERSION` | no | `v6.0` (default; match your Ghost major version) |

Provide them **either** way:

- **In your MCP client** — put them in the server's `env` block (see [Running](#running)). No `.env` file is needed; this is the usual setup for Claude Desktop.
- **In a local `.env`** — handy for development and the connection check: `cp .env.example .env` and fill it in. (If both are set, the client's `env` values win.)

Confirm the credentials reach your site:

```bash
uv run python scripts/check_connection.py
```

## Running

Interactively, with the MCP Inspector:

```bash
uv run fastmcp dev src/ghost_mcp/server.py
```

In Claude Desktop, add to your MCP servers config — put your credentials in the
`env` block and no `.env` file is needed:

```json
{
  "mcpServers": {
    "ghost": {
      "command": "uv",
      "args": ["run", "ghost-mcp"],
      "cwd": "/absolute/path/to/ghost-mcp",
      "env": {
        "GHOST_ADMIN_URL": "https://yourblog.example.com",
        "GHOST_STAFF_ACCESS_TOKEN": "<id>:<secret>",
        "GHOST_API_VERSION": "v6.0"
      }
    }
  }
}
```

## Authentication, briefly

Ghost's Admin API never takes the token directly. Each request carries a JWT signed
from the staff token (`id:secret`): split on the colon, hex-decode the secret, sign
HS256 with a five-minute expiry. `ghost_mcp.admin.auth` handles this for you.

Site-wide styling (code injection via `/settings/`) requires the **Owner or Admin**
role; a standard integration key cannot reach those endpoints.

## Architecture

The package is layered so each piece has one job:

| Layer  | Module             | Responsibility                                        |
|--------|--------------------|-------------------------------------------------------|
| Config | `ghost_mcp.config` | Load and validate environment configuration.          |
| Errors | `ghost_mcp.errors` | The shared `GhostError` exception hierarchy.          |
| Admin  | `ghost_mcp.admin`  | Authenticated Admin API: token signing, generic client, theme + settings helpers. |
| Vision | `ghost_mcp.vision` | Fetch the public rendered page + CSS (no auth).       |
| Themes | `ghost_mcp.theme`  | Generate, locally preview, and package themes.        |
| Tools  | `ghost_mcp.tools`  | Thin MCP wrappers over the layers above.              |
| Server | `ghost_mcp.server` | Assemble the layers into a runnable server.           |

The Admin API is uniform — every resource shares the same browse/read/add/edit/
delete shape — so `GhostAdminClient` implements those operations generically. A new
resource is a thin tool module, not a new subsystem.

This server is intentionally **pure Python**. Ghost's own tooling is JavaScript, but
nothing here needs it: styling deals in CSS strings and theme zips, and post content
can be sent as HTML via the Admin API's `?source=html` conversion rather than
converting to Lexical client-side.

## Contributing

The most important convention: **put logic in a service module (`admin/`,
`vision/`, `theme/`) as a plain, typed, testable function, then expose it through a
thin wrapper in `tools/`.** Tools adapt and shape data; they don't hold business logic.

To add a group of tools:

1. Write the logic as a plain function in the relevant service module, and test it.
2. Add `tools/<name>.py` with a `register(mcp)` function that wraps it.
3. Call your `register` from `register_all` in `tools/__init__.py`.

Conventions:

- Type-hint everything.
- Docstrings go *inside* functions (FastMCP reads them to describe tools to the
  model). Keep them concise; put longer context in the module docstring.
- Write docstrings for people reading the source — clear, no implementation noise.

Before opening a PR:

```bash
uv run ruff format       # format
uv run ruff check        # lint
uv run pytest            # test
```

Or install the git hook to run all three automatically before each commit:

```bash
uv run pre-commit install
```

## Security

Ghost MCP runs locally and never exposes your staff token through any tool. See
[SECURITY.md](SECURITY.md) for the security model, the prompt-injection trust
boundary, and how to report a vulnerability.

## License

MIT — see [LICENSE](LICENSE).
