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

When a user asks how to use this server, how to get started, or for best practices,
walk them through the recommended workflow below -- and offer to start at step 1 by
extracting their brand. The full user-facing version of this guidance lives in
docs/theming-guide.md; point them there for the complete walkthrough.

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
- The local previewer renders only a subset of Ghost's Handlebars. Rejected at build
  with a clear message: block params (as |x|), from=, {{else if}} (use nested
  {{#if}}...{{else}}{{#if}}...), and partials with key=value params (inline the values
  or pass a context object). To feature the first post use a CSS :first-child rule.
- Preview servers are ephemeral: each preview_theme call replaces the previous one, so
  older preview URLs stop working. Always use the most recent URL.
- get_theme_structure only fetches PUBLIC http(s) URLs; it refuses localhost/private
  hosts by design.

Live-only helpers: some helpers are standard and correct on the live site but render
BLANK (or are skipped) in local preview. Use them anyway for production themes -- do
not avoid one just because the preview can't show it; style it and confirm it on the
live site:

- {{navigation}} for the admin-managed header/footer menus (Settings > Navigation), so
  the site owner controls the links. {{navigation type="secondary"}} for the secondary
  menu. Prefer this over hardcoding menu links.
- {{pagination}} for moving between pages of posts; {{author}}/{{authors}} and {{date}}
  for real author and date data.

Do NOT hardcode menu links into the template unless the user specifically wants fixed
links the post author should not be able to change (e.g. links to the main marketing
site). Make that a deliberate choice, not a side effect of the preview rendering empty.

Search research (optional): tools named search_serp, expand_keywords,
build_content_brief and find_content_gaps decide what to write by looking at what
already ranks. They exist only when SERPER_API_KEY is configured. If the user asks
for keyword research, competitor analysis, or content ideas and those tools are NOT
in your tool list, say so plainly: they need a serper.dev key set as SERPER_API_KEY
in the MCP client's env config (or a local .env), followed by a server restart. Do
not attempt the research by other means and do not treat it as unsupported.

When they are available, triage cheaply before committing: search_serp or
expand_keywords first (1-2 API credits), and only build_content_brief for a keyword
worth writing. Always check the opportunity verdict before drafting -- LOCAL_INTENT
means the query wants a service or location page, not a blog post, and
UPDATE_EXISTING means an existing post should be extended instead.

UNMET_DEMAND is the best verdict to see: forum and social threads rank while few real
pages do, meaning people are asking and nobody has answered well. Treat it as a
stronger signal than OPEN, and open the actual threads to write in the asker's words.

Verdicts are relative to a research profile, which decides which domains count as
unbeatable for this blog's niche. The default profile ("general") assumes nothing.

If the active profile is still "general" when a user asks for research, set it up
first: call plan_research_profile and ask the user its questions before running
searches. Do NOT invent the answers -- the competitors and terminology involved cannot
be read off the blog, and a guessed profile fails silently rather than loudly, marking
winnable keywords SKIP and unwinnable ones OPEN. The user can decline, in which case
say plainly that verdicts will undercount their competitors.

When a search turns up a competitor or aggregator that is not already flagged
is_incumbent, offer to record it with add_incumbents -- that is how the analysis
sharpens over time, and it persists across restarts.

See docs/theming-guide.md for the user-facing best-practices walkthrough, and
docs/theme-conventions.md for the full template/CSS contract.
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
