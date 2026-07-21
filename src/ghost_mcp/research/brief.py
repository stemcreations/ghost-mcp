"""Turn a search result page plus its ranking competitors into an article brief.

Everything here is pure: it takes already-fetched data and returns plain data, so
the judgement calls (what counts as an incumbent, when a query is worth writing
for) are unit-testable without spending an API credit.

What counts as an unbeatable competitor is niche-specific, so this module holds no
opinion about it: the domain lists live in :mod:`ghost_mcp.research.incumbents`
behind a selectable profile. The logic here only asks "how many of the ranking
domains are incumbents, and are any of them decisive on their own?"

Two signals override a raw count, because they change what should be *written*
rather than merely how hard it would be:

* A local pack means Google reads the query as "find me a business", not "explain
  this to me". The answer is a service or location page, not a blog post.
* Three of a profile's *dominant* domains (medical authorities for consumer health,
  review aggregators for software) makes a query unwinnable however good the writing.
  The move is to re-angle the topic, not to abandon it.

Winnable ground is usually first-party: real prices, real protocols, comparisons and
lived experience -- the things an aggregator or a hospital site structurally cannot
publish.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ghost_mcp.research.incumbents import (
    Profile,
    get_profile,
    is_ugc,
    registrable,
    resolve,
)
from ghost_mcp.research.pages import RankingPage, normalize

#: Dropped before comparing headings, so "How much does a facial cost?" and
#: "Facial cost" are recognised as the same topic.
STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with",
        "is", "are", "your", "you", "it", "that", "this", "what", "how", "why",
        "best", "top", "vs", "versus", "at", "by", "from", "be", "can", "do",
        "does", "should", "will", "about", "when", "who", "was", "were", "get",
    }
)  # fmt: skip


def tokens(text: str) -> set[str]:
    """Content-bearing lowercase word tokens, for comparing headings and titles."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {word for word in words if word not in STOPWORDS and len(word) > 2}


# -- reading Serper's response ----------------------------------------------


def organic_results(data: dict) -> list[dict]:
    """The organic result list from a Serper response."""
    return [item for item in (data.get("organic") or []) if isinstance(item, dict)]


def people_also_ask(data: dict) -> list[str]:
    """The "people also ask" questions, which are literal user phrasings to answer."""
    items = data.get("peopleAlsoAsk") or []
    return [q for item in items if isinstance(item, dict) and (q := item.get("question"))]


def related_searches(data: dict) -> list[str]:
    """The "related searches" queries shown beneath the results."""
    items = data.get("relatedSearches") or []
    return [q for item in items if isinstance(item, dict) and (q := item.get("query"))]


def local_pack(data: dict) -> list[dict]:
    """Map-pack businesses, if Google showed any for this query."""
    return [item for item in (data.get("places") or []) if isinstance(item, dict)]


# -- query intent ------------------------------------------------------------

#: Ordered: queries routinely match several patterns, and the first hit wins. The
#: order encodes which reading is most *actionable*, not which is most literal --
#: "vagaro vs mindbody pricing" is a comparison article, not a pricing one.
_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "alternatives",
        re.compile(
            r"\balternatives?\b|\bcompetitors?\b|\binstead of\b|\bswitch(ing)? (from|to)\b|"
            r"\bmigrat\w+ (from|to)\b|\breplacement for\b|\bsimilar to\b"
        ),
    ),
    ("local", re.compile(r"\bnear (me|you|by)\b|\bnearby\b|\bin my area\b|\bopen now\b|\blocal\b")),
    (
        "comparison",
        re.compile(
            r"\bvs\.?\b|\bversus\b|difference between|compared to|better than|which is better"
        ),
    ),
    # "how much" must not swallow "how much time", which is a duration question.
    (
        "cost",
        re.compile(
            r"\bcosts?\b|\bprices?\b|pricing|\bfees?\b|how much(?! time)|cheap|"
            r"affordable|worth it|\bdeals?\b|\bfree\b|\bdiscount"
        ),
    ),
    # Practical, hands-on guidance. Deliberately ahead of "commercial" so that
    # "when is the best time to ..." reads as guidance rather than a "best X" roundup.
    (
        "how_to",
        re.compile(
            r"what to expect|first time|before and after|how often|how long|how many|"
            r"does it hurt|side effects?|\brisks?\b|\bsafe\b|how to |aftercare|"
            r"what happens|best (time|way) to|\bprotocols?\b|\broutines?\b|\btiming\b|"
            r"\bat home\b|step by step|\bsetup\b|\bset up\b|\btutorial\b|\bguide\b"
        ),
    ),
    (
        "commercial",
        re.compile(
            r"\bbest\b|\btop\b|\breviews?\b|\bnear\b|"
            r"\b(software|apps?|systems?|platforms?|tools?|services?) for\b"
        ),
    ),
]


def classify_query(query: str) -> str:
    """Label a query's intent, which decides what *format* the answer wants.

    Returns one of ``alternatives``, ``local``, ``comparison``, ``cost``, ``how_to``,
    ``commercial`` or ``informational``.

    The label matters more than it looks: ``local`` wants a service page rather than a
    post, ``alternatives`` and ``comparison`` are usually the highest-converting pages
    a challenger can publish, and ``cost``/``how_to`` are where first-party knowledge
    beats an aggregator or an institutional site.
    """
    text = (query or "").lower()
    for label, pattern in _INTENT_PATTERNS:
        if pattern.search(text):
            return label
    return "informational"


def group_queries(queries: list[str]) -> dict[str, list[str]]:
    """Group queries by intent, deduplicated, preserving first-seen order."""
    grouped: dict[str, list[str]] = {}
    seen: set[str] = set()
    for query in queries:
        cleaned = normalize(query)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        grouped.setdefault(classify_query(cleaned), []).append(cleaned)
    return grouped


# -- competitor structure ----------------------------------------------------


@dataclass
class TopicCluster:
    """A heading topic, grouped across the pages that cover it."""

    label: str
    page_count: int
    variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"topic": self.label, "page_count": self.page_count, "variants": self.variants}


def cluster_headings(pages: list[RankingPage], *, threshold: float = 0.55) -> list[TopicCluster]:
    """Group near-duplicate headings across pages into topics.

    Two headings belong together when their token sets overlap by ``threshold``
    (Jaccard), so "How much does a facial cost?" and "Facial pricing" collapse into
    one topic. The shortest phrasing becomes the label. Sorted by how many distinct
    pages cover the topic, which is the whole point: a topic on four of five ranking
    pages is table stakes, one on a single page is an angle.
    """
    groups: list[dict] = []
    for index, page in enumerate(pages):
        for _level, text in page.headings:
            heading_tokens = tokens(text)
            if not heading_tokens:
                continue
            match = None
            for group in groups:
                overlap = len(heading_tokens & group["tokens"])
                union = len(heading_tokens | group["tokens"]) or 1
                if overlap / union >= threshold:
                    match = group
                    break
            if match is None:
                groups.append(
                    {"tokens": heading_tokens, "label": text, "pages": {index}, "variants": [text]}
                )
                continue
            match["pages"].add(index)
            if text not in match["variants"]:
                match["variants"].append(text)
            if len(text) < len(match["label"]):
                match["label"] = text
    groups.sort(key=lambda group: (-len(group["pages"]), group["label"].lower()))
    return [
        TopicCluster(label=g["label"], page_count=len(g["pages"]), variants=g["variants"])
        for g in groups
    ]


def format_signals(pages: list[RankingPage]) -> dict:
    """Summarise what the ranking pages look like structurally."""
    fetched = [page for page in pages if page.ok]
    if not fetched:
        return {
            "pages_analyzed": 0,
            "pages_requested": len(pages),
            "recommendations": ["No competitor pages could be fetched; treat signals as unknown."],
        }
    word_counts = sorted(page.word_count for page in fetched)
    with_price = sum(1 for page in fetched if page.has_price_table)
    with_faq = sum(1 for page in fetched if page.has_faq)
    majority = max(2, len(fetched) // 2)
    # The crawler reads raw HTML, so a client-rendered page reports no text at all.
    # Left in the average it would silently drag the target length down.
    empty = sum(1 for page in fetched if page.word_count == 0)

    recommendations: list[str] = []
    if empty:
        recommendations.append(
            f"{empty} of {len(fetched)} pages returned no readable text -- most likely "
            "JavaScript-rendered. Their word counts are zero, so treat the length "
            "figures as a floor rather than a target."
        )
    if with_price >= majority:
        recommendations.append(
            "Include a pricing table -- most ranking pages have one, and first-party "
            "prices are something the big health sites cannot publish."
        )
    if with_faq >= majority:
        recommendations.append(
            "Include an FAQ block, and mark it up as FAQ structured data via "
            "codeinjection_head on the post."
        )
    return {
        "pages_analyzed": len(fetched),
        "pages_requested": len(pages),
        "median_word_count": int(statistics.median(word_counts)),
        "word_count_range": [word_counts[0], word_counts[-1]],
        "pages_with_price_table": with_price,
        "pages_with_faq": with_faq,
        "pages_without_text": empty,
        "median_list_count": int(statistics.median([page.lists for page in fetched])),
        "recommendations": recommendations,
    }


#: How many ranking pages must share a topic before it counts as agreement at all.
#: Exported so callers judging "is there consensus" and callers listing the topics use
#: one definition -- two thresholds both called "consensus" contradict each other.
SHARED_TOPIC_PAGES = 2


def assess_consensus(clusters: list[TopicCluster], pages_analyzed: int) -> dict:
    """Judge whether the ranking pages agree on what the query is even about.

    An empty consensus is a finding, not an absence of one. When several pages rank
    and *none* share a topic, Google has no settled intent for the query -- the
    results are a grab-bag of product pages, explainers and directories. That usually
    means thin or ambiguous demand, which matters because a low incumbent count on
    such a query reads as "wide open" when it more often means "nobody is competing
    because there is little here to win".
    """
    shared = [cluster for cluster in clusters if cluster.page_count >= SHARED_TOPIC_PAGES]
    if pages_analyzed < 3:
        return {
            "has_consensus": bool(shared),
            "shared_topic_count": len(shared),
            "note": "Too few pages analysed to judge consensus.",
        }
    if shared:
        return {"has_consensus": True, "shared_topic_count": len(shared), "note": ""}
    return {
        "has_consensus": False,
        "shared_topic_count": 0,
        "note": (
            f"None of the {pages_analyzed} ranking pages share a single topic, so there "
            "is no consensus structure to match. Google has not settled what this query "
            "means. Treat an OPEN verdict here with caution -- prefer a query whose "
            "results agree on what they are, and check 'related_searches' for one."
        ),
    }


# -- the verdict -------------------------------------------------------------


@dataclass
class Opportunity:
    """Whether a keyword is worth writing for, and what to write instead if not."""

    verdict: str
    reason: str
    recommendation: str
    total_results: int
    incumbent_count: int
    #: How many of the profile's *dominant* domains rank; three is decisive.
    dominant_count: int = 0
    #: Incumbents that are actual published pages -- what genuinely stands in the way.
    #: The verdict is judged on this, not on ``incumbent_count``.
    competing_pages: int = 0
    #: Forum and social results. Demand evidence, not competition.
    ugc_results: int = 0
    profile: str = ""
    incumbent_domains: list[str] = field(default_factory=list)
    ugc_domains: list[str] = field(default_factory=list)
    own_domain_ranks: bool = False
    has_local_pack: bool = False

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "recommendation": self.recommendation,
            "profile": self.profile,
            "total_results": self.total_results,
            "competing_pages": self.competing_pages,
            "ugc_results": self.ugc_results,
            "incumbent_count": self.incumbent_count,
            "dominant_count": self.dominant_count,
            "incumbent_domains": self.incumbent_domains,
            "ugc_domains": self.ugc_domains,
            "own_domain_ranks": self.own_domain_ranks,
            "has_local_pack": self.has_local_pack,
        }


def assess_opportunity(
    hosts: list[str],
    *,
    profile: str | Profile | None = None,
    incumbents: set[str] | None = None,
    own_domain: str | None = None,
    has_local_pack: bool = False,
) -> Opportunity:
    """Judge whether a keyword is winnable, from the domains ranking for it.

    Verdicts: ``UPDATE_EXISTING`` (you already rank -- improve that page rather than
    competing with yourself), ``LOCAL_INTENT`` (Google wants a business, not an
    article), ``SKIP``, ``CONTESTED``, ``OPEN``.

    Args:
        hosts: The hostnames ranking for the query, in order.
        profile: Which niche's incumbent list to judge against; defaults to the
            active profile.
        incumbents: An explicit domain set, bypassing the profile's own list. The
            profile is still consulted for its *dominant* group.
        own_domain: The user's site, excluded from the incumbent count.
        has_local_pack: Whether Google showed a map pack for the query.
    """
    resolved = profile if isinstance(profile, Profile) else get_profile(profile)
    if incumbents is None:
        _, incumbents = resolve(resolved, exclude=[own_domain] if own_domain else None)
    own = registrable(own_domain) if own_domain else None
    domains = [registrable(host) for host in hosts if host]

    matched = [domain for domain in domains if domain in incumbents and domain != own]
    dominant = [domain for domain in domains if domain in resolved.dominant and domain != own]
    own_ranks = bool(own) and own in domains

    # Forum and social results are not competition. A thread ranking almost always
    # means nobody published a good answer, so counting it as a barrier inverts the
    # signal -- the strongest evidence of demand gets read as a reason to walk away.
    ugc = [domain for domain in matched if is_ugc(domain)]
    competing = [domain for domain in matched if not is_ugc(domain)]
    demand = len(ugc) >= 2 and len(competing) <= 4

    if own_ranks:
        verdict = "UPDATE_EXISTING"
        reason = f"{own} already ranks for this query."
        recommendation = (
            "Improve the page that already ranks instead of publishing a competing one. "
            "Use find_content_gaps to see which sections it is missing."
        )
    elif has_local_pack:
        verdict = "LOCAL_INTENT"
        reason = "Google shows a local map pack, so it reads this as 'find me a business'."
        recommendation = (
            "A blog post will not capture this. Build a service or location page and "
            "invest in the Google Business Profile; use the blog only to support it."
        )
    elif len(dominant) >= 3:
        listed = ", ".join(sorted(set(dominant))[:4])
        verdict = "SKIP"
        reason = f"{len(dominant)} {resolved.dominant_label} sites rank ({listed})."
        if resolved.dominant_reason:
            reason += f" {resolved.dominant_reason}"
        recommendation = (
            "Do not compete head-on. Re-angle toward what only you can publish -- real "
            "prices, real workflows, honest limitations, direct comparisons."
        )
    elif len(competing) >= 7:
        verdict = "SKIP"
        reason = f"{len(competing)} of {len(domains)} results are established competitor pages."
        recommendation = "Find a longer-tail or more specific variant of this query."
    elif demand:
        verdict = "UNMET_DEMAND"
        reason = (
            f"{len(ugc)} forum/social results rank against only {len(competing)} "
            "established competitor pages. People are asking this and no one has "
            "published a good answer."
        )
        recommendation = (
            "The strongest kind of opportunity: demand is proven and the competition "
            "is thin. Read the actual threads, answer the question they are asking in "
            "their words, and be more specific than the generic pages that rank."
        )
    elif len(competing) >= 4:
        verdict = "CONTESTED"
        reason = f"{len(competing)} of {len(domains)} results are established competitor pages."
        recommendation = (
            "Winnable only with a genuinely better first-party answer: real numbers, "
            "real detail, and something no aggregator can reproduce."
        )
    else:
        verdict = "OPEN"
        reason = f"Only {len(competing)} of {len(domains)} results are competitor pages."
        recommendation = "There is room here. Write it."

    return Opportunity(
        verdict=verdict,
        reason=reason,
        recommendation=recommendation,
        profile=resolved.name,
        total_results=len(domains),
        incumbent_count=len(matched),
        dominant_count=len(dominant),
        competing_pages=len(competing),
        ugc_results=len(ugc),
        incumbent_domains=sorted(set(competing)),
        ugc_domains=sorted(set(ugc)),
        own_domain_ranks=own_ranks,
        has_local_pack=has_local_pack,
    )


# -- assembling a brief ------------------------------------------------------


def summarize_results(
    data: dict, incumbents: set[str], own_domain: str | None = None
) -> list[dict]:
    """Flatten the organic results, flagging incumbents and the user's own pages."""
    own = registrable(own_domain) if own_domain else None
    summary = []
    for position, item in enumerate(organic_results(data), start=1):
        domain = registrable(urlparse(item.get("link", "")).netloc)
        summary.append(
            {
                "position": position,
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "domain": domain,
                "snippet": normalize(item.get("snippet", "")),
                "is_incumbent": domain in incumbents and domain != own,
                "is_own_site": bool(own) and domain == own,
            }
        )
    return summary


def build_brief(
    keyword: str,
    data: dict,
    pages: list[RankingPage],
    *,
    profile: str | Profile | None = None,
    incumbents: set[str] | None = None,
    own_domain: str | None = None,
) -> dict:
    """Assemble the full brief from a search response and the crawled ranking pages.

    Returns structured data rather than prose: the model consuming this is the one
    writing the article, and it needs to be able to filter and re-rank the parts.
    """
    resolved = profile if isinstance(profile, Profile) else get_profile(profile)
    if incumbents is None:
        _, incumbents = resolve(resolved, exclude=[own_domain] if own_domain else None)
    places = local_pack(data)
    hosts = [urlparse(item.get("link", "")).netloc for item in organic_results(data)]

    opportunity = assess_opportunity(
        hosts,
        profile=resolved,
        incumbents=incumbents,
        own_domain=own_domain,
        has_local_pack=bool(places),
    )
    fetched = [page for page in pages if page.ok]
    clusters = cluster_headings(fetched)
    majority = max(2, len(fetched) // 2)

    required = [c for c in clusters if c.page_count >= majority]
    secondary = [c for c in clusters if majority > c.page_count >= 2]
    unique = [c for c in clusters if c.page_count == 1]

    questions = people_also_ask(data)
    related = related_searches(data)

    return {
        "keyword": keyword,
        "opportunity": opportunity.to_dict(),
        "ranking_results": summarize_results(data, incumbents, own_domain),
        "local_pack": [
            {"title": place.get("title"), "rating": place.get("rating")} for place in places[:5]
        ],
        "format_signals": format_signals(pages),
        "consensus": assess_consensus(clusters, len(fetched)),
        "required_sections": [cluster.to_dict() for cluster in required],
        "secondary_sections": [cluster.to_dict() for cluster in secondary[:20]],
        "unique_angles": [cluster.label for cluster in unique[:25]],
        "questions_to_answer": questions,
        "queries_by_intent": group_queries([keyword, *questions, *related]),
        "related_searches": related,
        "failed_fetches": [{"url": page.url, "error": page.error} for page in pages if not page.ok],
        "notes": [
            "Consensus sections are table stakes, not a differentiator. Cover them, "
            "then win on what only this business can say: real prices, real protocols, "
            "real before/after photos, and named practitioners.",
            "Answer the 'questions_to_answer' verbatim as H2s or FAQ entries -- they are "
            "literal user phrasings, so they match how people actually search.",
        ],
    }


# -- matching against what is already published ------------------------------


def match_topics(topics: list[str], posts: list[dict], *, threshold: float = 0.4) -> dict:
    """Split SERP topics into those the blog already covers and those it doesn't.

    Uses *containment* rather than Jaccard similarity: a post's title and excerpt
    carry many more tokens than a heading does, so a symmetric measure would score
    every real match near zero. The question being asked is "are this topic's words
    present in that post", not "are the two texts alike".
    """
    prepared = [
        (post, tokens(f"{post.get('title', '')} {post.get('excerpt') or ''}")) for post in posts
    ]
    covered: list[dict] = []
    gaps: list[str] = []
    for topic in topics:
        topic_tokens = tokens(topic)
        if not topic_tokens:
            continue
        best_post, best_score = None, 0.0
        for post, post_tokens in prepared:
            score = len(topic_tokens & post_tokens) / len(topic_tokens)
            if score > best_score:
                best_post, best_score = post, score
        if best_post is not None and best_score >= threshold:
            covered.append(
                {
                    "topic": topic,
                    "score": round(best_score, 2),
                    "post_id": best_post.get("id"),
                    "post_title": best_post.get("title"),
                    "post_url": best_post.get("url"),
                }
            )
        else:
            gaps.append(topic)
    return {"covered": covered, "gaps": gaps}
