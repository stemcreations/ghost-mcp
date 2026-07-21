"""Which domains already own a search result, and are therefore not worth fighting.

An "incumbent" here is not a business competitor -- it is a domain that holds a
result so firmly that a better article will not displace it. Counting them is how
:func:`~ghost_mcp.research.brief.assess_opportunity` decides whether a keyword is
worth writing for at all.

That judgement is entirely niche-dependent, so nothing here is hardcoded into the
analysis:

**Profiles.** The domains owning "booking software for salons" (review aggregators,
competing vendors) share nothing with those owning "is red light therapy safe"
(hospitals, medical publishers). Three profiles ship as starting points -- ``saas``,
``wellness`` and ``general`` -- but they are only seeds. Any user can define a
profile for their own niche, and ``general`` is the default precisely so a fresh
install assumes nothing about who is running it.

**A writable store.** The useful list is the one that grows as you notice the same
domain ranking again. Custom profiles and per-profile additions live in a small JSON
file that the MCP tools maintain, so the model records a new incumbent
mid-conversation instead of the user editing config and restarting.

Precedence, lowest to highest: profile defaults, then ``SERP_INCUMBENTS`` from the
environment, then the stored custom list. Exclusions (notably the user's own domain)
are applied last and always win.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ghost_mcp.errors import GhostError

#: Public suffixes with two labels, so ``bbc.co.uk`` doesn't reduce to ``co.uk``.
_MULTI_PART_SUFFIXES = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au",
        "org.au", "co.nz", "co.za", "com.br", "co.jp", "co.in",
    }
)  # fmt: skip


#: Leading ``scheme://`` on a value that turned out to be a full URL.
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://")


def registrable(host: str) -> str:
    """Reduce a host or URL to its registrable domain: ``www.a.example.com`` -> ``example.com``.

    Accepts a full URL because the domains being recorded are usually copied straight
    out of a search result, and requiring the caller to parse them first would just
    move the bug.

    Note ``removeprefix`` rather than ``lstrip``: ``lstrip`` strips a *character set*,
    so ``"www.wellnessliving.com".lstrip("www.")`` yields ``"ellnessliving.com"`` --
    silently breaking every domain that starts with a ``w`` or a dot.
    """
    host = _SCHEME.sub("", (host or "").strip().lower())
    host = re.split(r"[/?#]", host, maxsplit=1)[0]  # drop any path, query or fragment
    host = host.rsplit("@", 1)[-1].split(":", 1)[0]  # drop userinfo and port
    host = host.rstrip(".").removeprefix("www.")
    parts = [part for part in host.split(".") if part]
    if len(parts) < 3:
        return ".".join(parts)
    if ".".join(parts[-2:]) in _MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _clean(domains: list[str] | None) -> set[str]:
    """Normalise a list of user-supplied domains, dropping blanks."""
    return {cleaned for raw in (domains or []) if (cleaned := registrable(str(raw)))}


def _union(*groups: frozenset[str]) -> frozenset[str]:
    return frozenset().union(*groups)


# -- bundled starting points -------------------------------------------------

#: User-generated and social platforms. In every profile: they rank on domain
#: authority and community signals, which no amount of article quality overcomes.
PLATFORMS = frozenset(
    {
        "reddit.com", "quora.com", "youtube.com", "wikipedia.org", "amazon.com",
        "pinterest.com", "tiktok.com", "facebook.com", "instagram.com", "linkedin.com",
        "medium.com", "x.com", "twitter.com", "glassdoor.com",
    }
)  # fmt: skip

#: Software review aggregators. These rank for practically every "<category>
#: software" query on domain authority and review volume alone.
SAAS_AGGREGATORS = frozenset(
    {
        "capterra.com", "g2.com", "getapp.com", "softwareadvice.com", "trustradius.com",
        "sourceforge.net", "crozdesk.com", "saasworthy.com", "financesonline.com",
        "softwaresuggest.com", "goodfirms.co", "trustpilot.com", "producthunt.com",
        "slashdot.org", "tekpon.com",
    }
)  # fmt: skip

#: Business and tech publishers that produce "best X software" roundups.
SAAS_PUBLISHERS = frozenset(
    {
        "forbes.com", "businessnewsdaily.com", "techradar.com", "pcmag.com",
        "zapier.com", "hubspot.com", "shopify.com", "nerdwallet.com",
        "entrepreneur.com", "inc.com", "business.com", "investopedia.com",
        "fitsmallbusiness.com", "merchantmaverick.com", "tech.co", "expertmarket.com",
        "thebalancemoney.com",
    }
)  # fmt: skip

#: Health authorities. Google treats treatment questions as YMYL ("your money or your
#: life") and leans on institutional trust, so an article rarely displaces these.
MEDICAL_AUTHORITY = frozenset(
    {
        "healthline.com", "webmd.com", "mayoclinic.org", "clevelandclinic.org",
        "medicalnewstoday.com", "verywellhealth.com", "verywellfit.com",
        "everydayhealth.com", "health.com", "harvard.edu", "hopkinsmedicine.org",
        "nih.gov", "medlineplus.gov", "aad.org", "mountsinai.org", "uclahealth.org",
        "pennmedicine.org", "houstonmethodist.org", "stanford.edu", "brownhealth.org",
        "gundersenhealth.org", "medicine.umich.edu", "yalemedicine.org", "nyulangone.org",
    }
)  # fmt: skip

#: Lifestyle and beauty magazines that routinely occupy consumer wellness results.
CONSUMER_PUBLISHERS = frozenset(
    {
        "byrdie.com", "allure.com", "self.com", "prevention.com", "menshealth.com",
        "womenshealthmag.com", "shape.com", "realsimple.com", "goodhousekeeping.com",
        "nytimes.com", "cnn.com", "vogue.com", "elle.com", "cosmopolitan.com",
        "popsugar.com", "refinery29.com", "instyle.com", "harpersbazaar.com",
        "wellandgood.com", "forbes.com",
    }
)  # fmt: skip

#: Directories and marketplaces for finding a local provider.
LOCAL_DIRECTORIES = frozenset(
    {
        "yelp.com", "tripadvisor.com", "groupon.com", "classpass.com", "spafinder.com",
        "booksy.com", "fresha.com", "vagaro.com", "mindbodyonline.com", "thumbtack.com",
        "angi.com", "nextdoor.com",
    }
)  # fmt: skip


#: Forums and social platforms, where results are written by users rather than
#: published by a business. Counting these as competition is a category error: a
#: thread ranking usually means nobody has published a good answer, so it reads as
#: unmet demand, not as a wall. Kept separate from PLATFORMS -- which also holds
#: marketplaces like Amazon that really are barriers -- because only the
#: question-asking kind carries that signal.
UGC_DOMAINS = frozenset(
    {
        "reddit.com", "quora.com", "facebook.com", "youtube.com", "instagram.com",
        "tiktok.com", "x.com", "twitter.com", "linkedin.com", "stackexchange.com",
        "stackoverflow.com", "threads.net", "discord.com", "trustpilot.com",
    }
)  # fmt: skip


def is_ugc(domain: str) -> bool:
    """True if a domain's results are user-written rather than published by a business."""
    return registrable(domain) in UGC_DOMAINS


@dataclass(frozen=True)
class Profile:
    """A niche's incumbent domains, plus the subset that alone makes a query hopeless."""

    name: str
    description: str
    domains: frozenset[str]
    #: Heavy hitters. Three of these ranking calls a keyword unwinnable regardless of
    #: the total count. Empty means "no domain group is decisive on its own".
    dominant: frozenset[str] = frozenset()
    #: How the dominant group reads in a verdict, e.g. "review aggregator".
    dominant_label: str = "incumbent"
    #: Why the dominant group is unbeatable, appended to the verdict's reason.
    dominant_reason: str = ""
    #: False for profiles the user defined, which may be edited or deleted.
    bundled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "domain_count": len(self.domains),
            "dominant_count": len(self.dominant),
            "dominant_label": self.dominant_label,
            "bundled": self.bundled,
        }


#: Seeds, not a closed set. ``general`` is the default so a fresh install makes no
#: assumption about the user's niche; the others are conveniences worth having.
BUNDLED_PROFILES: dict[str, Profile] = {
    "general": Profile(
        name="general",
        description=(
            "No niche assumptions: social platforms and marketplaces only. The default. "
            "Add your own incumbents, or create a profile for your niche."
        ),
        domains=PLATFORMS,
    ),
    "saas": Profile(
        name="saas",
        description=(
            "Selling software to businesses. Incumbents are review aggregators and "
            "'best X software' roundups. Add your own competitors' domains -- those "
            "are specific to your category, so none ship by default."
        ),
        domains=_union(SAAS_AGGREGATORS, SAAS_PUBLISHERS, PLATFORMS),
        dominant=SAAS_AGGREGATORS,
        dominant_label="review aggregator",
        dominant_reason=(
            "Aggregators own category queries through domain authority and review "
            "volume, which an article cannot replicate."
        ),
    ),
    "wellness": Profile(
        name="wellness",
        description=(
            "Consumer-facing health and treatment content. Incumbents are hospitals, "
            "medical publishers, lifestyle magazines and booking directories."
        ),
        domains=_union(MEDICAL_AUTHORITY, CONSUMER_PUBLISHERS, LOCAL_DIRECTORIES, PLATFORMS),
        dominant=MEDICAL_AUTHORITY,
        dominant_label="medical-authority",
        dominant_reason=(
            "Google treats this as a YMYL health query and favours institutional trust."
        ),
    ),
}

DEFAULT_PROFILE = "general"

#: The union of every bundled profile, for callers that want a broad default.
DEFAULT_INCUMBENTS = _union(*(profile.domains for profile in BUNDLED_PROFILES.values()))

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


# -- the writable store ------------------------------------------------------

_STORE_VERSION = 1


def data_dir() -> Path:
    """Where custom research data is kept; override with ``GHOST_MCP_DATA_DIR``.

    Loads ``.env`` explicitly rather than relying on another module having done it
    first: this is read on every store access, and a silently-ignored setting would
    send writes to the wrong directory.
    """
    load_dotenv()  # does not override real environment variables
    configured = os.environ.get("GHOST_MCP_DATA_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".ghost-mcp"


def store_path() -> Path:
    """The JSON file holding the active profile, user profiles, and custom domains."""
    return data_dir() / "incumbents.json"


def load_store() -> dict:
    """Read the store, returning an empty one if it is absent or unreadable.

    Never raises: a corrupt or hand-edited file degrades to the bundled defaults
    rather than taking the server's research tools down with it.
    """
    empty: dict = {
        "version": _STORE_VERSION,
        "active_profile": None,
        "custom": {},
        "profiles": {},
    }
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    return {
        "version": data.get("version", _STORE_VERSION),
        "active_profile": data.get("active_profile"),
        "custom": data["custom"] if isinstance(data.get("custom"), dict) else {},
        "profiles": data["profiles"] if isinstance(data.get("profiles"), dict) else {},
    }


def save_store(store: dict) -> None:
    """Write the store atomically, so an interrupted write can't corrupt it."""
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _stored_profile(name: str, raw: dict) -> Profile:
    """Rebuild a user-defined profile from its stored JSON form."""
    return Profile(
        name=name,
        description=str(raw.get("description") or ""),
        domains=frozenset(_clean(raw.get("domains"))),
        dominant=frozenset(_clean(raw.get("dominant"))),
        dominant_label=str(raw.get("dominant_label") or "incumbent"),
        dominant_reason=str(raw.get("dominant_reason") or ""),
        bundled=False,
    )


def all_profiles() -> dict[str, Profile]:
    """Every available profile: the bundled seeds plus any the user defined.

    A user-defined profile shadows a bundled one of the same name, so the defaults
    can be overridden rather than only extended.
    """
    profiles = dict(BUNDLED_PROFILES)
    for name, raw in load_store()["profiles"].items():
        if isinstance(raw, dict):
            profiles[name] = _stored_profile(name, raw)
    return profiles


def active_profile_name() -> str:
    """The profile in force: the stored one, else ``SERP_PROFILE``, else the default."""
    available = all_profiles()
    stored = load_store().get("active_profile")
    if isinstance(stored, str) and stored in available:
        return stored
    from_env = os.environ.get("SERP_PROFILE", "").strip().lower()
    return from_env if from_env in available else DEFAULT_PROFILE


def get_profile(name: str | None = None) -> Profile:
    """Look up a profile by name, falling back to the active one."""
    available = all_profiles()
    if name and name in available:
        return available[name]
    return available.get(active_profile_name(), BUNDLED_PROFILES[DEFAULT_PROFILE])


def set_active_profile(name: str) -> str:
    """Persist the active profile.

    Raises:
        GhostError: if no such profile exists.
    """
    if name not in all_profiles():
        raise GhostError(
            f"Unknown profile {name!r}. Available: {', '.join(sorted(all_profiles()))}."
        )
    store = load_store()
    store["active_profile"] = name
    save_store(store)
    return name


def create_profile(
    name: str,
    description: str,
    domains: list[str],
    *,
    dominant: list[str] | None = None,
    dominant_label: str = "incumbent",
    dominant_reason: str = "",
) -> Profile:
    """Define (or replace) a profile for a niche the bundled ones don't cover.

    Raises:
        GhostError: if the name isn't a lowercase slug, or no domains are given.
    """
    slug = (name or "").strip().lower()
    if not _NAME_PATTERN.match(slug):
        raise GhostError(
            f"Profile name {name!r} must be lowercase letters, digits, '-' or '_' "
            "(max 40 characters)."
        )
    cleaned = sorted(_clean(domains))
    if not cleaned:
        raise GhostError("A profile needs at least one incumbent domain.")
    dominant_clean = sorted(_clean(dominant) & set(cleaned))

    store = load_store()
    store["profiles"][slug] = {
        "description": description,
        "domains": cleaned,
        "dominant": dominant_clean,
        "dominant_label": dominant_label,
        "dominant_reason": dominant_reason,
    }
    save_store(store)
    return _stored_profile(slug, store["profiles"][slug])


def delete_profile(name: str) -> bool:
    """Delete a user-defined profile. Bundled profiles cannot be deleted.

    Raises:
        GhostError: if the name refers to a bundled profile.
    """
    if name in BUNDLED_PROFILES and name not in load_store()["profiles"]:
        raise GhostError(f"{name!r} is a bundled profile and cannot be deleted.")
    store = load_store()
    if name not in store["profiles"]:
        return False
    del store["profiles"][name]
    # Drop its custom domains too, or they linger as unreachable cruft and silently
    # come back if a profile with the same name is created later.
    store["custom"].pop(name, None)
    if store.get("active_profile") == name:
        store["active_profile"] = None
    save_store(store)
    return True


def custom_domains(profile: str | None = None) -> list[str]:
    """The stored custom domains for a profile, normalised and sorted."""
    name = profile or active_profile_name()
    return sorted(_clean(load_store()["custom"].get(name)))


def add_domains(domains: list[str], profile: str | None = None) -> list[str]:
    """Add domains to a profile's custom list. Returns the ones newly added."""
    name = profile or active_profile_name()
    store = load_store()
    existing = _clean(store["custom"].get(name))
    incoming = _clean(domains)
    added = sorted(incoming - existing)
    if added:
        store["custom"][name] = sorted(existing | incoming)
        save_store(store)
    return added


def remove_domains(domains: list[str], profile: str | None = None) -> list[str]:
    """Remove domains from a profile's custom list. Returns the ones removed.

    Only affects custom entries; bundled defaults are the shared baseline, not user
    data, so they are excluded from a profile via ``exclude`` instead.
    """
    name = profile or active_profile_name()
    store = load_store()
    existing = _clean(store["custom"].get(name))
    targets = _clean(domains)
    removed = sorted(existing & targets)
    if removed:
        store["custom"][name] = sorted(existing - targets)
        save_store(store)
    return removed


def env_domains() -> set[str]:
    """Domains from the ``SERP_INCUMBENTS`` environment variable."""
    return _clean(os.environ.get("SERP_INCUMBENTS", "").split(","))


def resolve(
    profile: str | Profile | None = None,
    *,
    extra: list[str] | None = None,
    exclude: list[str] | None = None,
) -> tuple[Profile, set[str]]:
    """Build the effective incumbent set for a profile.

    Merges the profile's defaults with ``SERP_INCUMBENTS`` and the stored custom list,
    then applies exclusions last so the user's own domain is never counted against
    them -- if they already rank, that is an opportunity to update, not competition.
    """
    resolved = profile if isinstance(profile, Profile) else get_profile(profile)
    domains = set(resolved.domains) | env_domains() | set(custom_domains(resolved.name))
    domains |= _clean(extra)
    return resolved, domains - _clean(exclude)
