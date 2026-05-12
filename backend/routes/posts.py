"""Post composer and feeds with batched release."""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user
from services.release_window import next_window, CHICAGO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])


class PostCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    image_path: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(db):
    async def _user(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        return await get_current_user(db, session_token, authorization)

    async def _suspended_user_ids() -> set:
        rows = await db.users.find({"suspended": True}, {"_id": 0, "user_id": 1}).to_list(2000)
        return {r["user_id"] for r in rows}

    async def _attach_meta(items: List[dict], viewer_id: Optional[str] = None) -> List[dict]:
        if not items:
            return items
        user_ids = list({p["user_id"] for p in items})
        profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        profile_map = {p["user_id"]: p for p in profiles}
        user_map = {u["user_id"]: u for u in users}
        post_ids = [p["post_id"] for p in items]
        now_iso = _now_iso()
        pipeline = [
            {"$match": {"post_id": {"$in": post_ids}, "release_at": {"$lte": now_iso}, "status": {"$ne": "hidden"}}},
            {"$group": {"_id": "$post_id", "count": {"$sum": 1}}},
        ]
        agg = await db.replies.aggregate(pipeline).to_list(1000)
        reply_map = {a["_id"]: a["count"] for a in agg}

        # Viewer's flag set
        flagged_ids = set()
        if viewer_id:
            f = await db.flags.find(
                {"flagger_id": viewer_id, "target_kind": "post", "target_id": {"$in": post_ids}, "resolved": False},
                {"_id": 0, "target_id": 1},
            ).to_list(500)
            flagged_ids = {x["target_id"] for x in f}

        for p in items:
            prof = profile_map.get(p["user_id"])
            usr = user_map.get(p["user_id"], {})
            p["author"] = {
                "user_id": p["user_id"],
                "name": (prof or {}).get("name") or usr.get("name") or "Member",
                "market": (prof or {}).get("market"),
                "avatar_path": (prof or {}).get("avatar_path"),
            }
            p["reply_count"] = reply_map.get(p["post_id"], 0)
            p["is_released"] = p.get("release_at", "") <= now_iso
            p["viewer_flagged"] = p["post_id"] in flagged_ids
        return items

    @router.post("")
    async def create_post(payload: PostCreate, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        if user.get("suspended"):
            raise HTTPException(status_code=403, detail="Account suspended")
        post_id = f"post_{uuid.uuid4().hex[:12]}"
        now_iso = _now_iso()
        release_at = next_window(datetime.now(CHICAGO)).astimezone(timezone.utc).isoformat()
        doc = {
            "post_id": post_id,
            "user_id": user["user_id"],
            "text": payload.text.strip(),
            "image_path": payload.image_path,
            "status": "pending_release",
            "created_at": now_iso,
            "release_at": release_at,
        }
        await db.posts.insert_one(doc)
        return {"post_id": post_id, "created_at": now_iso, "release_at": release_at, "status": "pending_release"}

    @router.get("/public")
    async def public_feed(limit: int = Query(50, le=100)):
        now_iso = _now_iso()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        suspended = await _suspended_user_ids()
        cur = db.posts.find(
            {
                "release_at": {"$lte": now_iso, "$gte": cutoff},
                "status": {"$nin": ["declined", "hidden"]},
                "user_id": {"$nin": list(suspended)},
            },
            {"_id": 0},
        ).sort("release_at", -1).limit(limit)
        items = await cur.to_list(limit)
        items = await _attach_meta(items)
        return {"items": items}

    @router.get("/feed")
    async def home_feed(
        limit: int = Query(50, le=100),
        scope: str = Query("everyone"),
        user=Depends(_user),
    ):
        if user.get("status") != "approved":
            return {"items": []}
        now_iso = _now_iso()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        suspended = await _suspended_user_ids()

        query = {
            "release_at": {"$lte": now_iso, "$gte": cutoff},
            "status": {"$nin": ["declined", "hidden"]},
            "user_id": {"$nin": list(suspended)},
        }

        if scope == "following":
            follows = await db.follows.find({"follower_id": user["user_id"]}, {"_id": 0}).to_list(2000)
            followed_ids = [f["followed_id"] for f in follows]
            # Include self in following feed (so you see your own released posts there too)
            followed_ids.append(user["user_id"])
            query["user_id"] = {"$in": followed_ids, "$nin": list(suspended)}

        cur = db.posts.find(query, {"_id": 0}).sort("release_at", -1).limit(limit)
        items = await cur.to_list(limit)
        items = await _attach_meta(items, viewer_id=user["user_id"])
        return {"items": items, "scope": scope}

    @router.get("/mine")
    async def my_posts(user=Depends(_user)):
        if user.get("status") != "approved":
            return {"items": []}
        cur = db.posts.find(
            {"user_id": user["user_id"], "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0},
        ).sort("created_at", -1).limit(50)
        items = await cur.to_list(50)
        items = await _attach_meta(items, viewer_id=user["user_id"])
        return {"items": items}

    @router.get("/by-user/{user_id}")
    async def posts_by_user(user_id: str, user=Depends(_user)):
        # Hide all posts of suspended users from non-admin viewers
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not target:
            return {"items": []}
        if target.get("suspended") and not user.get("is_admin"):
            return {"items": []}
        now_iso = _now_iso()
        cur = db.posts.find(
            {"user_id": user_id, "release_at": {"$lte": now_iso}, "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0},
        ).sort("release_at", -1).limit(50)
        items = await cur.to_list(50)
        items = await _attach_meta(items, viewer_id=user["user_id"])
        return {"items": items}

    return router
