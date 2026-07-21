"""Tools for managing blog posts: list, read, create, update, delete, and preview.

Posts carry a ``preview_url``: Ghost's native draft preview (``{site}/p/{uuid}/``),
which renders the post in the active theme exactly as it will look when published.
It works for drafts and is shareable, so it's the way to review a post before it
goes live.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ghost_mcp.admin import posts as posts_api
from ghost_mcp.errors import GhostError
from ghost_mcp.tools._client import admin_client, config


def _summary(post: dict, site_url: str | None = None) -> dict:
    data = {
        "id": post.get("id"),
        "title": post.get("title"),
        "slug": post.get("slug"),
        "status": post.get("status"),
        "url": post.get("url"),
        "updated_at": post.get("updated_at"),
    }
    uuid = post.get("uuid")
    if site_url and uuid:
        data["preview_url"] = f"{site_url}/p/{uuid}/"
    return data


def _detail(post: dict, site_url: str | None = None) -> dict:
    return {
        **_summary(post, site_url),
        "html": post.get("html"),
        "excerpt": post.get("custom_excerpt") or post.get("excerpt"),
        "feature_image": post.get("feature_image"),
        "feature_image_alt": post.get("feature_image_alt"),
        "meta_title": post.get("meta_title"),
        "meta_description": post.get("meta_description"),
        "codeinjection_head": post.get("codeinjection_head"),
        "codeinjection_foot": post.get("codeinjection_foot"),
        "tags": [tag.get("name") for tag in (post.get("tags") or [])],
    }


#: Tool argument name -> Ghost field name, for the fields that pass straight through.
#: A mapping rather than a chain of ``if`` statements so adding a field is one line,
#: and so the two tools cannot drift apart on which fields they accept.
_FIELDS = {
    "title": "title",
    "slug": "slug",
    "status": "status",
    "excerpt": "custom_excerpt",
    "feature_image": "feature_image",
    "feature_image_alt": "feature_image_alt",
    "meta_title": "meta_title",
    "meta_description": "meta_description",
    "codeinjection_head": "codeinjection_head",
    "codeinjection_foot": "codeinjection_foot",
}


def _build_fields(**values: object) -> dict:
    """Map supplied tool arguments onto Ghost's field names, dropping any left unset.

    ``None`` means "leave unchanged", which is why it is skipped rather than sent. An
    empty string is sent, so a field can still be deliberately cleared.
    """
    fields: dict = {
        ghost_name: values[argument]
        for argument, ghost_name in _FIELDS.items()
        if values.get(argument) is not None
    }
    tags = values.get("tags")
    if tags is not None:
        fields["tags"] = [{"name": name} for name in tags]  # type: ignore[union-attr]
    return fields


def register(mcp: FastMCP) -> None:
    """Register the post tools on the given server."""

    @mcp.tool
    def list_posts(
        limit: int = 15,
        page: int = 1,
        filter: str | None = None,
        order: str = "updated_at desc",
    ) -> dict:
        """List blog posts.

        Args:
            limit: Posts per page (Ghost allows up to 100).
            page: Which page of results to return.
            filter: Optional Ghost filter, e.g. ``status:published`` or ``tag:news``.
            order: Sort order, e.g. ``published_at desc``.

        Returns:
            A list of post summaries (each with a ``preview_url``) and the pagination
            block.
        """
        result = posts_api.browse_posts(
            admin_client(), filter=filter, limit=limit, page=page, order=order
        )
        return {
            "posts": [_summary(p, config().site_url) for p in result.get("posts", [])],
            "pagination": result.get("meta", {}).get("pagination"),
        }

    @mcp.tool
    def get_post(post_id: str | None = None, slug: str | None = None) -> dict:
        """Read a single post by id or slug, including its rendered HTML.

        Provide either ``post_id`` or ``slug``. The result includes a ``preview_url``
        for viewing the post in the active theme.
        """
        if not post_id and not slug:
            raise GhostError("Provide either post_id or slug.")
        post = posts_api.read_post(admin_client(), slug or post_id, slug=bool(slug))
        return _detail(post, config().site_url)

    @mcp.tool
    def create_post(
        title: str,
        html: str = "",
        status: str = "draft",
        slug: str | None = None,
        excerpt: str | None = None,
        tags: list[str] | None = None,
        feature_image: str | None = None,
        feature_image_alt: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        codeinjection_head: str | None = None,
        codeinjection_foot: str | None = None,
    ) -> dict:
        """Create a blog post from HTML content.

        Defaults to a **draft**; pass ``status="published"`` to publish immediately.
        ``tags`` are given as names and created if they don't already exist.
        ``meta_title``/``meta_description`` set the post's search-snippet metadata.

        ``slug`` sets the URL path; Ghost derives one from the title if omitted. A
        shorter, keyword-led slug is usually better than a full title, and changing it
        after publishing breaks existing links.

        ``feature_image_alt`` is the alt text for the feature image. Set it whenever
        you set ``feature_image``: it is what screen readers announce, and an image
        with no alt text is invisible to them.

        ``codeinjection_head``/``codeinjection_foot`` are raw HTML injected verbatim
        into this post's ``<head>`` and page footer. Unlike ``html`` (which Ghost
        converts to Lexical and strips ``<script>`` from), code injection is left
        untouched, so it's the right home for a ``<script type="application/ld+json">``
        block such as FAQ or Article structured data.

        Returns the created post's summary, including a ``preview_url`` for reviewing
        the draft in the active theme before publishing.
        """
        fields = _build_fields(
            title=title,
            slug=slug,
            status=status,
            excerpt=excerpt,
            tags=tags,
            feature_image=feature_image,
            feature_image_alt=feature_image_alt,
            meta_title=meta_title,
            meta_description=meta_description,
            codeinjection_head=codeinjection_head,
            codeinjection_foot=codeinjection_foot,
        )
        created = posts_api.create_post(admin_client(), fields, html=html or None)
        return _summary(created, config().site_url)

    @mcp.tool
    def update_post(
        post_id: str,
        title: str | None = None,
        html: str | None = None,
        status: str | None = None,
        slug: str | None = None,
        excerpt: str | None = None,
        tags: list[str] | None = None,
        feature_image: str | None = None,
        feature_image_alt: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        codeinjection_head: str | None = None,
        codeinjection_foot: str | None = None,
    ) -> dict:
        """Update an existing post by id; only the fields you pass are changed.

        Pass ``status="published"`` to publish a draft, or ``status="draft"`` to
        unpublish. An empty ``html`` is treated as "leave the body unchanged" (same
        as create), so it never blanks a post.

        ``slug`` changes the URL path. On an already-published post this breaks every
        existing link to it, so only change it on explicit instruction.

        ``feature_image_alt`` sets the feature image's alt text, which screen readers
        announce in place of the image. Worth adding to older posts that have none.

        ``codeinjection_head``/``codeinjection_foot`` are raw HTML injected verbatim
        into this post's ``<head>`` and page footer, untouched by Ghost's Lexical
        conversion. Use them for a ``<script type="application/ld+json">`` block
        (e.g. FAQ or Article structured data) that would be stripped from ``html``.
        Pass an empty string to clear an existing injection. Returns the updated
        post summary.
        """
        fields = _build_fields(
            title=title,
            slug=slug,
            status=status,
            excerpt=excerpt,
            tags=tags,
            feature_image=feature_image,
            feature_image_alt=feature_image_alt,
            meta_title=meta_title,
            meta_description=meta_description,
            codeinjection_head=codeinjection_head,
            codeinjection_foot=codeinjection_foot,
        )
        updated = posts_api.update_post(admin_client(), post_id, fields, html=html or None)
        return _summary(updated, config().site_url)

    @mcp.tool
    def publish_post(
        post_id: str,
        newsletter_slug: str,
        email_segment: str = "all",
        scheduled_at: str | None = None,
    ) -> dict:
        """Publish a post AND email it to a newsletter's subscribers. SENDS REAL EMAIL.

        This is outward-facing and irreversible: it emails the post to members the
        moment it publishes (or at ``scheduled_at``). Only call it on explicit user
        instruction to send. To publish WITHOUT emailing, use
        ``update_post(status="published")`` instead.

        Args:
            post_id: The post to publish and send.
            newsletter_slug: The newsletter to send through (from ``list_newsletters``).
                An archived or unknown slug means no email is sent.
            email_segment: Which members receive it, as an NQL filter: ``all`` (default),
                ``status:free``, or ``status:-free`` (paid).
            scheduled_at: Optional ISO 8601 time to schedule the send; if given, the post
                is scheduled and Ghost emails it automatically then. Omit to send now.

        Returns:
            The updated post summary.
        """
        fields: dict = {"status": "scheduled" if scheduled_at else "published"}
        if scheduled_at:
            fields["published_at"] = scheduled_at
        updated = posts_api.update_post(
            admin_client(),
            post_id,
            fields,
            params={"newsletter": newsletter_slug, "email_segment": email_segment},
        )
        return _summary(updated, config().site_url)

    @mcp.tool
    def delete_post(post_id: str) -> dict:
        """Delete a post by id. This cannot be undone."""
        posts_api.delete_post(admin_client(), post_id)
        return {"deleted": post_id}
