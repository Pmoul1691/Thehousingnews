"""Admin analytics dashboard."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header

from services.auth_helpers import get_current_user, is_admin_email, is_user_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/analytics", tags=["analytics"])


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("")
    async def summary(admin=Depends(_admin)):
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        # Member counts
        total_approved = await db.users.count_documents({"status": "approved"})
        suspended = await db.users.count_documents({"suspended": True})
        with_profile = await db.profiles.count_documents({})
        supporters = await db.users.count_documents({"supporter_until": {"$gt": now_iso}})

        # Application funnel
        pending = await db.applications.count_documents({"status": "pending"})
        approved = await db.applications.count_documents({"status": "approved"})
        declined = await db.applications.count_documents({"status": "declined"})

        # Posts per week (last 8 weeks of released posts)
        posts_per_week = []
        for i in range(8):
            week_end = now - timedelta(days=7 * i)
            week_start = week_end - timedelta(days=7)
            count = await db.posts.count_documents({
                "release_at": {"$gte": week_start.isoformat(), "$lt": week_end.isoformat(), "$lte": now_iso},
                "status": {"$nin": ["declined", "hidden"]},
            })
            posts_per_week.append({
                "week_start": week_start.date().isoformat(),
                "count": count,
            })
        posts_per_week.reverse()  # chronological

        # Active members (distinct authors in last 14 days)
        cutoff_14 = (now - timedelta(days=14)).isoformat()
        active_pipeline = [
            {"$match": {"release_at": {"$gte": cutoff_14, "$lte": now_iso}, "status": {"$nin": ["declined", "hidden"]}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"},
        ]
        active_agg = await db.posts.aggregate(active_pipeline).to_list(1)
        active_members_14d = (active_agg[0]["count"] if active_agg else 0)

        # Top markets (count members per market)
        markets_pipeline = [
            {"$group": {"_id": "$market", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        markets_agg = await db.profiles.aggregate(markets_pipeline).to_list(10)
        top_markets = [{"market": m["_id"], "count": m["count"]} for m in markets_agg if m["_id"]]

        # Open flags
        open_flags = await db.flags.count_documents({"resolved": False})

        # Pete picks count (active, last 30 days)
        cutoff_30 = (now - timedelta(days=30)).isoformat()
        pete_picks_count = await db.posts.count_documents({
            "is_pete_pick": True,
            "release_at": {"$gte": cutoff_30, "$lte": now_iso},
        })

        return {
            "members": {
                "total_approved": total_approved,
                "suspended": suspended,
                "with_profile": with_profile,
                "supporters": supporters,
                "active_14d": active_members_14d,
            },
            "application_funnel": {
                "pending": pending,
                "approved": approved,
                "declined": declined,
            },
            "posts_per_week": posts_per_week,
            "top_markets": top_markets,
            "open_flags": open_flags,
            "pete_picks_30d": pete_picks_count,
            "generated_at": now_iso,
        }

    @router.get("/email")
    async def email_summary(admin=Depends(_admin)):
        """Aggregate open / click stats per recent dispatch batch."""
        now = datetime.now(timezone.utc)
        cutoff_30 = (now - timedelta(days=30)).isoformat()

        # Group dispatches by kind+window_label (digests) or kind+post_id (essays)
        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff_30}}},
            {"$group": {
                "_id": {
                    "kind": "$kind",
                    "post_id": "$post_id",
                    "window_label": "$window_label",
                },
                "sent": {"$sum": 1},
                "opened": {"$sum": {"$cond": [{"$ifNull": ["$first_opened_at", False]}, 1, 0]}},
                "clicked": {"$sum": {"$cond": [{"$ifNull": ["$first_clicked_at", False]}, 1, 0]}},
                "first_at": {"$min": "$created_at"},
            }},
            {"$sort": {"first_at": -1}},
            {"$limit": 30},
        ]
        rows = await db.email_dispatches.aggregate(pipeline).to_list(30)
        items = []
        total_sent = total_opened = total_clicked = 0
        for r in rows:
            kind = r["_id"].get("kind") or "unknown"
            label = r["_id"].get("window_label") or r["_id"].get("post_id") or ""
            sent = r.get("sent", 0)
            opened = r.get("opened", 0)
            clicked = r.get("clicked", 0)
            total_sent += sent
            total_opened += opened
            total_clicked += clicked
            items.append({
                "kind": kind,
                "label": label,
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
                "open_rate": round((opened / sent) * 100, 1) if sent else 0,
                "click_rate": round((clicked / sent) * 100, 1) if sent else 0,
                "first_at": r.get("first_at"),
            })
        return {
            "totals": {
                "sent": total_sent,
                "opened": total_opened,
                "clicked": total_clicked,
                "open_rate": round((total_opened / total_sent) * 100, 1) if total_sent else 0,
                "click_rate": round((total_clicked / total_sent) * 100, 1) if total_sent else 0,
            },
            "items": items,
            "generated_at": now.isoformat(),
        }

    return router
