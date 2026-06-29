# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ghost MCP — a [FastMCP](https://github.com/jlowin/fastmcp) (Python) server that exposes the
[Ghost Admin API](https://docs.ghost.org/admin-api) as MCP tools, so an MCP client can read and
manage a Ghost site's content.

The project is at its earliest stage: the dependencies and a Python 3.13 venv exist, but **no
server code has been written yet**. The sections below describe the intended toolchain and the
architecture any implementation must follow, grounded in the installed dependencies and the
vendored API spec.

## Toolchain & commands

- Python **3.13** in `.venv` (interpreter base: `C:\Users\WesCarothers\python3.13`).
- Package manager: **uv** (user-local at `~/.local/bin/uv.exe`, no admin). uv replaces pip — use
  `uv add` / `uv run`, never `pip install`.
- Already installed in the venv: `fastmcp` 3.x, `mcp`, `httpx` (+ `httpx-sse`), `pyjwt`.

There is **no `pyproject.toml`, lockfile, test suite, or linter yet** — formalize dependencies with
`uv init` + `uv add fastmcp httpx pyjwt` before relying on reproducible installs.

```powershell
.venv\Scripts\Activate.ps1        # activate the existing venv (PowerShell)
fastmcp run server.py             # run the server (once server.py exists)
fastmcp dev server.py             # run with the MCP Inspector for interactive testing
uv run fastmcp run server.py      # equivalent via uv without activating
```

## Architecture

Two things make this codebase non-obvious; both must be reproduced correctly for any tool to work.

### 1. Authentication — JWT minted from a Staff Access Token

The Ghost Admin API does **not** accept the staff token directly. The token in
`.env` (`GHOST_STAFF_ACCESS_TOKEN`) is an `id:secret` pair, and every request needs a fresh,
short-lived JWT signed from it (this is why `pyjwt` is a dependency):

1. Split the token on `:` into `id` and `secret`.
2. **Hex-decode** the `secret` into raw bytes — sign with the bytes, not the hex string.
3. Sign HS256 with JWT header `{ "alg": "HS256", "typ": "JWT", "kid": <id> }` and payload
   `{ "aud": "/admin/", "iat": <now>, "exp": <now + 300> }` (exp is **max 5 minutes** out; `iat`/`exp`
   are seconds since epoch).
4. Send it on every call as `Authorization: Ghost <jwt>` together with an
   `Accept-Version: v{major}.{minor}` header.

Tokens are single-use / short-lived, so mint a JWT per request (or cache within the 5-minute window)
rather than once at startup.

### 2. Request/response shape (Ghost Admin API)

- Base URL: `https://{admin_domain}/ghost/api/admin/` — the admin domain may differ from the public
  site domain. **This is not yet in `.env`**; a config var (e.g. `GHOST_ADMIN_URL`) must be added.
- HTTP calls go through `httpx`.
- Resources are wrapped: `{ "<resource_type>": [ { ... } ], "meta": { ... } }`, where
  `<resource_type>` matches the URL segment. Exceptions returned unwrapped: `/site/` and `/settings/`.
- POST/PUT bodies use the same wrapped envelope and require `Content-Type: application/json`.
- Browse endpoints paginate (15/page default) via `meta.pagination`, and accept `include`, `fields`,
  `filter`, `limit`, `page`, `order` query params — values must be URL-encoded.

### Mapping to MCP

Each Ghost endpoint becomes a FastMCP tool (`@mcp.tool`). Keep auth/HTTP in one shared client layer
so individual tools only describe their endpoint, params, and payload.

## Reference material

`ghost-llms-full.txt` (~728 KB) is the **complete vendored Ghost Admin API documentation** —
endpoints, fields, filtering, error formats, and auth. Treat it as the authoritative spec when
building or wrapping tools; consult it instead of guessing endpoint shapes. It is reference data, not
code.

## Secrets

`.env` contains a real `GHOST_STAFF_ACCESS_TOKEN` and is gitignored (`.env.example` documents the
variable). Never read its value into committed code, logs, or output.
