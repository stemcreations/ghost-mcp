"""Tools for deciding what to write, based on what already ranks.

These are registered only when ``SERPER_API_KEY`` is set (see
:func:`ghost_mcp.tools.register_all`), because every one of them needs it.

They are deliberately split by cost, since each Serper call is billable:
``search_serp`` and ``expand_keywords`` are cheap reconnaissance, while
``build_content_brief`` and ``find_content_gaps`` add a crawl of the ranking pages.
Start cheap; only build a brief for a keyword that survived triage.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastmcp import FastMCP

from ghost_mcp.admin import posts as posts_api
from ghost_mcp.research import SHARED_TOPIC_PAGES, fetch_pages
from ghost_mcp.research import brief as brief_api
from ghost_mcp.research import incumbents as incumbents_api
from ghost_mcp.research.interview import interview_plan
from ghost_mcp.tools._client import admin_client, config, serper_client

#: How many ranking pages to crawl at most, whatever the caller asks for. Each one is
#: an HTTP fetch inside a single tool call, and the marginal signal past ~8 is small.
_MAX_FETCH = 8


def _own_domain() -> str | None:
    """The blog's own registrable domain, so its pages aren't scored as competition."""
    try:
        return urlparse(config().site_url).netloc or None
    except Exception:  # noqa: BLE001 - research must still work if Ghost config is absent
        return None


def _organic_links(data: dict, limit: int) -> list[str]:
    return [link for item in brief_api.organic_results(data)[:limit] if (link := item.get("link"))]


def register(mcp: FastMCP) -> None:
    """Register the search-research tools on the given server."""

    @mcp.tool
    def search_serp(
        query: str, num: int = 10, location: str | None = None, profile: str | None = None
    ) -> dict:
        """See what currently ranks for a query, and whether it is worth writing for.

        The cheap first step: one search, no page crawling. Use it to triage a list of
        candidate topics before spending a crawl on any of them.

        Two verdicts matter most. ``LOCAL_INTENT`` means Google showed a map pack and
        wants a business, not an article -- recommend a service or location page
        instead of a post. ``SKIP`` means the query is owned by domains that outrank
        on authority alone, so the topic should be re-angled rather than abandoned.

        Judgement depends on the active research profile, which decides which domains
        count as unbeatable; see ``list_research_profiles``.

        Args:
            query: The search query to inspect.
            num: How many organic results to retrieve.
            location: Locality to search from, e.g. ``Denver, Colorado, United States``.
                Pass it whenever the query might have local intent -- it decides
                whether a local pack appears at all.
            profile: Override the active research profile for this call.

        Returns:
            The ``opportunity`` verdict, the ranking results (each flagged
            ``is_incumbent`` / ``is_own_site``), any ``local_pack`` businesses, the
            "people also ask" questions, related searches, and those queries grouped
            by intent.
        """
        data = serper_client().search(query, num=num, location=location)
        own = _own_domain()
        resolved, incumbents = incumbents_api.resolve(profile, exclude=[own] if own else None)
        hosts = [urlparse(item.get("link", "")).netloc for item in brief_api.organic_results(data)]
        places = brief_api.local_pack(data)
        questions = brief_api.people_also_ask(data)
        related = brief_api.related_searches(data)
        opportunity = brief_api.assess_opportunity(
            hosts,
            profile=resolved,
            incumbents=incumbents,
            own_domain=own,
            has_local_pack=bool(places),
        )
        return {
            "query": query,
            "opportunity": opportunity.to_dict(),
            "ranking_results": brief_api.summarize_results(data, incumbents, own),
            "local_pack": [
                {"title": place.get("title"), "rating": place.get("rating")} for place in places[:5]
            ],
            "questions_to_answer": questions,
            "related_searches": related,
            "queries_by_intent": brief_api.group_queries([query, *questions, *related]),
        }

    @mcp.tool
    def expand_keywords(seed: str, depth: int = 1, location: str | None = None) -> dict:
        """Expand a seed topic into the real queries people search, grouped by intent.

        Harvests Google's own "people also ask", related searches, and autocomplete,
        so the phrasings come from actual search behaviour rather than guesswork. Use
        it to decide which questions an article must answer, and to find sub-topics
        that deserve posts of their own.

        The intent groups tell you what *format* each query wants, which matters more
        than the raw list. ``local`` queries want a service page rather than a post.
        ``alternatives`` ("X alternatives", "switching from X") and ``comparison``
        ("X vs Y") are usually the highest-converting pages a challenger can publish.
        ``cost`` and ``how_to`` are where real numbers and real workflows beat an
        aggregator that has neither.

        Args:
            seed: The topic to expand, e.g. ``red light therapy``.
            depth: ``1`` costs 2 API credits (one search + one autocomplete). ``2``
                additionally runs autocomplete on the top 3 related searches, costing
                5 credits total. Use 2 only when 1 produced too few queries.
            location: Locality to search from; affects which queries surface.

        Returns:
            ``queries_by_intent`` (the grouped result -- the useful part),
            ``all_queries``, the source lists, and ``credits_used``.
        """
        client = serper_client()
        data = client.search(seed, num=10, location=location)
        questions = brief_api.people_also_ask(data)
        related = brief_api.related_searches(data)
        suggestions = client.autocomplete(seed)
        credits = 2

        if depth >= 2:
            for query in related[:3]:
                suggestions.extend(client.autocomplete(query))
                credits += 1

        collected = [seed, *questions, *related, *suggestions]
        grouped = brief_api.group_queries(collected)
        return {
            "seed": seed,
            "queries_by_intent": grouped,
            "all_queries": sorted({q for group in grouped.values() for q in group}),
            "people_also_ask": questions,
            "related_searches": related,
            "autocomplete": suggestions,
            "credits_used": credits,
        }

    @mcp.tool
    def build_content_brief(
        keyword: str,
        fetch: int = 5,
        num: int = 10,
        location: str | None = None,
        profile: str | None = None,
    ) -> dict:
        """Build a full article brief by analysing the pages that rank for a keyword.

        Searches, then crawls the top results to extract the structure they share:
        which sections appear on most of them (table stakes), which appear on only one
        (an angle worth taking), how long they run, and whether they carry pricing
        tables or FAQs. Costs one API credit plus the page fetches.

        Check the ``opportunity`` verdict before writing: if it says ``LOCAL_INTENT``
        or ``SKIP``, the brief is still informative but a post is the wrong response.

        Args:
            keyword: The target keyword to build a brief for.
            fetch: How many top-ranking pages to crawl (capped at 8).
            num: How many organic results to retrieve.
            location: Locality to search from, e.g. ``Denver, Colorado, United States``.
            profile: Override the active research profile for this call.

        Returns:
            ``opportunity``, ``required_sections`` (consensus structure),
            ``secondary_sections``, ``unique_angles``, ``format_signals`` (word count,
            pricing table and FAQ prevalence), ``questions_to_answer``,
            ``queries_by_intent``, and ``failed_fetches``.
        """
        data = serper_client().search(keyword, num=num, location=location)
        pages = fetch_pages(_organic_links(data, min(fetch, _MAX_FETCH)))
        own = _own_domain()
        return brief_api.build_brief(keyword, data, pages, profile=profile, own_domain=own)

    @mcp.tool
    def find_content_gaps(
        keyword: str,
        fetch: int = 5,
        post_limit: int = 100,
        location: str | None = None,
        profile: str | None = None,
    ) -> dict:
        """Compare what the SERP expects against what this blog has already published.

        Joins the two halves of this server: it builds the consensus topic list for a
        keyword, then matches it against the blog's existing posts. That answers the
        question worth asking before writing anything -- "do we already cover this,
        and should we extend that post instead of publishing a competing one?"

        Publishing a near-duplicate of an existing post splits their ranking signals,
        so prefer extending the matched post when ``covered_topics`` is non-empty.

        Args:
            keyword: The target keyword to analyse.
            fetch: How many top-ranking pages to crawl (capped at 8).
            post_limit: How many published posts to compare against.
            location: Locality to search from.
            profile: Override the active research profile for this call.

        Returns:
            ``gaps`` (topics the SERP expects that no post covers -- write these),
            ``covered_topics`` (each with the post to extend), ``unanswered_questions``,
            and the underlying ``opportunity`` verdict.
        """
        data = serper_client().search(keyword, num=10, location=location)
        pages = fetch_pages(_organic_links(data, min(fetch, _MAX_FETCH)))
        own = _own_domain()
        resolved, incumbents = incumbents_api.resolve(profile, exclude=[own] if own else None)

        fetched = [page for page in pages if page.ok]
        clusters = brief_api.cluster_headings(fetched)
        # Any topic two ranking pages agree on is worth checking coverage against --
        # the same bar assess_consensus uses, so the two can't contradict each other.
        # (build_content_brief keeps a stricter bar for "sections you must include".)
        topics = [cluster.label for cluster in clusters if cluster.page_count >= SHARED_TOPIC_PAGES]
        questions = brief_api.people_also_ask(data)

        result = posts_api.browse_posts(
            admin_client(), filter="status:published", limit=post_limit, order="published_at desc"
        )
        posts = [
            {
                "id": post.get("id"),
                "title": post.get("title"),
                "url": post.get("url"),
                "excerpt": post.get("custom_excerpt") or post.get("excerpt"),
            }
            for post in result.get("posts", [])
        ]

        matched = brief_api.match_topics(topics, posts)
        question_match = brief_api.match_topics(questions, posts)
        hosts = [urlparse(item.get("link", "")).netloc for item in brief_api.organic_results(data)]
        opportunity = brief_api.assess_opportunity(
            hosts,
            profile=resolved,
            incumbents=incumbents,
            own_domain=own,
            has_local_pack=bool(brief_api.local_pack(data)),
        )
        consensus = brief_api.assess_consensus(clusters, len(fetched))
        notes = [
            "Topics in 'gaps' are the strongest case for a new post.",
            "For 'covered_topics', extend the named post with update_post rather "
            "than publishing a second page on the same topic.",
        ]
        # Empty gaps mean two very different things. Say which, or "no gaps found"
        # reads as "you already cover it" when nothing was actually compared.
        if not topics:
            notes.insert(
                0,
                "No consensus topics were found, so 'gaps' being empty does NOT mean "
                "the blog already covers this keyword -- there was nothing to compare "
                "against. See 'consensus' for why, and rely on 'unanswered_questions'.",
            )
        return {
            "keyword": keyword,
            "opportunity": opportunity.to_dict(),
            "consensus": consensus,
            "posts_compared": len(posts),
            "pages_analyzed": len(fetched),
            "topics_analyzed": len(topics),
            "gaps": matched["gaps"],
            "covered_topics": matched["covered"],
            "unanswered_questions": question_match["gaps"],
            "failed_fetches": [
                {"url": page.url, "error": page.error} for page in pages if not page.ok
            ],
            "notes": notes,
        }

    # -- maintaining the incumbent lists -------------------------------------

    @mcp.tool
    def list_research_profiles() -> dict:
        """List the research profiles and show which incumbent domains are in force.

        A profile decides which domains count as unbeatable when judging a keyword,
        which is entirely niche-dependent -- the sites that own "booking software for
        salons" are not the ones that own "is red light therapy safe". ``general`` is
        the default and assumes nothing.

        Returns:
            Every available profile, the ``active`` one, the domains currently in
            force for it, and the path of the JSON file where custom data is stored.
        """
        active = incumbents_api.active_profile_name()
        profile, domains = incumbents_api.resolve(active)
        return {
            "active": active,
            "profiles": [p.to_dict() for p in incumbents_api.all_profiles().values()],
            "active_profile_domains": sorted(domains),
            "custom_domains": incumbents_api.custom_domains(active),
            "dominant_domains": sorted(profile.dominant),
            "store_path": str(incumbents_api.store_path()),
        }

    @mcp.tool
    def set_research_profile(name: str) -> dict:
        """Set the active research profile, persisting it for future sessions.

        Args:
            name: A profile from ``list_research_profiles``.
        """
        active = incumbents_api.set_active_profile(name)
        profile, domains = incumbents_api.resolve(active)
        return {
            "active": active,
            "description": profile.description,
            "domain_count": len(domains),
        }

    @mcp.tool
    def add_incumbents(domains: list[str], profile: str | None = None) -> dict:
        """Record domains you could not realistically outrank, so verdicts account for them.

        This is a "cannot beat this" list, **not** a list of competitors. Every domain
        added makes verdicts more pessimistic, so logging every rival that appears
        steadily degrades the analysis -- and punishes you for discovering that a
        competitor is weak. Add a domain when it holds a result through authority a
        better article would not overcome: a category leader, a review aggregator, a
        major publisher. Leave out small or new players you could plausibly beat, and
        track those as market intelligence instead.

        Do not add forums or social platforms. They are scored separately, because a
        thread ranking is evidence that nobody has published a good answer yet.

        Saved to disk, so it survives restarts and applies to every later call. Bare
        domains are fine (``capterra.com``); URLs and ``www.`` are normalised.

        Args:
            domains: Domains to add, e.g. ``["capterra.com", "g2.com"]``.
            profile: Which profile to add them to; defaults to the active one.
        """
        added = incumbents_api.add_domains(domains, profile)
        target = profile or incumbents_api.active_profile_name()
        supplied = {incumbents_api.registrable(d) for d in domains} - {""}
        return {
            "profile": target,
            "added": added,
            "already_present": sorted(supplied - set(added)),
            "custom_domains": incumbents_api.custom_domains(target),
        }

    @mcp.tool
    def remove_incumbents(domains: list[str], profile: str | None = None) -> dict:
        """Remove domains previously added with ``add_incumbents``.

        Only affects custom additions; a profile's bundled defaults are the shared
        baseline and stay put.

        Args:
            domains: Domains to remove.
            profile: Which profile to remove them from; defaults to the active one.
        """
        removed = incumbents_api.remove_domains(domains, profile)
        target = profile or incumbents_api.active_profile_name()
        return {
            "profile": target,
            "removed": removed,
            "custom_domains": incumbents_api.custom_domains(target),
        }

    @mcp.tool
    def plan_research_profile() -> dict:
        """Get the questions to ask the user before building a research profile.

        **Call this first, and ask the user its questions, before
        ``create_research_profile``.** A profile decides which domains count as
        unbeatable, so a guessed one does not fail loudly -- it returns confident,
        wrong verdicts: a winnable keyword reads as ``SKIP``, and one owned by
        competitors the profile never heard of reads as ``OPEN``. Nothing in the output
        reveals that it was guessed.

        Ask the questions conversationally, a few at a time, and do not answer them on
        the user's behalf. Also worth running when verdicts look wrong, since the usual
        cause is a profile missing the competitors that actually rank.

        Returns:
            The ``questions`` to ask (each with why it matters and what it configures),
            the ``current_state`` of profiles, and the ``then`` steps to follow once
            the user has answered.
        """
        return interview_plan(
            incumbents_api.active_profile_name(),
            sorted(incumbents_api.all_profiles()),
            _own_domain(),
        )

    @mcp.tool
    def create_research_profile(
        name: str,
        description: str,
        domains: list[str],
        dominant_domains: list[str] | None = None,
        dominant_label: str = "incumbent",
        dominant_reason: str = "",
    ) -> dict:
        """Define a research profile for a niche the bundled ones don't cover.

        Run ``plan_research_profile`` first and ask the user its questions. The domains
        here are specific to their business and cannot be inferred from the blog; a
        profile assembled from guesses produces confident, wrong verdicts.

        The bundled profiles are only starting points. If neither ``saas`` nor
        ``wellness`` describes the blog, build one: list the domains that keep winning
        the results you care about, and mark the few that are hopeless on their own.

        Calling this with an existing name replaces that profile, which is also how you
        override a bundled one.

        Args:
            name: A short lowercase slug, e.g. ``indie-game-dev``.
            description: What niche this covers, for whoever reads it later.
            domains: Every domain to treat as an incumbent.
            dominant_domains: The subset so authoritative that three of them ranking
                makes a keyword unwinnable regardless of the total count. Must be a
                subset of ``domains``; entries outside it are ignored.
            dominant_label: How the dominant group reads in a verdict, e.g.
                ``review aggregator`` -> "3 review aggregator sites rank".
            dominant_reason: One sentence on why that group can't be beaten, appended
                to the verdict's reason.
        """
        created = incumbents_api.create_profile(
            name,
            description,
            domains,
            dominant=dominant_domains,
            dominant_label=dominant_label,
            dominant_reason=dominant_reason,
        )
        return {
            **created.to_dict(),
            "note": f"Call set_research_profile('{created.name}') to make it active.",
        }

    @mcp.tool
    def delete_research_profile(name: str) -> dict:
        """Delete a profile created with ``create_research_profile``.

        Bundled profiles cannot be deleted. If the deleted profile was active, the
        active profile reverts to the default.
        """
        return {"deleted": incumbents_api.delete_profile(name), "profile": name}
