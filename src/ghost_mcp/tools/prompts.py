"""User-triggerable prompts that kick off a guided workflow.

A prompt is something the user invokes (it isn't called by the model like a tool);
it returns a message that steers the model through a multi-step flow. ``theme-a-site``
encodes the brand-first theming order so a user can start the whole build with one
action instead of the model rediscovering the steps.
"""

from fastmcp import FastMCP

_THEME_A_SITE = """\
You are designing a custom Ghost blog theme that matches an existing brand. Before
writing any theme, gather these inputs from the user, in order, and confirm them back
before building.

1. Product site. The live URL of their product or marketing site. As soon as you have
   it, call extract_brand(site_url) and show what you found (palette, fonts, logo).{site_line}
2. Product and audience. One sentence on what the product does and who it is for.
3. Colours. Match the site automatically, or specific hex values.
4. Fonts. Match the site, or a preference (serif or sans, named families).
5. Feel. Light or dark.
6. Purpose and conversion. What the blog is for, and the single action every post
   should push readers toward (signup, demo, booking). This shapes every CTA.
7. Content and layout. The post categories, and any layout preference (featured hero,
   grid, or list).

Then summarise the direction in a few lines and get a clear yes before calling
create_theme. Build the header and footer in default_template, page sections in the
content templates, and the design in styles. Preview with preview_theme and iterate
before suggesting upload. Once the layout is approved, set Ghost's own accent colour
(update_branding) and site metadata (update_site_metadata) to match. Install with
upload_theme; it stays inactive, so tell the user to activate it in Ghost Admin.
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
