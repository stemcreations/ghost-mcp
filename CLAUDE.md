# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [FastMCP](https://github.com/jlowin/fastmcp) (Python) MCP server for **styling and
managing a Ghost blog**. The differentiator is *vision*: it fetches the live blog's
rendered HTML + CSS so the model can write CSS against real selectors instead of
guessing. Vision and styling ship first; the authenticated client is generic so the
full Ghost Admin API (posts, members, tags, …) follows as thin tool wrappers.

This is a public repo. Keep code clean, typed, and documented; keep the README
current for contributors.

## Commands

uv manages everything (no global pip, no manual venv). If `uv` isn't found in a
fresh shell, it's at `~/.local/bin/uv.exe`; open a new terminal or prepend it to
PATH.

```bash
uv sync                                  # install deps + the package (editable)
uv run python scripts/check_connection.py  # smoke-test live Admin API credentials
uv run fastmcp dev src/ghost_mcp/server.py # run with the MCP Inspector
uv run ghost-mcp                         # run the server over stdio
uv run ruff format                       # format
uv run ruff check                        # lint
uv run pytest                            # run all tests
uv run pytest tests/test_auth.py::test_audience_is_admin  # run a single test
```

## Architecture

Layered package under `src/ghost_mcp/`, each layer with one responsibility:

- `config.py`: load/validate env (`GHOST_ADMIN_URL`, `GHOST_STAFF_ACCESS_TOKEN`, optional `GHOST_API_VERSION`).
- `errors.py`: the `GhostError` hierarchy (`ConfigError`, `GhostAPIError`).
- `admin/`: authenticated Admin API: `auth.py` mints JWTs, `client.py` is the HTTP client.
- `vision/`: `structure.py` fetches the public page + CSS (no auth).
- `tools/`: thin MCP wrappers; one module per domain, each exposing `register(mcp)`.
- `server.py`: builds the FastMCP server and wires tools; `main()` is the entry point.

**The core convention:** business logic lives in a service module (`admin/`,
`vision/`) as a plain, testable function; the `tools/` wrapper only adapts it to MCP.
To add a tool group: write+test the logic, add `tools/<name>.py` with `register(mcp)`,
and call it from `register_all` in `tools/__init__.py`.

### Two load-bearing, non-obvious details

1. **Auth (`admin/auth.py`).** Ghost's Admin API rejects the staff token directly.
   Each request needs a fresh JWT: split the `id:secret` token on `:`, **hex-decode
   the secret to bytes** (sign with the bytes, not the hex string), HS256, header
   `kid=<id>`, payload `aud="/admin/"`, `exp` ≤ 5 min. Sent as `Authorization: Ghost
   <jwt>` with `Accept-Version: v5.0`.

2. **Uniform API shape (`admin/client.py`).** Every resource uses the same envelope:
   `{ "<resource>": [ {...} ], "meta": {...} }` (`/site/` and `/settings/` are
   unwrapped exceptions). That uniformity is why `browse/read/add/edit/delete` are
   generic over a `resource` name rather than written per-resource.

## Conventions

- Type-hint everything; target Python 3.13.
- **Docstrings go inside functions** (PEP 257): FastMCP reads a tool's `__doc__` to
  describe it to the model, so a comment above `def` would be invisible. Keep
  function docstrings concise; put longer context in the module docstring. Write them
  for humans reading the source.
- Raise `GhostError` subclasses, never bare exceptions, for expected failure modes.
- Pure Python only; see the README for why no Node/TypeScript layer is needed.

## Reference material

`ghost-llms-full.txt` (~728 KB, gitignored) is the complete Ghost Admin API
documentation: endpoints, fields, filtering, errors, auth. Treat it as the
authoritative spec when adding tools; consult it instead of guessing endpoint shapes.
`handoffdoc.md` (gitignored) holds the project's design rationale and scope decisions.

## Secrets

`.env` holds a real `GHOST_STAFF_ACCESS_TOKEN` and is gitignored (`.env.example`
documents the variables). Never copy its value into committed code, logs, or output.
