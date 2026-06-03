"""Authenticated landing page bundle — everything a member needs on login.

Single endpoint that returns:
  - briefing:        the current window's briefing (morning before 5:30 PM CT,
                     evening after) using the existing build_brief_payload
  - recent_essays:   5 most recent approved member essays
  - top_aggregator:  4 freshest publisher articles in the last 24h (deduped by
                     publisher), independent of the briefing pick
  - my_draft:        the user's in-progress draft (or None)
  - notifications:   counts of unseen replies + new followers since the user's
                     last visit to /api/today
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Cookie, Header, Response

from services.auth_helpers import get_current_user
from services.briefings import build_brief_payload
from services.release_window import now_chicago

logger = logging.getLogger(__name__)


def _set_private_no_store(response: Response) -> None:
    """Personalized payload — never let any cache (browser, Cloudflare, CDN)
    keep this. Two users on the same edge POP must NEVER see each other's
    notifications, drafts, or last-seen counters."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization, Cookie"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_brief_kind() -> str:
    """Morning brief is shown from 7:30 AM until 5:30 PM CT, evening after."""
    n = now_chicago()
    morning_start = n.replace(hour=7, minute=30, second=0, microsecond=0)
    evening_start = n.replace(hour=17, minute=30, second=0, microsecond=0)
    if morning_start <= n < evening_start:
        return "morning"
    return "evening"


def setup(db):
    router = APIRouter(prefix="/api/today", tags=["today"])

    @router.get("")
    async def today_bundle(
        response: Response,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        _set_private_no_store(response)
        user = await get_current_user(db, session_token, authorization)
        user_id = user["user_id"]
        last_seen = user.get("last_today_seen_at")

        # ─── Briefing for the current window ───────────────────────────────
        kind = _current_brief_kind()
        try:
            briefing = await build_brief_payload(db, kind)
        except Exception:
            logger.exception("today: brief payload failed")
            briefing = {"kind": kind, "articles": [], "essay": None}

        # ─── Recent member essays (last 5, approved) ───────────────────────
        essays_raw = await db.posts.find(
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
        ).sort("release_at", -1).limit(5).to_list(5)

        author_ids = list({e["user_id"] for e in essays_raw if e.get("user_id")})
        profiles_by_uid: dict = {}
        if author_ids:
            async for prof in db.profiles.find(
                {"user_id": {"$in": author_ids}},
                {"_id": 0, "user_id": 1, "name": 1, "market": 1, "avatar_path": 1},
            ):
                profiles_by_uid[prof["user_id"]] = prof
        for e in essays_raw:
            e["author"] = profiles_by_uid.get(e["user_id"]) or {"name": "—"}

        # ─── Top aggregator (last 24h, deduped by publisher) ───────────────
        from datetime import timedelta
        cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        pool = await db.agg_articles.find(
            {"published_at": {"$gte": cutoff_24h}, "hidden": {"$ne": True}},
            {"_id": 0, "id": 1, "title": 1, "snippet": 1, "publisher_id": 1,
             "original_url": 1, "published_at": 1},
        ).sort("published_at", -1).limit(24).to_list(24)
        pub_ids = list({a["publisher_id"] for a in pool})
        pubs_by_id: dict = {}
        if pub_ids:
            async for p in db.agg_publishers.find(
                {"id": {"$in": pub_ids}},
                {"_id": 0, "id": 1, "name": 1, "slug": 1, "homepage_url": 1,
                 "category": 1, "logo_url": 1},
            ):
                pubs_by_id[p["id"]] = p
        top_aggregator: list = []
        seen_pubs: set = set()
        for a in pool:
            if a["publisher_id"] in seen_pubs:
                continue
            seen_pubs.add(a["publisher_id"])
            a["publisher"] = pubs_by_id.get(a["publisher_id"])
            top_aggregator.append(a)
            if len(top_aggregator) >= 4:
                break

        # ─── My draft ──────────────────────────────────────────────────────
        my_draft = await db.drafts.find_one(
            {"user_id": user_id},
            {"_id": 0, "kind": 1, "title": 1, "text": 1, "updated_at": 1},
        )

        # ─── Notifications (replies on my posts + new followers) ───────────
        new_replies = 0
        new_followers = 0
        try:
            # My approved posts
            my_posts = await db.posts.find(
                {"user_id": user_id, "status": "approved"},
                {"_id": 0, "post_id": 1},
            ).to_list(500)
            my_post_ids = [p["post_id"] for p in my_posts]
            if my_post_ids:
                reply_filter = {
                    "post_id": {"$in": my_post_ids},
                    "user_id": {"$ne": user_id},
                }
                if last_seen:
                    reply_filter["created_at"] = {"$gt": last_seen}
                new_replies = await db.replies.count_documents(reply_filter)
        except Exception:
            logger.exception("today: replies count failed")

        try:
            follow_filter: dict = {"following_user_id": user_id}
            if last_seen:
                follow_filter["created_at"] = {"$gt": last_seen}
            new_followers = await db.follows.count_documents(follow_filter)
        except Exception:
            logger.exception("today: follows count failed")

        # Stamp last-seen so next visit's notifications are fresh
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_today_seen_at": _now_iso()}},
        )

        return {
            "viewer": {
                "user_id": user_id,
                "name": user.get("name") or "",
                "status": user.get("status"),
            },
            "briefing": briefing,
            "recent_essays": essays_raw,
            "top_aggregator": top_aggregator,
            "my_draft": my_draft,
            "notifications": {
                "new_replies": new_replies,
                "new_followers": new_followers,
                "last_seen_at": last_seen,
            },
        }

    return router
