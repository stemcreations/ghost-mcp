"""The runnable Ghost Styling MCP server.

Run it interactively during development::

    uv run fastmcp dev src/ghost_mcp/server.py

or over stdio via the installed entry point::

    uv run ghost-mcp
"""

from fastmcp import FastMCP

from ghost_mcp.tools import register_all

#: Sent to the model on initialize, so the theming workflow and its hard-won gotchas
#: are always in context instead of being rediscovered by trial and error.
INSTRUCTIONS = """\
This server styles and manages a Ghost blog. Its differentiator is *vision*: it can
read a live site's rendered HTML/CSS so you style against real selectors, not guesses.

Recommended order for theming a site (follow it unless the user steers otherwise):

1. Inspect the brand. Call extract_brand(site_url) on the customer's live product or
   marketing site to pull its palette, fonts, and logo (use get_theme_structure when
   you need the full rendered HTML/CSS). Match the brand; never invent a palette.
2. Confirm direction with the user before building: colours, fonts, light vs dark,
   and -- most importantly -- what the blog should convert readers toward (signup,
   demo, booking). That one answer shapes every CTA.
3. create_theme. Put site chrome (nav/header/footer) in default_template; put page
   bodies in index/post/page templates; put the design in styles (CSS).
4. preview_theme, then iterate. Open the returned URL.
5. update_branding and update_site_metadata so Ghost's own accent colour and SEO
   match the new theme.
6. upload_theme (it installs inactive). The user activates it in Ghost Admin; there
   is deliberately no activate tool.

Gotchas that will bite you otherwise:

- The stylesheet must sit inside a real <link>: {{asset "built/screen.css"}} only
  emits a URL, so a bare {{asset ...}} renders as visible text and loads no CSS. (The
  builder injects the <link> for default_template overrides that omit it.)
- Content templates must start with {{!< default}} to inherit the layout; the builder
  injects it if missing. A default_template must contain {{{body}}} or it's rejected.
- The local previewer renders only a subset of Ghost's Handlebars. {{date}}, {{#get}},
  {{navigation}}, {{pagination}} and other server-side helpers render BLANK in preview
  (they work once uploaded). Block params (as |x|) and from= are rejected outright --
  to feature the first post, use a CSS :first-child rule, not {{#foreach posts from=}}.
- Preview servers are ephemeral: each preview_theme call replaces the previous one, so
  older preview URLs stop working. Always use the most recent URL.
- get_theme_structure only fetches PUBLIC http(s) URLs; it refuses localhost/private
  hosts by design.

See docs/theme-conventions.md for the full template/CSS contract.
"""


def create_server() -> FastMCP:
    """Build a fully wired server instance."""
    mcp = FastMCP(name="Ghost Styling MCP", instructions=INSTRUCTIONS)
    register_all(mcp)
    return mcp


#: Module-level server so ``fastmcp run`` / ``fastmcp dev`` can discover it.
mcp = create_server()


def main() -> None:
    """Entry point for the ``ghost-mcp`` command; serves over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
