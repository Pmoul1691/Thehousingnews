"""Admin analytics dashboard."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header

from services.auth_helpers import get_current_user, is_admin_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/analytics", tags=["analytics"])


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
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

    return router
