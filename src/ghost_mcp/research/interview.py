"""The questions to ask before building a research profile.

A profile decides which domains count as unbeatable, and every later verdict rests on
it. Guessed wrong, the tools do not fail loudly -- they return confident,
wrong answers: a keyword the user could win reads as ``SKIP``, and one owned by
competitors the profile never heard of reads as ``OPEN``. The guessing is invisible in
the output, which is exactly what makes it worth a few minutes of questions.

So this module holds the interview rather than the profile builder holding defaults.
The questions are shared by the ``plan_research_profile`` tool (which the model can
reach on its own) and the ``set-up-research`` prompt (which the user triggers), so the
two can never drift apart.

The single highest-value question is the terminology one. Search analysis is worthless
if the seed keywords are phrases nobody types -- a business can describe itself one way
while every customer searches for another, and the resulting SERP looks winnable purely
because there is no competition for a phrase nobody uses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    """One interview question, with why it is asked and what it configures."""

    id: str
    ask: str
    why: str
    maps_to: str

    def to_dict(self) -> dict:
        return {"id": self.id, "ask": self.ask, "why": self.why, "configures": self.maps_to}


#: Ordered so the answers build on each other: what the business is, then what winning
#: looks like, then who is in the way.
INTERVIEW: tuple[Question, ...] = (
    Question(
        id="business",
        ask="What do you sell, and who buys it? One or two sentences is plenty.",
        why=(
            "Decides whether this is B2B software, consumer content, a local service or "
            "something else -- which changes what 'unbeatable competitor' even means."
        ),
        maps_to="profile description, and which bundled profile to start from",
    ),
    Question(
        id="goal",
        ask=(
            "What should the blog actually do -- bring in trials or leads, support "
            "customers you already have, or build authority in a category?"
        ),
        why=(
            "Decides which search intents are worth pursuing. A lead-generation blog "
            "wants comparison and alternatives pages; an authority blog wants how-to "
            "and informational ones. The same keyword list serves them differently."
        ),
        maps_to="which queries_by_intent groups to prioritise",
    ),
    Question(
        id="terminology",
        ask=(
            "What do your customers call themselves and what you do? Use their words, "
            "not your marketing ones -- and say if the two differ."
        ),
        why=(
            "The highest-value answer here. Research against phrases nobody types looks "
            "encouraging for the wrong reason: no competition, because no demand. If "
            "customers say 'spa' while you say 'wellness studio', every seed keyword "
            "should say spa."
        ),
        maps_to="the seed keywords to research first",
    ),
    Question(
        id="competitors",
        ask="Which companies do you lose deals to, or get compared against?",
        why=(
            "Their sites rank for your category terms, so they are incumbents whether "
            "or not they are big. These are specific to you and cannot be guessed."
        ),
        maps_to="profile domains (incumbents)",
    ),
    Question(
        id="serp_regulars",
        ask=(
            "When you search your main keywords, which sites keep showing up that "
            "aren't direct competitors -- review sites, magazines, directories, forums?"
        ),
        why=(
            "Aggregators and publishers occupy results without selling anything. They "
            "are usually what actually stands between a new page and page one."
        ),
        maps_to="profile domains (incumbents)",
    ),
    Question(
        id="unbeatable",
        ask=(
            "Of everything you just listed, which could you honestly never outrank, "
            "however good the article? And what would you call that group in a sentence?"
        ),
        why=(
            "Three of these ranking marks a keyword unwinnable on the spot, regardless "
            "of the total count. Naming the group makes the verdict readable, e.g. "
            "'3 review aggregator sites rank'."
        ),
        maps_to="dominant_domains, dominant_label and dominant_reason",
    ),
    Question(
        id="geography",
        ask=(
            "Do customers search with a place name ('massage denver'), or is it "
            "national? If local, which town or city should searches run from?"
        ),
        why=(
            "Local intent changes the correct answer from a blog post to a service or "
            "location page, and results differ by where the search runs from."
        ),
        maps_to="the location argument passed to searches",
    ),
)


def interview_plan(
    active_profile: str,
    available_profiles: list[str],
    own_domain: str | None = None,
) -> dict:
    """Return the questions to ask, plus what to do with the answers.

    Args:
        active_profile: The profile currently in force.
        available_profiles: Every profile name that already exists.
        own_domain: The blog's own domain, if it could be determined.
    """
    return {
        "instruction": (
            "Ask the user these questions before creating a profile. Ask them in "
            "conversation -- a few at a time, not as a form -- and do not guess an "
            "answer on their behalf. A wrong profile does not fail loudly; it returns "
            "confident, wrong verdicts. If the user would rather skip this, say that "
            "'general' stays active and every verdict will undercount their "
            "competitors until they add some."
        ),
        "questions": [question.to_dict() for question in INTERVIEW],
        "current_state": {
            "active_profile": active_profile,
            "available_profiles": available_profiles,
            "own_domain": own_domain,
            "own_domain_note": (
                "Excluded from incumbents automatically, so the blog is never scored as "
                "its own competition."
            ),
        },
        "then": [
            "Summarise the answers back and get a clear yes before writing anything.",
            "Call create_research_profile with the domains from 'competitors' and "
            "'serp_regulars', and the 'unbeatable' subset as dominant_domains.",
            "Call set_research_profile to activate it.",
            "Run search_serp on 3-5 seed keywords built from the user's own "
            "terminology, and show which are OPEN, CONTESTED and SKIP before writing.",
            "As real searches turn up domains the profile missed, add them with "
            "add_incumbents -- the list is expected to grow, not to be right first try.",
        ],
    }
