"""Unit tests for the search-research analysis (no environment or network access)."""

import json

import httpx
import pytest

from ghost_mcp.config import serper_api_key
from ghost_mcp.errors import ConfigError, GhostError, ResearchError
from ghost_mcp.research import (
    BUNDLED_PROFILES,
    INTERVIEW,
    SHARED_TOPIC_PAGES,
    RankingPage,
    SerperClient,
    active_profile_name,
    add_domains,
    all_profiles,
    assess_consensus,
    assess_opportunity,
    build_brief,
    classify_query,
    cluster_headings,
    create_profile,
    custom_domains,
    delete_profile,
    format_signals,
    get_profile,
    group_queries,
    interview_plan,
    is_ugc,
    match_topics,
    parse_page,
    registrable,
    remove_domains,
    resolve,
    set_active_profile,
    store_path,
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the incumbent store at a temp dir so tests never touch the real one."""
    monkeypatch.setenv("GHOST_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SERP_INCUMBENTS", raising=False)
    monkeypatch.delenv("SERP_PROFILE", raising=False)


# -- registrable -------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("www.wellnessliving.com", "wellnessliving.com"),  # the lstrip bug: was "ellnessliving"
        ("web.com", "web.com"),  # a leading "w" must survive
        ("WWW.Capterra.COM", "capterra.com"),
        ("health.harvard.edu", "harvard.edu"),
        ("my.clevelandclinic.org", "clevelandclinic.org"),
        ("example.co.uk", "example.co.uk"),
        ("shop.example.co.uk", "example.co.uk"),
        ("example.com.", "example.com"),
        ("", ""),
    ],
)
def test_registrable(host: str, expected: str) -> None:
    assert registrable(host) == expected


# -- profiles and the writable store -----------------------------------------


def test_default_profile_is_unopinionated() -> None:
    assert active_profile_name() == "general"
    assert get_profile().dominant == frozenset()


def test_resolve_merges_env_and_custom(monkeypatch) -> None:
    monkeypatch.setenv("SERP_INCUMBENTS", "fromenv.com, www.other.com")
    add_domains(["stored.com"], "general")
    _profile, domains = resolve("general")
    assert {"fromenv.com", "other.com", "stored.com", "reddit.com"} <= domains


def test_resolve_exclusion_wins_over_everything(monkeypatch) -> None:
    monkeypatch.setenv("SERP_INCUMBENTS", "mysite.com")
    add_domains(["mysite.com"], "general")
    _profile, domains = resolve("general", exclude=["www.mysite.com"])
    assert "mysite.com" not in domains


def test_add_and_remove_domains_persist() -> None:
    assert add_domains(["Capterra.com", "https://g2.com"], "saas") == ["capterra.com", "g2.com"]
    assert add_domains(["capterra.com"], "saas") == []  # already present
    assert custom_domains("saas") == ["capterra.com", "g2.com"]
    assert remove_domains(["capterra.com"], "saas") == ["capterra.com"]
    assert custom_domains("saas") == ["g2.com"]
    assert json.loads(store_path().read_text(encoding="utf-8"))["custom"]["saas"] == ["g2.com"]


def test_custom_domains_are_scoped_per_profile() -> None:
    add_domains(["one.com"], "saas")
    add_domains(["two.com"], "wellness")
    assert custom_domains("saas") == ["one.com"]
    assert custom_domains("wellness") == ["two.com"]


def test_create_and_activate_a_user_profile() -> None:
    created = create_profile(
        "indie-games",
        "Indie game development blogs.",
        ["steamcommunity.com", "itch.io", "gamedeveloper.com"],
        dominant=["steamcommunity.com", "notlisted.com"],
        dominant_label="platform",
    )
    assert created.bundled is False
    assert created.dominant == frozenset({"steamcommunity.com"})  # subset of domains only
    assert "indie-games" in all_profiles()

    set_active_profile("indie-games")
    assert active_profile_name() == "indie-games"
    _profile, domains = resolve()
    assert "itch.io" in domains


def test_user_profile_shadows_a_bundled_one() -> None:
    create_profile("saas", "My own take.", ["onlythis.com"])
    profile = get_profile("saas")
    assert profile.bundled is False
    assert profile.domains == frozenset({"onlythis.com"})


def test_deleting_a_profile_resets_the_active_one() -> None:
    create_profile("temp", "Throwaway.", ["a.com"])
    set_active_profile("temp")
    assert delete_profile("temp") is True
    assert active_profile_name() == "general"


def test_bundled_profiles_cannot_be_deleted() -> None:
    with pytest.raises(GhostError, match="bundled"):
        delete_profile("wellness")


@pytest.mark.parametrize("name", ["", "Has Spaces", "has/slash", "way-too-" + "x" * 40])
def test_create_profile_rejects_bad_names(name: str) -> None:
    with pytest.raises(GhostError, match="Profile name"):
        create_profile(name, "desc", ["a.com"])


def test_create_profile_normalises_the_name() -> None:
    assert create_profile("  MyNiche  ", "desc", ["a.com"]).name == "myniche"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.g2.com/categories/scheduling", "g2.com"),
        ("http://sub.example.co.uk/path?q=1", "example.co.uk"),
        ("example.com:8443", "example.com"),
    ],
)
def test_registrable_accepts_full_urls(raw: str, expected: str) -> None:
    assert registrable(raw) == expected


def test_create_profile_requires_domains() -> None:
    with pytest.raises(GhostError, match="at least one"):
        create_profile("empty", "desc", [])


def test_set_active_profile_rejects_unknown() -> None:
    with pytest.raises(GhostError, match="Unknown profile"):
        set_active_profile("nope")


def test_corrupt_store_degrades_to_defaults() -> None:
    store_path().parent.mkdir(parents=True, exist_ok=True)
    store_path().write_text("{ not json", encoding="utf-8")
    assert active_profile_name() == "general"
    assert custom_domains("general") == []


# -- opportunity verdicts ----------------------------------------------------


def test_dominant_group_triggers_skip_per_profile() -> None:
    hosts = ["healthline.com", "webmd.com", "mayoclinic.org", "someblog.com"]
    result = assess_opportunity(hosts, profile="wellness")
    assert result.verdict == "SKIP"
    assert result.dominant_count == 3
    assert "medical-authority" in result.reason
    assert "YMYL" in result.reason


def test_the_same_serp_is_open_under_a_different_profile() -> None:
    """The verdict is a function of the profile, not a global truth."""
    hosts = ["healthline.com", "webmd.com", "mayoclinic.org", "someblog.com"]
    assert assess_opportunity(hosts, profile="saas").verdict == "OPEN"


def test_saas_profile_flags_review_aggregators() -> None:
    hosts = ["capterra.com", "g2.com", "softwareadvice.com", "myrival.com"]
    result = assess_opportunity(hosts, profile="saas")
    assert result.verdict == "SKIP"
    assert "review aggregator" in result.reason
    assert result.profile == "saas"


def test_local_pack_beats_a_clean_serp() -> None:
    result = assess_opportunity(["someblog.com", "another.com"], has_local_pack=True)
    assert result.verdict == "LOCAL_INTENT"
    assert "service or location page" in result.recommendation


def test_own_domain_ranking_recommends_an_update() -> None:
    result = assess_opportunity(
        ["healthline.com", "myspa.com"],
        profile="wellness",
        own_domain="www.myspa.com",
        has_local_pack=True,
    )
    assert result.verdict == "UPDATE_EXISTING"
    assert result.own_domain_ranks is True


def test_own_domain_is_never_counted_as_an_incumbent() -> None:
    result = assess_opportunity(["reddit.com"], own_domain="reddit.com")
    assert result.incumbent_count == 0


def test_open_and_contested_thresholds() -> None:
    assert assess_opportunity(["a.com", "b.com", "c.com"]).verdict == "OPEN"
    # Published pages, not forums -- four of them is genuine competition.
    contested = ["wikipedia.org", "amazon.com", "pinterest.com", "medium.com", "a.com"]
    assert assess_opportunity(contested).verdict == "CONTESTED"


# -- forums are demand, not competition --------------------------------------


def test_forum_results_with_thin_competition_read_as_unmet_demand() -> None:
    """The signal this fixes: people asking, nobody answering, tool said 'walk away'."""
    hosts = ["reddit.com", "facebook.com", "quora.com", "medium.com", "smallfry.com"]
    result = assess_opportunity(hosts)
    assert result.verdict == "UNMET_DEMAND"
    assert result.ugc_results == 3
    assert result.competing_pages == 1
    assert "no one has published a good answer" in result.reason


def test_forums_do_not_count_toward_a_skip() -> None:
    """Seven results, but only two are published pages -- that is not a wall."""
    hosts = [
        "reddit.com", "quora.com", "youtube.com", "facebook.com", "x.com",
        "wikipedia.org", "amazon.com",
    ]  # fmt: skip
    result = assess_opportunity(hosts)
    assert result.verdict != "SKIP"
    assert result.competing_pages == 2
    assert result.ugc_results == 5


def test_heavy_real_competition_still_skips_despite_forums() -> None:
    """Forums must not rescue a query that established pages genuinely own."""
    hosts = [
        "healthline.com", "webmd.com", "mayoclinic.org", "byrdie.com", "allure.com",
        "self.com", "shape.com", "reddit.com", "quora.com",
    ]  # fmt: skip
    result = assess_opportunity(hosts, profile="wellness")
    assert result.verdict == "SKIP"


def test_ugc_and_competitor_domains_are_reported_separately() -> None:
    result = assess_opportunity(["reddit.com", "wikipedia.org"])
    assert result.ugc_domains == ["reddit.com"]
    assert result.incumbent_domains == ["wikipedia.org"]


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("www.reddit.com", True),
        ("https://www.facebook.com/groups/123", True),
        ("wikipedia.org", False),  # a platform, but not somewhere people ask for advice
        ("capterra.com", False),
        ("", False),
    ],
)
def test_is_ugc(domain: str, expected: bool) -> None:
    assert is_ugc(domain) is expected


def test_custom_incumbents_change_the_verdict() -> None:
    hosts = ["rival-a.com", "rival-b.com", "rival-c.com", "rival-d.com"]
    assert assess_opportunity(hosts).verdict == "OPEN"
    add_domains([*hosts], "general")
    assert assess_opportunity(hosts).verdict == "CONTESTED"


# -- query intent ------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # the reported bug: "best" must not outrank the guidance reading
        ("When is the best time to do contrast therapy?", "how_to"),
        ("best way to onboard staff", "how_to"),
        ("contrast therapy protocol", "how_to"),
        ("contrast therapy routine", "how_to"),
        ("how much time does setup take", "how_to"),  # not "cost"
        ("vagaro alternatives", "alternatives"),
        ("mindbody competitors", "alternatives"),
        ("switching from vagaro", "alternatives"),
        ("booking software for massage therapists", "commercial"),
        ("best salon software", "commercial"),
        ("mindbody vs vagaro pricing", "comparison"),  # comparison outranks cost
        ("how much does vagaro cost", "cost"),
        ("vagaro fees", "cost"),
        ("red light therapy near me", "local"),
        ("how often should you get a facial", "how_to"),
        ("what to expect at your first massage", "how_to"),
        ("red light therapy benefits", "informational"),
    ],
)
def test_classify_query(query: str, expected: str) -> None:
    assert classify_query(query) == expected


def test_group_queries_dedupes_case_insensitively() -> None:
    grouped = group_queries(["Massage Near Me", "massage near me", "facial cost"])
    assert grouped["local"] == ["Massage Near Me"]
    assert grouped["cost"] == ["facial cost"]


# -- page parsing ------------------------------------------------------------

_HTML = """
<html><head><title>  Facials   Explained </title></head>
<body>
  <nav><h2>Navigation</h2></nav>
  <article>
    <h2>What is a facial?</h2>
    <p>one two three four five</p>
    <h2>Related Posts</h2>
    <h3>How much does a facial cost?</h3>
    <table><tr><td>$120 per session</td></tr></table>
    <ul><li>a</li></ul>
    <p>Frequently asked questions</p>
  </article>
  <footer><h2>Footer links</h2></footer>
</body></html>
"""


def test_parse_page_extracts_structure_and_drops_chrome() -> None:
    page = parse_page("https://example.com/facials", _HTML)
    headings = [text for _level, text in page.headings]
    assert page.title == "Facials Explained"
    assert "What is a facial?" in headings
    assert "How much does a facial cost?" in headings
    assert "Navigation" not in headings  # <nav> removed
    assert "Footer links" not in headings  # <footer> removed
    assert "Related Posts" not in headings  # junk-heading pattern
    assert page.has_price_table is True
    assert page.has_faq is True
    assert page.lists == 1


# -- clustering and signals --------------------------------------------------


def _page(url: str, headings: list[str], **kwargs) -> RankingPage:
    return RankingPage(url=url, ok=True, headings=[("h2", h) for h in headings], **kwargs)


def test_cluster_headings_groups_variants_and_counts_pages() -> None:
    pages = [
        _page("a", ["How much does a facial cost?", "Benefits of facials"]),
        _page("b", ["Facial cost"]),
        _page("c", ["A completely unrelated topic"]),
    ]
    clusters = cluster_headings(pages)
    top = clusters[0]
    assert top.page_count == 2
    assert top.label == "Facial cost"  # shortest phrasing wins
    assert len(clusters) == 3


def test_cluster_headings_counts_a_page_once_per_topic() -> None:
    pages = [_page("a", ["Facial cost", "facial COST"])]
    assert cluster_headings(pages)[0].page_count == 1


def test_format_signals_recommends_price_table_on_majority() -> None:
    pages = [
        _page("a", [], word_count=1000, has_price_table=True, has_faq=True),
        _page("b", [], word_count=2000, has_price_table=True, has_faq=False),
        _page("c", [], word_count=3000, has_price_table=False, has_faq=False),
    ]
    signals = format_signals(pages)
    assert signals["median_word_count"] == 2000
    assert signals["word_count_range"] == [1000, 3000]
    assert signals["pages_with_price_table"] == 2
    assert any("pricing table" in note for note in signals["recommendations"])
    assert not any("FAQ" in note for note in signals["recommendations"])


def test_format_signals_survives_a_total_crawl_failure() -> None:
    signals = format_signals([RankingPage(url="a", ok=False, error="boom")])
    assert signals["pages_analyzed"] == 0
    assert signals["recommendations"]


# -- gap matching ------------------------------------------------------------


def test_match_topics_splits_covered_from_gaps() -> None:
    posts = [{"id": "1", "title": "The benefits of red light therapy", "excerpt": ""}]
    result = match_topics(["Benefits of red light therapy", "Contrast therapy protocols"], posts)
    assert result["gaps"] == ["Contrast therapy protocols"]
    assert result["covered"][0]["post_id"] == "1"


def test_match_topics_with_no_posts_reports_all_gaps() -> None:
    result = match_topics(["Anything at all"], [])
    assert result["gaps"] == ["Anything at all"]
    assert result["covered"] == []


# -- brief assembly ----------------------------------------------------------


def test_build_brief_assembles_sections_and_flags_own_site() -> None:
    data = {
        "organic": [
            {"title": "Mine", "link": "https://myspa.com/facials", "snippet": "  hi  "},
            {"title": "Rival", "link": "https://healthline.com/x", "snippet": ""},
        ],
        "peopleAlsoAsk": [{"question": "How often should you get a facial?"}],
        "relatedSearches": [{"query": "facial cost near me"}],
    }
    pages = [
        _page("a", ["Facial cost", "A unique angle"], word_count=900),
        _page("b", ["How much does a facial cost?"], word_count=1100),
    ]
    brief = build_brief("facials", data, pages, profile="wellness", own_domain="myspa.com")

    assert brief["opportunity"]["verdict"] == "UPDATE_EXISTING"
    assert brief["opportunity"]["profile"] == "wellness"
    assert brief["ranking_results"][0]["is_own_site"] is True
    assert brief["ranking_results"][0]["snippet"] == "hi"
    assert brief["ranking_results"][1]["is_incumbent"] is True
    assert [s["topic"] for s in brief["required_sections"]] == ["Facial cost"]
    assert brief["unique_angles"] == ["A unique angle"]
    assert brief["questions_to_answer"] == ["How often should you get a facial?"]
    assert "facial cost near me" in brief["queries_by_intent"]["local"]


def test_build_brief_reports_failed_fetches() -> None:
    pages = [RankingPage(url="https://dead.example", ok=False, error="Timeout")]
    brief = build_brief("x", {"organic": []}, pages)
    assert brief["failed_fetches"] == [{"url": "https://dead.example", "error": "Timeout"}]


# -- the Serper client -------------------------------------------------------


def _client(handler) -> SerperClient:
    return SerperClient(api_key="test-key", transport=httpx.MockTransport(handler))


def test_search_sends_key_and_location() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["X-API-KEY"]
        seen["body"] = request.content
        return httpx.Response(200, json={"organic": []})

    _client(handler).search("massage", location="Denver, Colorado, United States")
    assert seen["key"] == "test-key"
    assert b"Denver" in seen["body"]


@pytest.mark.parametrize(
    ("status", "match"),
    [(401, "API key"), (429, "credits"), (500, "status 500")],
)
def test_search_errors_are_actionable(status: int, match: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="nope")

    with pytest.raises(ResearchError, match=match):
        _client(handler).search("massage")


def test_autocomplete_unwraps_suggestions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"suggestions": [{"value": "red light therapy at home"}, {"value": ""}]}
        )

    assert _client(handler).autocomplete("red light") == ["red light therapy at home"]


def test_client_without_a_key_raises_config_error(monkeypatch) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setattr("ghost_mcp.research.serper.serper_api_key", lambda: None)
    with pytest.raises(ConfigError, match="SERPER_API_KEY"):
        SerperClient()


def test_serper_api_key_is_none_when_blank(monkeypatch) -> None:
    monkeypatch.setenv("SERPER_API_KEY", "   ")
    assert serper_api_key() is None


def test_bundled_profiles_are_self_consistent() -> None:
    for profile in BUNDLED_PROFILES.values():
        assert profile.dominant <= profile.domains, profile.name
        assert profile.description


# -- consensus ---------------------------------------------------------------


def test_no_shared_topics_is_reported_as_a_finding() -> None:
    """An incoherent SERP must not look like "nothing missing"."""
    clusters = cluster_headings(
        [_page("a", ["Branded mobile app"]), _page("b", ["Hyde Park"]), _page("c", ["01 Prepare"])]
    )
    result = assess_consensus(clusters, 3)
    assert result["has_consensus"] is False
    assert result["shared_topic_count"] == 0
    assert "not settled" in result["note"]


def test_shared_topics_report_consensus() -> None:
    clusters = cluster_headings([_page("a", ["Facial cost"]), _page("b", ["Facial cost"])])
    result = assess_consensus(clusters, 3)
    assert result["has_consensus"] is True
    assert result["note"] == ""


def test_consensus_is_not_judged_on_too_few_pages() -> None:
    assert "Too few" in assess_consensus([], 2)["note"]


def test_javascript_rendered_pages_are_flagged() -> None:
    pages = [
        _page("a", [], word_count=0),
        _page("b", [], word_count=1200),
        _page("c", [], word_count=1400),
    ]
    signals = format_signals(pages)
    assert signals["pages_without_text"] == 1
    assert any("JavaScript-rendered" in note for note in signals["recommendations"])


def test_build_brief_includes_consensus() -> None:
    brief = build_brief("x", {"organic": []}, [_page("a", ["Only here"])])
    assert brief["consensus"]["has_consensus"] is False


def test_consensus_and_gap_topics_use_one_threshold() -> None:
    """A topic on exactly 2 of 6 pages must not be 'consensus' and 'no topics' at once.

    Regression: gap analysis required a *majority* of pages while assess_consensus
    needed only two, so a topic shared by exactly two pages was simultaneously
    reported as consensus and as "no consensus topics found".
    """
    solo = ["Pricing tiers", "Staff permissions", "Mobile application", "Refund policy"]
    pages = [_page(url, ["Shared topic"]) for url in "ab"]
    pages += [_page(url, [heading]) for url, heading in zip("cdef", solo, strict=True)]

    clusters = cluster_headings(pages)
    counted = [c.label for c in clusters if c.page_count >= SHARED_TOPIC_PAGES]
    assert counted == ["Shared topic"]  # on 2 of 6 pages: below a majority, still shared
    assert assess_consensus(clusters, len(pages))["has_consensus"] is True


def test_deleting_a_profile_drops_its_custom_domains() -> None:
    """Otherwise they linger unreachable, and silently return under a reused name."""
    create_profile("temp", "Throwaway.", ["a.com"])
    add_domains(["leftover.com"], "temp")
    delete_profile("temp")
    assert "temp" not in json.loads(store_path().read_text(encoding="utf-8"))["custom"]
    create_profile("temp", "Reused name.", ["a.com"])
    assert custom_domains("temp") == []


# -- the profile interview ---------------------------------------------------


def test_interview_covers_what_a_profile_needs() -> None:
    """Every profile field a user must supply has a question that elicits it."""
    ids = {q.id for q in INTERVIEW}
    assert {"business", "goal", "terminology", "competitors", "unbeatable"} <= ids
    configures = " ".join(q.maps_to for q in INTERVIEW)
    assert "dominant_domains" in configures
    assert "domains" in configures


def test_every_question_explains_itself() -> None:
    for question in INTERVIEW:
        assert question.ask.strip(), question.id
        assert question.why.strip(), question.id
        assert question.maps_to.strip(), question.id


def test_interview_plan_reports_state_and_next_steps() -> None:
    plan = interview_plan("general", ["general", "saas"], own_domain="myblog.com")
    assert plan["current_state"]["active_profile"] == "general"
    assert plan["current_state"]["own_domain"] == "myblog.com"
    assert len(plan["questions"]) == len(INTERVIEW)
    assert any("create_research_profile" in step for step in plan["then"])
    assert any("add_incumbents" in step for step in plan["then"])
    # It must tell the model not to answer on the user's behalf.
    assert "not guess" in plan["instruction"]


def test_interview_plan_handles_an_unknown_own_domain() -> None:
    assert interview_plan("saas", ["saas"], own_domain=None)["current_state"]["own_domain"] is None
