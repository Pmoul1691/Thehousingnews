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
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.brevo import send_brief_email
from services.podcasts_directory import get_directory
from services.trending import compute_trending

logger = logging.getLogger(__name__)


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


def _fetch_top_podcast() -> Optional[dict]:
    """The most recently aired podcast episode in the directory."""
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


async def build_brief_payload(db, kind: str) -> dict:
    """Build content for either 'morning' or 'evening' brief."""
    if kind == "morning":
        articles = await _fetch_top_articles(db, hours=14, limit=8)
        extra = {"podcast": _fetch_top_podcast(), "trending": None}
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
    return {"kind": kind, "articles": articles, "essay": essay, **extra}


async def send_brief(db, kind: str, dry_run: bool = False) -> dict:
    """Send the morning or evening brief to all approved + invited members.

    If `dry_run` is True, builds the payload + recipient list but does NOT send.
    """
    if kind not in ("morning", "evening"):
        raise ValueError("kind must be 'morning' or 'evening'")
    payload = await build_brief_payload(db, kind)
    if not payload["articles"]:
        logger.warning("Brief %s aborted — no articles available", kind)
        return {"sent": 0, "skipped_no_articles": True, "kind": kind}

    recipients = await db.users.find(
        {
            "status": {"$in": ["approved", "invited"]},
            "suspended": {"$ne": True},
            "brief_optout": {"$ne": True},
            # Per-window opt-outs added in Phase 16. Either flag suppresses
            # just one window; the legacy `brief_optout` still suppresses both.
            f"brief_{kind}_optout": {"$ne": True},
        },
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(5000)
    # De-dup against member emails
    member_emails = {r["email"].lower() for r in recipients if r.get("email")}

    # Newsletter (non-member) subscribers — Phase 31 free-brief launch.
    # Each row carries its own unsubscribe_token so the brief footer can
    # one-click unsubscribe without needing to log in.
    sub_recipients = await db.newsletter_subscribers.find(
        {"status": "confirmed"},
        {"_id": 0, "email": 1, "unsubscribe_token": 1},
    ).to_list(20000)
    for s in sub_recipients:
        if (s.get("email") or "").lower() in member_emails:
            continue  # never double-send to a member who also subscribed
        recipients.append({
            "user_id": None,
            "email": s["email"],
            "name": "",
            "unsubscribe_token": s.get("unsubscribe_token"),
            "is_subscriber": True,
        })

    try:
        from services.release_window import CHICAGO
        today_label = datetime.now(CHICAGO).strftime("%a %b %-d")
    except Exception:
        today_label = datetime.utcnow().strftime("%a %b %-d")
    label_word = "Morning" if kind == "morning" else "Evening"
    subject = f"Housing News · {label_word} Brief · {today_label}"

    if dry_run:
        return {
            "dry_run": True,
            "kind": kind,
            "subject": subject,
            "recipients_total": len(recipients),
            "articles_count": len(payload["articles"]),
            "has_podcast": bool(payload.get("podcast")),
            "has_trending": bool(payload.get("trending")),
            "has_essay": bool(payload.get("essay")),
        }

    sent = 0
    failed = 0
    for r in recipients:
        dispatch_id = uuid.uuid4().hex
        try:
            await db.brief_dispatches.insert_one({
                "dispatch_id": dispatch_id,
                "kind": f"brief_{kind}",
                "recipient_user_id": r.get("user_id"),
                "recipient_email": r["email"],
                "is_subscriber": bool(r.get("is_subscriber")),
                "articles_count": len(payload["articles"]),
                "first_opened_at": None,
                "first_clicked_at": None,
                "created_at": _now_iso(),
            })
        except Exception:
            logger.exception("brief dispatch record failed for %s", r.get("email"))
        try:
            send_brief_email(
                r["email"],
                r.get("name") or "",
                subject=subject,
                kind=kind,
                payload=payload,
                dispatch_id=dispatch_id,
                unsubscribe_token=r.get("unsubscribe_token"),
            )
            sent += 1
        except Exception:
            logger.exception("brief send failed for %s", r.get("email"))
            failed += 1

    logger.info(
        "Brief %s sent to %s recipients (%s failed) — articles=%s",
        kind, sent, failed, len(payload["articles"]),
    )
    return {
        "sent": sent,
        "failed": failed,
        "kind": kind,
        "recipients_total": len(recipients),
        "articles_count": len(payload["articles"]),
    }


async def send_morning_brief(db) -> dict:
    return await send_brief(db, "morning")


async def send_evening_brief(db) -> dict:
    return await send_brief(db, "evening")
