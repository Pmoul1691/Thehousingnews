"""Regional taxonomy — fixed list of region slugs members can target.

The tiers (city → metro → state → region → national) are flat in the data:
every entry has a `tier` field but the slug is globally unique. AI tagging
and feed filtering both work off the slug; tier is only metadata used by the
UI to group the picker.

Keep this list moderate (< 60 entries) so the LLM tagging prompt stays cheap
and the chip picker stays scannable. Add more cities as the membership
spreads geographically.
"""
from typing import Optional

REGIONS = [
    # ── National ──────────────────────────────────────────────────────
    {"slug": "national",      "label": "National",            "tier": "national"},

    # ── Macro regions ────────────────────────────────────────────────
    {"slug": "northeast",     "label": "Northeast",           "tier": "region"},
    {"slug": "midwest",       "label": "Midwest",             "tier": "region"},
    {"slug": "south",         "label": "South",               "tier": "region"},
    {"slug": "west",          "label": "West",                "tier": "region"},

    # ── States (the 10 most populous + DC) ───────────────────────────
    {"slug": "ny",            "label": "New York",            "tier": "state"},
    {"slug": "ca",            "label": "California",          "tier": "state"},
    {"slug": "tx",            "label": "Texas",               "tier": "state"},
    {"slug": "fl",            "label": "Florida",             "tier": "state"},
    {"slug": "il",            "label": "Illinois",            "tier": "state"},
    {"slug": "pa",            "label": "Pennsylvania",        "tier": "state"},
    {"slug": "oh",            "label": "Ohio",                "tier": "state"},
    {"slug": "ga",            "label": "Georgia",             "tier": "state"},
    {"slug": "nc",            "label": "North Carolina",      "tier": "state"},
    {"slug": "mi",            "label": "Michigan",            "tier": "state"},
    {"slug": "ma",            "label": "Massachusetts",       "tier": "state"},
    {"slug": "wa",            "label": "Washington",          "tier": "state"},
    {"slug": "co",            "label": "Colorado",            "tier": "state"},
    {"slug": "az",            "label": "Arizona",             "tier": "state"},
    {"slug": "nj",            "label": "New Jersey",          "tier": "state"},
    {"slug": "va",            "label": "Virginia",            "tier": "state"},
    {"slug": "dc",            "label": "Washington DC",       "tier": "state"},

    # ── Metros ───────────────────────────────────────────────────────
    {"slug": "nyc-metro",     "label": "NYC Metro",           "tier": "metro"},
    {"slug": "la-metro",      "label": "LA Metro",            "tier": "metro"},
    {"slug": "chicago-metro", "label": "Chicago Metro",       "tier": "metro"},
    {"slug": "bay-area",      "label": "Bay Area",            "tier": "metro"},
    {"slug": "dfw-metro",     "label": "Dallas–Fort Worth",   "tier": "metro"},
    {"slug": "houston-metro", "label": "Houston Metro",       "tier": "metro"},
    {"slug": "miami-metro",   "label": "Miami Metro",         "tier": "metro"},
    {"slug": "atlanta-metro", "label": "Atlanta Metro",       "tier": "metro"},
    {"slug": "boston-metro",  "label": "Boston Metro",        "tier": "metro"},
    {"slug": "dc-metro",      "label": "DC Metro",            "tier": "metro"},
    {"slug": "philly-metro",  "label": "Philly Metro",        "tier": "metro"},
    {"slug": "denver-metro",  "label": "Denver Metro",        "tier": "metro"},
    {"slug": "seattle-metro", "label": "Seattle Metro",       "tier": "metro"},
    {"slug": "phoenix-metro", "label": "Phoenix Metro",       "tier": "metro"},

    # ── Major cities ─────────────────────────────────────────────────
    {"slug": "nyc",           "label": "New York City",       "tier": "city"},
    {"slug": "la",            "label": "Los Angeles",         "tier": "city"},
    {"slug": "chicago",       "label": "Chicago",             "tier": "city"},
    {"slug": "san-francisco", "label": "San Francisco",       "tier": "city"},
    {"slug": "dallas",        "label": "Dallas",              "tier": "city"},
    {"slug": "houston",       "label": "Houston",             "tier": "city"},
    {"slug": "miami",         "label": "Miami",               "tier": "city"},
    {"slug": "atlanta",       "label": "Atlanta",             "tier": "city"},
    {"slug": "boston",        "label": "Boston",              "tier": "city"},
    {"slug": "philadelphia",  "label": "Philadelphia",        "tier": "city"},
    {"slug": "seattle",       "label": "Seattle",             "tier": "city"},
    {"slug": "denver",        "label": "Denver",              "tier": "city"},
    {"slug": "austin",        "label": "Austin",              "tier": "city"},
    {"slug": "phoenix",       "label": "Phoenix",             "tier": "city"},
    {"slug": "portland",      "label": "Portland",            "tier": "city"},
    {"slug": "san-diego",     "label": "San Diego",           "tier": "city"},
    {"slug": "nashville",     "label": "Nashville",           "tier": "city"},
    {"slug": "brooklyn",      "label": "Brooklyn",            "tier": "city"},
]

# Index for O(1) validation
_ALLOWED_SLUGS = {r["slug"] for r in REGIONS}
_BY_SLUG = {r["slug"]: r for r in REGIONS}

TIER_ORDER = ["city", "metro", "state", "region", "national"]


def is_valid_slug(slug: str) -> bool:
    return slug in _ALLOWED_SLUGS


def normalise(slugs) -> list[str]:
    """Lowercase, drop dupes, drop anything not in the taxonomy. Caps at 8."""
    if not slugs:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for s in slugs:
        if not isinstance(s, str):
            continue
        s = s.strip().lower()
        if s in _ALLOWED_SLUGS and s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) >= 8:
                break
    return out


def label_for(slug: str) -> Optional[str]:
    r = _BY_SLUG.get(slug)
    return r["label"] if r else None


def all_slugs() -> list[str]:
    return [r["slug"] for r in REGIONS]


def grouped() -> dict[str, list[dict]]:
    """Return a {tier: [{slug, label}, …]} map for the UI picker."""
    out: dict[str, list[dict]] = {t: [] for t in TIER_ORDER}
    for r in REGIONS:
        out[r["tier"]].append({"slug": r["slug"], "label": r["label"]})
    return out
