"""User-triggerable prompts that kick off a guided workflow.

A prompt is something the user invokes (it isn't called by the model like a tool);
it returns a message that steers the model through a multi-step flow. ``theme-a-site``
encodes the brand-first theming order so a user can start the whole build with one
action instead of the model rediscovering the steps.
"""

from fastmcp import FastMCP

from ghost_mcp.config import serper_api_key
from ghost_mcp.research.interview import INTERVIEW

_SET_UP_RESEARCH = """\
You are setting up search research for this blog, so topic choices rest on what
already ranks instead of on guesses.

Start by calling plan_research_profile, then interview the user with the questions
below. Ask them conversationally, a few at a time -- not as a form -- and do not answer
any of them yourself. The domains involved are specific to this business and cannot be
read off the blog.

{questions}

Why this matters enough to ask: a profile decides which domains count as unbeatable,
and a wrong one fails silently. Keywords the user could win come back as SKIP, and ones
owned by competitors the profile never heard of come back as OPEN. Nothing in the
output shows that it was guessed.

When they have answered: summarise it back, get a clear yes, then call
create_research_profile (competitors and SERP regulars as domains, the unbeatable ones
as dominant_domains) followed by set_research_profile. Finish by running search_serp on
3-5 seed keywords built from the user's OWN terminology and showing which are OPEN,
CONTESTED or SKIP -- do not draft anything until they pick one.

Treat the profile as a starting point: whenever a search turns up a domain it missed,
offer to record it with add_incumbents.
"""

_NO_KEY = """\
Search research is not available: this server has no SERPER_API_KEY configured, so the
research tools were not registered.

Tell the user they need a key from serper.dev, set as SERPER_API_KEY either in their
MCP client's env block for this server or in a local .env file, and that the server
must be restarted afterwards. Do not attempt the research another way.
"""

_THEME_A_SITE = """\
You are designing a custom Ghost blog theme that matches an existing brand. Before
writing any theme, gather these inputs from the user, in order, and confirm them back
before building.

1. Product site. The live URL of their product or marketing site. As soon as you have
   it, call extract_brand(site_url) and show what you found (palette, fonts, logo, and
   the navigation links).{site_line}
2. Product and audience. One sentence on what the product does and who it is for.
3. Colours. Match the site automatically, or specific hex values.
4. Fonts. Match the site, or a preference (serif or sans, named families).
5. Feel. Light or dark.
6. Purpose and conversion. What the blog is for, and the single action every post
   should push readers toward (signup, demo, booking). This shapes every CTA.
7. Content and layout. The post categories, and any layout preference (featured hero,
   grid, or list).
8. Navigation. extract_brand also returns the site's menus (navigation.primary,
   navigation.secondary, navigation.membership). Show the content links it found and
   ask which to use for the blog's header and footer menus. Treat membership links
   (login/sign-up/account) specially: they usually point at the parent app's own
   auth, NOT the blog, so ask the user whether to drop them (default), keep them as
   external links, or -- only if you are re-theming an existing Ghost blog -- wire
   them into the theme as Portal buttons (data-portal). Never add membership links to
   the menus automatically.

Then summarise the direction in a few lines and get a clear yes before calling
create_theme. Build the header and footer in default_template, page sections in the
content templates, and the design in styles. Preview with preview_theme and iterate
before suggesting upload. Once the layout is approved, set Ghost's own accent colour
(update_branding), site metadata (update_site_metadata), and the navigation menus the
user chose (update_navigation) to match. Install with upload_theme; it stays inactive,
so tell the user to activate it in Ghost Admin.
"""


def register(mcp: FastMCP) -> None:
    """Register the guided-flow prompts on the given server."""

    @mcp.prompt(name="theme-a-site", title="Theme a site")
    def theme_a_site(site_url: str | None = None) -> str:
        """Guided flow to design and build a custom Ghost theme matched to a brand.

        Args:
            site_url: Optional live product/marketing site to match. If given, the
                flow starts by extracting its brand.
        """
        site_line = f"\n   The user gave: {site_url} -- start there." if site_url else ""
        return _THEME_A_SITE.format(site_line=site_line)

    @mcp.prompt(name="set-up-research", title="Set up search research")
    def set_up_research() -> str:
        """Guided flow to configure keyword research for this blog's niche.

        Interviews the user about their business, competitors and customers' own
        terminology, then builds the research profile every verdict depends on.
        """
        if not serper_api_key():
            return _NO_KEY
        questions = "\n".join(
            f"{index}. {question.ask}\n   ({question.why})"
            for index, question in enumerate(INTERVIEW, start=1)
        )
        return _SET_UP_RESEARCH.format(questions=questions)
