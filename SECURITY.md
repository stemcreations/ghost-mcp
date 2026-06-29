# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — use GitHub's
**Security → Advisories → "Report a vulnerability"** on this repository rather than
opening a public issue. Include reproduction steps and the impact you observed.
You'll get an acknowledgement and a fix or mitigation as fast as is practical.

## Security model

Ghost MCP is a **local, single-user** server. It runs over stdio, launched by your
MCP client (e.g. Claude Desktop), and talks to **one** Ghost site with **one** staff
token. It is not a multi-tenant or network-exposed service, and the credential lives
on your own machine.

### Controls in place

- **The staff token is never returned by any tool.** No tool exposes the credential
  or raw environment, so even a fully prompt-injected model cannot read or exfiltrate
  it. The blast radius is *actions on your own blog*, not credential theft.
- **Settings writes are allow-listed.** The settings tools can only change brand and
  SEO metadata; Stripe/members/`is_private`/`password` and similar settings cannot be
  touched through the tools, and the read path filters out secret-bearing keys.
- **Activating a theme is deliberately not a tool.** It changes the live site, so it
  stays a manual step.
- **The vision fetcher is SSRF-guarded.** It refuses non-`http(s)` URLs and
  private/loopback/link-local/metadata hosts (including across redirects), and caps
  the response size. It sends no `Authorization` header, so it can't leak the token.
- **Credential hygiene:** the token signs a short-lived (5-minute) JWT per request,
  TLS verification is on by default, the token is masked in `Settings`' repr, and a
  warning is emitted if `GHOST_ADMIN_URL` is not HTTPS.

### The main trust boundary: untrusted content (prompt injection)

Some tools pull in content you don't control — a rendered web page via
`get_theme_structure`, or a post's HTML via `get_post` — and hand it to the model.
**Treat that content as untrusted input.** A malicious page or post can contain
instructions ("prompt injection") that try to steer the model into using its tools
to delete content, publish spam, or change site settings.

Because no tool exposes the token, the worst case is unwanted *actions on your own
blog*, not a stolen credential. To stay safe:

- Be cautious pointing the tools at pages or posts you don't trust.
- Review destructive or publishing actions — `delete_post`, `delete_tag`,
  `delete_theme`, and `create_post`/`update_post` with `status="published"`.
- Keep `activate_theme` a manual step (it already is).

## Credentials

`GHOST_ADMIN_URL` and `GHOST_STAFF_ACCESS_TOKEN` are supplied via your MCP client's
`env` block or a local `.env` file. `.env` is gitignored; never commit real
credentials. Use a staff token scoped to the role you actually need.

## Dependencies

Dependencies are pinned with hashes in `uv.lock`. Keep them up to date —
`pybars3` (theme preview rendering) and `beautifulsoup4` (HTML parsing of fetched
pages) process untrusted input, so prefer current versions.
