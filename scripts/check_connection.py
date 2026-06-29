"""Manual check that the configured credentials reach the Ghost Admin API.

Run with::

    uv run python scripts/check_connection.py

Exercises the real config, auth, and client layers against the live site and
prints the result of a few read-only requests.
"""

from ghost_mcp.admin import GhostAdminClient
from ghost_mcp.config import load_settings


def main() -> None:
    settings = load_settings()
    print(f"Site      : {settings.site_url}")
    print(f"Admin API : {settings.admin_api_base}\n")

    with GhostAdminClient(settings) as client:
        site = client.get("/site/")["site"]
        print(f"Connected to '{site['title']}' (Ghost {site['version']})")

        me = client.read("users", "me")
        print(f"Authenticated as: {me.get('name')} <{me.get('email')}>")

        posts = client.browse("posts", params={"limit": 3})
        titles = [p["title"] for p in posts.get("posts", [])]
        print(f"Recent posts: {titles}")


if __name__ == "__main__":
    main()
