"""Morning + Evening housing-news brief dispatchers.

Curated digest emails sent at 7:30 AM and 5:30 PM America/Chicago to every
approved member. The Housing News is free forever for everyone in housing.

- Morning Brief: top 8 publisher articles from last 14h + 1 podcast pick + 1
  recent member essay.
- Evening Brief: top 8 publisher articles from last 8h + a "Trending across
  housing · 24h" block + 1 recent member essay.

Each send records a `brief_dispatches` row so opens/clicks can be tracked via
the existing services/tracking.py wrapper.
"""
import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.brevo import (
    BRIEF_SENDER_EMAIL,
    BRIEF_SENDER_NAME,
    build_brief_html,
    send_brief_email,
)
from services.podcasts_directory import get_directory
from services.resend_broadcasts import create_broadcast, send_broadcast
from services.trending import compute_trending

logger = logging.getLogger(__name__)


# In-process cache for build_brief_payload. The brief content only changes
# when the aggregator re-ingests articles (every 15 min via scheduler), so
# rebuilding it on every /api/today hit is wasteful — that's what was
# making the /today page hang for signed-in users on production. 5-minute
# TTL keeps the payload fresh enough while making subsequent calls
# essentially free.
#
# Key: f"brief:{kind}"  →  (payload_dict, expires_at_unix_ts)
_BRIEF_CACHE: dict = {}
_BRIEF_TTL_SECONDS = 300


def _brief_cache_get(kind: str):
    entry = _BRIEF_CACHE.get(f"brief:{kind}")
    if entry and entry[1] > time.time():
        return entry[0]
    return None


def _brief_cache_set(kind: str, payload: dict) -> None:
    _BRIEF_CACHE[f"brief:{kind}"] = (payload, time.time() + _BRIEF_TTL_SECONDS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def _fetch_top_articles(db, hours: int, limit: int = 8) -> list[dict]:
    """Top N most recent publisher articles in the last `hours`, deduped by publisher."""
    publishers = await db.agg_publishers.find(
        {"active": True},
        {"_id": 0, "id": 1, "slug": 1, "name": 1, "category": 1, "logo_url": 1, "homepage_url": 1},
    ).to_list(500)
    pub_index = {p["id"]: p for p in publishers}
    if not pub_index:
        return []
    cutoff = _cutoff_iso(hours)
    pool = await db.agg_articles.find(
        {
            "publisher_id": {"$in": list(pub_index.keys())},
            "published_at": {"$gte": cutoff},
            "hidden": {"$ne": True},
        },
        {"_id": 0},
    ).sort("published_at", -1).limit(limit * 4).to_list(limit * 4)
    # Dedupe by publisher so one outlet can't dominate the brief
    out: list[dict] = []
    seen_pubs: set = set()
    for it in pool:
        if it["publisher_id"] in seen_pubs:
            continue
        seen_pubs.add(it["publisher_id"])
        it["publisher"] = pub_index.get(it["publisher_id"])
        out.append(it)
        if len(out) >= limit:
            break
    # If dedupe left us short, allow repeats from the pool
    if len(out) < limit:
        existing_ids = {a.get("id") for a in out}
        for it in pool:
            if it.get("id") in existing_ids:
                continue
            it["publisher"] = pub_index.get(it["publisher_id"])
            out.append(it)
            if len(out) >= limit:
                break
    return out


async def _fetch_top_podcast_async(timeout_s: float = 2.0) -> Optional[dict]:
    """Non-blocking variant for the interactive /api/today path. Reads
    only from the in-process directory cache (never blocks on RSS).
    First user after a cold pod start gets no podcast; the background
    refresh triggered by the fast getter fills the cache shortly after.
    """
    from services.podcasts_directory import get_directory_fast
    _ = timeout_s  # kept for backwards-compat with callers; no longer needed
    try:
        directory = get_directory_fast()
    except Exception:
        logger.exception("podcast directory fetch failed")
        return None
    items = directory.get("items") if isinstance(directory, dict) else None
    if not items:
        return None
    with_eps = [p for p in items if p.get("latest_episode")]
    if not with_eps:
        return None
    with_eps.sort(
        key=lambda p: (p.get("latest_episode") or {}).get("published_at", ""),
        reverse=True,
    )
    return with_eps[0]


def _fetch_top_podcast() -> Optional[dict]:
    """Synchronous variant kept for compatibility with the email-dispatch
    path, which uses `use_cache=False`. Has no timeout because the email
    job runs on a background scheduler where a slow RSS feed is fine.
    """
    try:
        directory = get_directory()
    except Exception:
        logger.exception("podcast directory fetch failed")
        return None
    items = directory.get("items") if isinstance(directory, dict) else None
    if not items:
        return None
    with_eps = [p for p in items if p.get("latest_episode")]
    if not with_eps:
        return None
    with_eps.sort(
        key=lambda p: (p.get("latest_episode") or {}).get("published_at", ""),
        reverse=True,
    )
    return with_eps[0]


async def _fetch_top_essay(db) -> Optional[dict]:
    """Most recent approved essay with author info attached."""
    essay = await db.posts.find_one(
        {"kind": "essay", "status": "approved"},
        {
            "_id": 0,
            "post_id": 1,
            "title": 1,
            "subtitle": 1,
            "user_id": 1,
            "release_at": 1,
            "created_at": 1,
            "read_time_minutes": 1,
        },
        sort=[("release_at", -1)],
    )
    if not essay:
        return None
    profile = await db.profiles.find_one(
        {"user_id": essay["user_id"]},
        {"_id": 0, "name": 1, "market": 1},
    )
    if profile:
        essay["author"] = profile
    return essay


async def _fetch_trending(db, hours: int = 24, limit: int = 5) -> list[dict]:
    cutoff = _cutoff_iso(hours)
    articles = await db.agg_articles.find(
        {"published_at": {"$gte": cutoff}, "hidden": {"$ne": True}},
        {"_id": 0, "title": 1},
    ).to_list(500)
    titles = [a.get("title") or "" for a in articles]
    return compute_trending(titles, limit=limit)


async def build_brief_payload(db, kind: str, use_cache: bool = True) -> dict:
    """Build content for either 'morning' or 'evening' brief.

    Cached for 5 minutes in-process — the underlying article pool only
    changes when the aggregator re-ingests (every 15 min), so we don't
    need to rebuild this on every /api/today hit. Pass `use_cache=False`
    from the email-dispatch path so a fresh brief is always sent.
    """
    if use_cache:
        cached = _brief_cache_get(kind)
        if cached is not None:
            return cached

    if kind == "morning":
        articles = await _fetch_top_articles(db, hours=14, limit=8)
        # Interactive path (use_cache=True): hard 2s timeout on the podcast
        # so a slow external RSS feed can never hang /api/today again.
        # Email dispatch path: use the blocking variant, no urgency.
        if use_cache:
            podcast = await _fetch_top_podcast_async(timeout_s=2.0)
        else:
            podcast = _fetch_top_podcast()
        extra = {"podcast": podcast, "trending": None}
    else:
        articles = await _fetch_top_articles(db, hours=8, limit=8)
        # If 8h window is too thin, widen to 14h for the evening brief.
        if len(articles) < 5:
            articles = await _fetch_top_articles(db, hours=14, limit=8)
        extra = {
            "podcast": None,
            "trending": await _fetch_trending(db, hours=24, limit=5),
        }
    essay = await _fetch_top_essay(db)
    payload = {"kind": kind, "articles": articles, "essay": essay, **extra}
    if use_cache:
        _brief_cache_set(kind, payload)
    return payload


async def send_brief(db, kind: str, dry_run: bool = False) -> dict:
    """Send the morning or evening brief to the newsletter audience via the
    Resend Broadcasts API. One API call → Resend fans out to the entire
    audience (currently 14k contacts in "General"). Resend handles
    per-recipient unsubscribe tokens + deliverability.

    If `dry_run=True`, builds the payload but does NOT create or send the
    broadcast.

    The audience ID is read from `RESEND_BRIEF_AUDIENCE_ID` (defaults to the
    General audience). Members who opted out globally (`brief_optout: True`)
    are handled via Resend's audience `unsubscribed` flag — the per-window
    opt-outs (`brief_morning_optout`, `brief_evening_optout`) are no longer
    honored at send time (operator decision, 2026-02-23).

    Tracking: writes a single row to `db.brief_broadcasts` per send with the
    `broadcast_id` so the admin can look it up in the Resend dashboard.
    """
    if kind not in ("morning", "evening"):
        raise ValueError("kind must be 'morning' or 'evening'")
    payload = await build_brief_payload(db, kind, use_cache=False)
    if not payload["articles"]:
        logger.warning("Brief %s aborted — no articles available", kind)
        return {"sent": 0, "skipped_no_articles": True, "kind": kind}

    try:
        from services.release_window import CHICAGO
        today_label = datetime.now(CHICAGO).strftime("%a %b %-d")
    except Exception:
        today_label = datetime.utcnow().strftime("%a %b %-d")
    label_word = "Morning" if kind == "morning" else "Evening"
    subject = f"Housing News · {label_word} Brief · {today_label}"

    audience_id = os.environ.get(
        "RESEND_BRIEF_AUDIENCE_ID",
        "e680753d-e3c1-40db-9286-1418fc25bf63",  # default General audience
    )

    if dry_run:
        return {
            "dry_run": True,
            "kind": kind,
            "subject": subject,
            "audience_id": audience_id,
            "articles_count": len(payload["articles"]),
            "has_podcast": bool(payload.get("podcast")),
            "has_trending": bool(payload.get("trending")),
            "has_essay": bool(payload.get("essay")),
        }

    html = build_brief_html(kind, payload, broadcast=True)

    # Step 1: create the broadcast (draft).
    created = await asyncio.to_thread(
        create_broadcast,
        audience_id,
        subject,
        html,
        BRIEF_SENDER_EMAIL,
        BRIEF_SENDER_NAME,
        BRIEF_SENDER_EMAIL,
        f"Brief / {kind} / {today_label}",
    )
    if not created or created.get("error"):
        logger.error("Brief %s create_broadcast failed: %s", kind, created)
        return {
            "sent": 0,
            "kind": kind,
            "error": (created or {}).get("error", "unknown"),
            "subject": subject,
        }
    broadcast_id = created.get("id")

    # Step 2: trigger the send.
    triggered = await asyncio.to_thread(send_broadcast, broadcast_id)
    if not triggered or triggered.get("error"):
        logger.error("Brief %s send_broadcast failed (id=%s): %s", kind, broadcast_id, triggered)
        return {
            "sent": 0,
            "kind": kind,
            "broadcast_id": broadcast_id,
            "error": (triggered or {}).get("error", "unknown"),
            "subject": subject,
        }

    # Step 3: record locally so the admin can correlate.
    try:
        await db.brief_broadcasts.insert_one({
            "broadcast_id": broadcast_id,
            "kind": f"brief_{kind}",
            "audience_id": audience_id,
            "subject": subject,
            "articles_count": len(payload["articles"]),
            "created_at": _now_iso(),
        })
    except Exception:
        logger.exception("brief_broadcasts insert failed (broadcast_id=%s)", broadcast_id)

    logger.info(
        "Brief %s broadcast queued (id=%s, articles=%s)",
        kind, broadcast_id, len(payload["articles"]),
    )
    return {
        "sent": 1,
        "kind": kind,
        "broadcast_id": broadcast_id,
        "subject": subject,
        "articles_count": len(payload["articles"]),
        "audience_id": audience_id,
    }


async def send_morning_brief(db) -> dict:
    return await send_brief(db, "morning")


async def send_evening_brief(db) -> dict:
    return await send_brief(db, "evening")
