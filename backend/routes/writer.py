"""Writer dashboard routes: stats + published/scheduled lists."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Cookie, Header, HTTPException

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me/writer", tags=["writer"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    @router.get("/stats")
    async def writer_stats(user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        now_iso = _now_iso()
        thirty = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        published_essays = await db.posts.count_documents({
            "user_id": user["user_id"], "kind": "essay",
            "release_at": {"$lte": now_iso}, "status": {"$nin": ["declined", "hidden"]},
        })
        scheduled_essays = await db.posts.count_documents({
            "user_id": user["user_id"], "kind": "essay", "status": "scheduled",
        })
        short_posts_30d = await db.posts.count_documents({
            "user_id": user["user_id"], "kind": "post",
            "release_at": {"$gte": thirty, "$lte": now_iso},
            "status": {"$nin": ["declined", "hidden"]},
        })
        follower_count = await db.follows.count_documents({"followed_id": user["user_id"]})
        dispatches_30d = await db.essay_dispatches.count_documents({
            "writer_id": user["user_id"],
            "created_at": {"$gte": thirty},
        })
        has_draft = await db.drafts.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 1})

        return {
            "published_essays": published_essays,
            "scheduled_essays": scheduled_essays,
            "short_posts_30d": short_posts_30d,
            "follower_count": follower_count,
            "essay_emails_sent_30d": dispatches_30d,
            "has_draft": bool(has_draft),
        }

    @router.get("/published")
    async def published_list(user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        now_iso = _now_iso()
        cur = db.posts.find(
            {"user_id": user["user_id"], "kind": "essay",
             "release_at": {"$lte": now_iso},
             "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0, "text": 0},
        ).sort("release_at", -1).limit(100)
        items = await cur.to_list(100)

        # Reads count per essay (how many followers got the email)
        post_ids = [p["post_id"] for p in items]
        if post_ids:
            pipeline = [
                {"$match": {"post_id": {"$in": post_ids}, "writer_id": user["user_id"]}},
                {"$group": {"_id": "$post_id", "count": {"$sum": 1}}},
            ]
            agg = await db.essay_dispatches.aggregate(pipeline).to_list(500)
            dispatch_map = {a["_id"]: a["count"] for a in agg}
            for p in items:
                p["emails_sent"] = dispatch_map.get(p["post_id"], 0)
        return {"items": items}

    @router.get("/scheduled")
    async def scheduled_list(user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        cur = db.posts.find(
            {"user_id": user["user_id"], "kind": "essay", "status": "scheduled"},
            {"_id": 0, "text": 0},
        ).sort("release_at", 1).limit(100)
        items = await cur.to_list(100)
        return {"items": items}

    return router
