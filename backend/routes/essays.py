"""Essay-specific routes: single essay reader with paywall for non-members."""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/essays", tags=["essays"])

PREVIEW_CHARS = 320


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def setup(db):
    @router.get("")
    async def list_essays(
        q: Optional[str] = None,
        market: Optional[str] = None,
        writer_id: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 30,
    ):
        """Browse essays. Public. Returns title/subtitle/preview/author for each."""
        limit = min(max(1, limit), 60)
        now_iso = _now_iso()
        query = {
            "kind": "essay",
            "status": {"$nin": ["declined", "hidden"]},
            "release_at": {"$lte": before or now_iso},
        }
        # Exclude suspended authors
        sus_rows = await db.users.find({"suspended": True}, {"_id": 0, "user_id": 1}).to_list(2000)
        sus = [s["user_id"] for s in sus_rows]
        if writer_id:
            if writer_id in sus:
                return {"items": [], "next_before": None}
            query["user_id"] = writer_id
        else:
            if sus:
                query["user_id"] = {"$nin": sus}

        if q:
            ql = q.strip()
            query["$or"] = [
                {"title": {"$regex": ql, "$options": "i"}},
                {"subtitle": {"$regex": ql, "$options": "i"}},
                {"text": {"$regex": ql, "$options": "i"}},
            ]

        # Pull a bit more than needed so we can filter by market in-memory
        raw_limit = limit * 3 if market else limit
        cur = db.posts.find(query, {"_id": 0}).sort("release_at", -1).limit(raw_limit)
        items = await cur.to_list(raw_limit)
        if not items:
            return {"items": [], "next_before": None}

        # Hydrate authors
        user_ids = list({p["user_id"] for p in items})
        profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
        pmap = {p["user_id"]: p for p in profiles}
        umap = {u["user_id"]: u for u in users}

        out = []
        for p in items:
            prof = pmap.get(p["user_id"]) or {}
            usr = umap.get(p["user_id"]) or {}
            author_market = prof.get("market") or ""
            if market and market.strip().lower() not in author_market.lower():
                continue
            text = p.get("text") or ""
            out.append({
                "post_id": p["post_id"],
                "kind": "essay",
                "title": p.get("title"),
                "subtitle": p.get("subtitle"),
                "preview": _preview(text),
                "word_count": len(text.split()),
                "image_path": p.get("image_path"),
                "media": p.get("media") or ([{"kind": "image", "path": p["image_path"]}] if p.get("image_path") else []),
                "created_at": p.get("created_at"),
                "release_at": p.get("release_at"),
                "is_pete_pick": bool(p.get("is_pete_pick")),
                "author": {
                    "user_id": p["user_id"],
                    "name": prof.get("name") or usr.get("name") or "Member",
                    "market": author_market,
                    "avatar_path": prof.get("avatar_path"),
                    "is_supporter": (usr.get("supporter_until") or "") > _now_iso(),
                },
            })
            if len(out) >= limit:
                break

        next_before = out[-1]["release_at"] if len(out) == limit else None
        return {"items": out, "next_before": next_before}

    @router.get("/{post_id}")
    async def get_essay(
        post_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        post = await db.posts.find_one(
            {"post_id": post_id, "kind": "essay", "status": {"$nin": ["declined", "hidden"]}},
            {"_id": 0},
        )
        if not post:
            raise HTTPException(status_code=404, detail="Essay not found")

        owner = await db.users.find_one({"user_id": post["user_id"]}, {"_id": 0})
        if owner and owner.get("suspended"):
            raise HTTPException(status_code=404, detail="Essay not found")

        # Author
        profile = await db.profiles.find_one({"user_id": post["user_id"]}, {"_id": 0})
        now_iso = _now_iso()
        author = {
            "user_id": post["user_id"],
            "name": (profile or {}).get("name") or (owner or {}).get("name") or "Member",
            "market": (profile or {}).get("market"),
            "avatar_path": (profile or {}).get("avatar_path"),
            "bio": (profile or {}).get("bio"),
            "is_supporter": ((owner or {}).get("supporter_until") or "") > now_iso,
        }

        # Reply count (released only)
        reply_count = await db.replies.count_documents({
            "post_id": post_id,
            "release_at": {"$lte": now_iso},
            "status": {"$ne": "hidden"},
        })

        # Determine viewer
        viewer = None
        try:
            viewer = await get_current_user(db, session_token, authorization)
        except Exception:
            viewer = None

        is_member = viewer is not None and viewer.get("status") == "approved"

        body = {
            "post_id": post["post_id"],
            "kind": "essay",
            "title": post.get("title"),
            "subtitle": post.get("subtitle"),
            "image_path": post.get("image_path"),
            "media": post.get("media") or ([{"kind": "image", "path": post["image_path"]}] if post.get("image_path") else []),
            "created_at": post.get("created_at"),
            "release_at": post.get("release_at"),
            "is_pete_pick": bool(post.get("is_pete_pick")),
            "is_released": True,
            "author": author,
            "reply_count": reply_count,
            "is_member_only": True,
        }

        if is_member:
            from services.markdown_render import render as md_render
            body["text"] = post.get("text") or ""
            body["html"] = md_render(post.get("text") or "")
            body["paywall"] = False
        else:
            body["preview"] = _preview(post.get("text") or "")
            body["paywall"] = True

        return body

    return router
