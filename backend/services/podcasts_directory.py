"""Top 10 Residential Real Estate Podcasts directory.

- Static curated list of 10 podcasts (data lives here, not in DB).
- Pulls cover art + latest episode dynamically from each show's RSS feed.
- For shows that don't expose a stable RSS URL, the iTunes Lookup API is used
  to resolve `feedUrl` from the Apple Podcast ID.
- Everything is cached in-process for 1 hour to keep traffic to publisher feeds
  polite and to keep the page fast.
- Per-podcast RSS fetches are run concurrently via a thread pool so the cold
  cache fill takes ~2s instead of ~12s.

The cache is per-process — fine for a single backend pod; a Redis layer can be
swapped in later if the deployment scales horizontally.
"""
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple

import feedparser
import httpx

logger = logging.getLogger(__name__)


# Curated directory. Order here is the canonical ranking — frontend renders
# them in this order. RSS_LOOKUP means "use iTunes Lookup API to resolve".
RSS_LOOKUP = "__APPLE_LOOKUP__"

PODCASTS = [
    {
        "id": "biggerpockets-real-estate",
        "title": "BiggerPockets Real Estate Podcast",
        "host": "Dave Meyer",
        "description": "Tactics, deal walkthroughs, and conversations with investors building wealth in today's market. New episodes Monday, Wednesday, Friday.",
        "website": "https://www.biggerpockets.com/podcasts/real-estate",
        "apple_url": "https://podcasts.apple.com/us/podcast/biggerpockets-real-estate-podcast/id594419649",
        "apple_id": "594419649",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": "https://www.biggerpockets.com/podcast.rss",
    },
    {
        "id": "real-estate-rockstars",
        "title": "Real Estate Rockstars",
        "host": "Aaron Amuchastegui",
        "description": "Over six million downloads. Interviews with top-producing agents, brokers, and investors on what's actually working.",
        "website": "https://realestaterockstarsnetwork.com",
        "apple_url": "https://podcasts.apple.com/us/podcast/real-estate-rockstars-podcast/id832885584",
        "apple_id": "832885584",
        "spotify_url": "https://open.spotify.com/show/0SNeDBANSt0mGBk6laoJEo",
        "spotify_id": "0SNeDBANSt0mGBk6laoJEo",
        "rss_url": "https://hibandigital.libsyn.com/rss",
    },
    {
        "id": "tom-ferry",
        "title": "The Tom Ferry Podcast Experience",
        "host": "Tom Ferry",
        "description": "The industry's leading agent coach on mindset, production, and team-building. Multi-format weekly content.",
        "website": "https://www.tomferry.com/podcast/",
        "apple_url": "https://podcasts.apple.com/us/podcast/the-tom-ferry-podcast-experience/id1076436648",
        "apple_id": "1076436648",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": "https://feed.podbean.com/tomferry/feed.xml",
    },
    {
        "id": "realtrending",
        "title": "RealTrending",
        "host": "Tracey Velt",
        "description": "HousingWire's weekly show featuring brokerage leaders, top agents, and industry experts on trends and the business of real estate.",
        "website": "https://www.housingwire.com/shows/realtrending/",
        "apple_url": "https://podcasts.apple.com/us/podcast/realtrending/id1201340557",
        "apple_id": "1201340557",
        "spotify_url": "https://open.spotify.com/show/0XxJHcZ92fbUVNmtaRNF8o",
        "spotify_id": "0XxJHcZ92fbUVNmtaRNF8o",
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "mrea",
        "title": "The Millionaire Real Estate Agent (MREA Podcast)",
        "host": "Jason Abrams",
        "description": "Keller Williams' flagship podcast. Proven models and systems for building a real estate business, drawn from the bestselling Gary Keller book.",
        "website": "https://millionaireagentpodcast.com/",
        "apple_url": "https://podcasts.apple.com/us/podcast/the-millionaire-real-estate-agent-the-mrea-podcast/id1712458115",
        "apple_id": "1712458115",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "referrals",
        "title": "The Referrals Podcast",
        "host": "Michael J. Maher",
        "description": "Weekly conversations on building a referral-based business, based on the (7L) Seven Levels of Communication framework.",
        "website": None,
        "apple_url": "https://podcasts.apple.com/us/podcast/referrals-podcast/id1434896715",
        "apple_id": "1434896715",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": "https://referralspodcast.libsyn.com/rss",
    },
    {
        "id": "brian-buffini",
        "title": "The Brian Buffini Show",
        "host": "Brian Buffini",
        "description": "Buffini & Company founder on growing a referral business, leadership, and personal development. Long-running and consistently top-ranked.",
        "website": "https://www.thebrianbuffinishow.com/",
        "apple_url": "https://podcasts.apple.com/us/podcast/the-brian-buffini-show/id1089027054",
        "apple_id": "1089027054",
        "spotify_url": "https://open.spotify.com/show/5t4rlBQz31cXiYeyirtMJC",
        "spotify_id": "5t4rlBQz31cXiYeyirtMJC",
        "rss_url": "https://feeds.acast.com/public/shows/61a7bc4c981ee80013e20d42",
    },
    {
        "id": "ninja-selling",
        "title": "The Ninja Selling Podcast",
        "host": "Rob Nelson, Eric Thompson",
        "description": "Practical episodes built around the Ninja Selling system. Flow, consistency, and the habits behind top agent production.",
        "website": "https://theninjasellingpodcast.com/",
        "apple_url": "https://podcasts.apple.com/us/podcast/ninja-selling-podcast/id1448214127",
        "apple_id": "1448214127",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": "https://ninjaselling.libsyn.com/rss",
    },
    {
        "id": "real-estate-rookie",
        "title": "Real Estate Rookie",
        "host": "Ashley Kehr, Tony J. Robinson",
        "description": "BiggerPockets' beginner-investor podcast. First deals, deal analysis, and Q&A for new residential investors.",
        "website": "https://www.biggerpockets.com/podcasts/real-estate-rookie",
        "apple_url": "https://podcasts.apple.com/us/podcast/real-estate-rookie/id1499646507",
        "apple_id": "1499646507",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "massive-agent",
        "title": "Massive Agent Podcast",
        "host": "Dustin Brohm",
        "description": "Marketing, lead generation, and scalable systems for solo agents and small teams. Part of the Broke Agent Media network.",
        "website": "https://massiveagentpodcast.buzzsprout.com/",
        "apple_url": "https://podcasts.apple.com/us/podcast/massive-agent-podcast/id1335300981",
        "apple_id": "1335300981",
        "spotify_url": "https://open.spotify.com/show/3c5qSDbcwlPbiydjqWYEze",
        "spotify_id": "3c5qSDbcwlPbiydjqWYEze",
        "rss_url": "https://feeds.buzzsprout.com/147449.rss",
    },
    {
        "id": "real-estate-news-for-investors",
        "title": "Real Estate News for Investors",
        "host": "Kathy Fettke",
        "description": "Short, daily news updates for residential real estate investors. Markets, rates, and policy distilled by RealWealth co-founder Kathy Fettke.",
        "website": "https://realwealth.com/real-estate-news-for-investors-podcast/",
        "apple_url": "https://podcasts.apple.com/us/podcast/real-estate-news-real-estate-investing-podcast/id1079952715",
        "apple_id": "1079952715",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "power-house",
        "title": "Power House",
        "host": "Diego Sanchez",
        "description": "HousingWire's executive interview show. Conversations with the CEOs, founders, and operators reshaping housing.",
        "website": "https://www.housingwire.com/shows/power-house/",
        "apple_url": "https://podcasts.apple.com/us/podcast/power-house/id1426081802",
        "apple_id": "1426081802",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "housingwire-daily",
        "title": "HousingWire Daily",
        "host": "HousingWire newsroom",
        "description": "HousingWire's daily housing-news show. Quick takes on the stories moving mortgage, real estate, and housing markets.",
        "website": "https://www.housingwire.com/shows/housingwire-daily/",
        "apple_url": "https://podcasts.apple.com/us/podcast/housingwire-daily/id1518666256",
        "apple_id": "1518666256",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "real-estate-today",
        "title": "Real Estate Today",
        "host": "Stephen Gasque",
        "description": "NAR's weekly radio show on buying, selling, and owning a home. Trusted, consumer-friendly real estate journalism.",
        "website": "https://www.nar.realtor/real-estate-today",
        "apple_url": "https://podcasts.apple.com/us/podcast/real-estate-today/id305356944",
        "apple_id": "305356944",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "crd-podcast",
        "title": "Center for REALTOR Development",
        "host": "Monica Neubauer",
        "description": "NAR's professional-development show. Education, specialty designations, and skill-building for working agents.",
        "website": "https://crd.realtor/crd-podcast/",
        "apple_url": "https://podcasts.apple.com/us/podcast/center-for-realtor-development/id1231174561",
        "apple_id": "1231174561",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "americas-cre-show",
        "title": "America's Commercial Real Estate Show",
        "host": "Michael Bull",
        "description": "Long-running weekly show on commercial real estate markets, trends, and deal-making. Hosted by Bull Realty CEO Michael Bull.",
        "website": "https://www.creshow.com",
        "apple_url": "https://podcasts.apple.com/us/podcast/america-s-commercial-real-estate-show/id398600916",
        "apple_id": "398600916",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
    {
        "id": "keeping-it-real",
        "title": "Keeping It Real",
        "host": "D.J. Paris",
        "description": "Interviews with top 1% REALTORS sharing the tactics and habits behind their production. New episodes weekly.",
        "website": "https://keepingitrealpod.com/",
        "apple_url": "https://podcasts.apple.com/us/podcast/keeping-it-real-podcast-secrets-of-top-1-realtors/id1237389947",
        "apple_id": "1237389947",
        "spotify_url": None,
        "spotify_id": None,
        "rss_url": RSS_LOOKUP,
    },
]


# === In-process TTL caches ===
_CACHE_TTL_S = 60 * 60  # 1 hour
_FEED_URL_CACHE: dict = {}   # apple_id -> (feed_url, expires_at)
_FEED_CACHE: dict = {}       # rss_url   -> (parsed_dict, expires_at)
_DIR_CACHE: dict = {}        # "entry"   -> (directory_dict, expires_at)
_USER_AGENT = "thehousingnews-podcast-directory/1.0 (+https://thehousingnews.com)"
# Tight per-request timeout. With 10 feeds in the thread pool, the total
# cold-fill is bounded by `_HTTP_TIMEOUT + small overhead` even when every
# feed is dead. Was 12s — caused 30-second hangs on /news the moment any
# one feed misbehaved.
_HTTP_TIMEOUT = 3.0


_DIR_REFRESH_LOCK = threading.Lock()
_DIR_REFRESHING = False


def _refresh_directory_in_background() -> None:
    """Spawn a background thread that rebuilds the in-process directory
    cache. Guarded by a lock so we never spin up more than one refresher
    at a time. Called from `get_directory_fast()` when the cache is
    stale or empty; the calling request returns instantly with whatever
    cached data exists."""
    global _DIR_REFRESHING
    with _DIR_REFRESH_LOCK:
        if _DIR_REFRESHING:
            return
        _DIR_REFRESHING = True

    def _run():
        global _DIR_REFRESHING
        try:
            get_directory()  # populates _DIR_CACHE
        except Exception:
            logger.exception("background podcast directory refresh failed")
        finally:
            with _DIR_REFRESH_LOCK:
                _DIR_REFRESHING = False

    threading.Thread(target=_run, daemon=True, name="podcast-dir-refresh").start()


def get_directory_fast() -> dict:
    """Non-blocking variant for interactive routes (/api/agg/podcasts and
    the cached brief path). Returns whatever's currently in the cache
    (fresh OR stale), and asynchronously kicks off a background rebuild
    if the data is stale or missing. The first user after a cold pod
    start gets an empty list and the page renders instantly; the
    background fill completes in a few seconds and every subsequent
    user gets the full directory.

    Use the blocking `get_directory()` from background jobs (scheduler,
    email dispatch) where waiting for fresh data is fine.
    """
    now = time.time()
    entry = _DIR_CACHE.get("entry")
    if entry and entry[1] > now:
        return entry[0]  # fresh
    # Trigger background refresh; serve stale-or-empty immediately.
    _refresh_directory_in_background()
    if entry:
        return entry[0]  # stale but rendered
    return {"items": []}


def get_directory_stale_or_empty() -> dict:
    """Used by the public /api/agg/podcasts route as a fast fallback when
    the live fetch is slower than the outer route timeout. Returns the
    last successfully built directory (even if its TTL has expired) so
    /news renders instantly with the most recent known data. If the
    cache has never been populated, returns an empty list."""
    entry = _DIR_CACHE.get("entry")
    if entry:
        return entry[0]
    return {"items": []}


def _resolve_apple_feed_url(apple_id: str) -> Optional[str]:
    """Look up the canonical RSS feedUrl via Apple's iTunes Lookup API."""
    now = time.time()
    cached = _FEED_URL_CACHE.get(apple_id)
    if cached and cached[1] > now:
        return cached[0]
    try:
        r = httpx.get(
            "https://itunes.apple.com/lookup",
            params={"id": apple_id, "entity": "podcast"},
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            logger.warning("iTunes lookup returned no results for %s", apple_id)
            return None
        feed_url = results[0].get("feedUrl")
        if feed_url:
            _FEED_URL_CACHE[apple_id] = (feed_url, now + _CACHE_TTL_S)
        return feed_url
    except Exception as e:
        logger.warning("iTunes lookup failed for %s: %s", apple_id, e)
        return None


def _largest_itunes_image(entry) -> Optional[str]:
    """Some feeds have a per-episode itunes:image; falls back to channel image."""
    val = entry.get("image") if isinstance(entry, dict) else None
    if isinstance(val, dict):
        return val.get("href") or val.get("url")
    return None


def _parse_feed(rss_url: str) -> Optional[dict]:
    """Fetch and parse an RSS feed. Returns a dict with `cover_art`,
    `episode_count`, and `latest_episode` (title, audio_url, published_at,
    published_label, duration_s). Cached for 1h."""
    now = time.time()
    cached = _FEED_CACHE.get(rss_url)
    if cached and cached[1] > now:
        return cached[0]
    try:
        r = httpx.get(rss_url, headers={"User-Agent": _USER_AGENT}, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as e:
        logger.warning("RSS fetch failed for %s: %s", rss_url, e)
        return None
    if feed.bozo and not feed.entries:
        logger.warning("Malformed RSS at %s: %s", rss_url, getattr(feed, "bozo_exception", ""))
        return None

    channel = feed.feed or {}
    cover_art = None
    img = channel.get("image") or {}
    if isinstance(img, dict):
        cover_art = img.get("href") or img.get("url")
    # itunes:image often holds the high-res version
    itunes_img = channel.get("itunes_image") or {}
    if isinstance(itunes_img, dict) and itunes_img.get("href"):
        cover_art = itunes_img.get("href")

    latest = None
    for entry in feed.entries or []:
        audio_url = None
        for enc in (entry.get("enclosures") or []):
            href = enc.get("href") or enc.get("url")
            mime = (enc.get("type") or "").lower()
            if href and (mime.startswith("audio/") or href.lower().endswith((".mp3", ".m4a", ".aac", ".ogg"))):
                audio_url = href
                break
        if not audio_url:
            continue
        published_at = entry.get("published") or entry.get("updated")
        published_iso = None
        if published_at:
            try:
                dt = parsedate_to_datetime(published_at)
                published_iso = dt.isoformat()
            except Exception:
                published_iso = None
        duration_s = None
        dur = entry.get("itunes_duration")
        if dur:
            try:
                parts = [int(p) for p in str(dur).split(":") if p.strip().isdigit()]
                if len(parts) == 3:
                    duration_s = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2:
                    duration_s = parts[0] * 60 + parts[1]
                elif len(parts) == 1:
                    duration_s = parts[0]
            except Exception:
                duration_s = None
        latest = {
            "title": entry.get("title") or "(untitled)",
            "audio_url": audio_url,
            "published_at": published_iso,
            "published_label": published_at,
            "duration_s": duration_s,
            "episode_image": _largest_itunes_image(entry),
            "link": entry.get("link"),
        }
        break  # first entry is the most recent

    out = {
        "cover_art": cover_art,
        "episode_count": len(feed.entries or []),
        "latest_episode": latest,
        "feed_title": channel.get("title"),
    }
    _FEED_CACHE[rss_url] = (out, now + _CACHE_TTL_S)
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", (s or "").lower()).strip("-")


def get_directory() -> dict:
    """Returns the curated 10-podcast directory with live RSS data merged in.
    Per-podcast failures degrade gracefully — the card still renders with the
    static metadata, just without the cover art / latest episode.

    Per-podcast RSS fetches are parallelized via a small thread pool so the
    cold-cache fill is ~2s rather than the 11s of a serial loop. Subsequent
    calls are served entirely from the in-process feed cache (1h TTL).
    """
    now = time.time()
    cached = _DIR_CACHE.get("entry")
    if cached and cached[1] > now:
        return cached[0]

    def _enrich(p: dict) -> dict:
        rss_url = p["rss_url"]
        if rss_url == RSS_LOOKUP:
            rss_url = _resolve_apple_feed_url(p["apple_id"])
        parsed = _parse_feed(rss_url) if rss_url else None
        # Fallback: if the curated RSS URL is dead (redirect to HTML, 404,
        # publisher moved hosts), resolve the canonical feed via the Apple
        # Lookup API and retry. Cached for an hour either way.
        if (not parsed or not (parsed.get("cover_art") and parsed.get("latest_episode"))) and p.get("apple_id"):
            fallback = _resolve_apple_feed_url(p["apple_id"])
            if fallback and fallback != rss_url:
                parsed2 = _parse_feed(fallback)
                if parsed2 and parsed2.get("latest_episode"):
                    parsed = parsed2
                    rss_url = fallback
        return {
            "id": p["id"],
            "title": p["title"],
            "host": p["host"],
            "description": p["description"],
            "website": p["website"],
            "apple_url": p["apple_url"],
            "apple_id": p["apple_id"],
            "apple_embed_url": f"https://embed.podcasts.apple.com/us/podcast/id{p['apple_id']}",
            "spotify_url": p["spotify_url"],
            "spotify_id": p["spotify_id"],
            "spotify_embed_url": (
                f"https://open.spotify.com/embed/show/{p['spotify_id']}"
                if p["spotify_id"] else None
            ),
            "rss_url": rss_url,
            "cover_art": (parsed or {}).get("cover_art"),
            "latest_episode": (parsed or {}).get("latest_episode"),
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        items = list(ex.map(_enrich, PODCASTS))
    out = {"items": items, "cache_ttl_seconds": _CACHE_TTL_S}
    _DIR_CACHE["entry"] = (out, now + _CACHE_TTL_S)
    return out
