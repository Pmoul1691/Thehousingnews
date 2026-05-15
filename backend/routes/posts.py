"""Post composer and feeds with batched release. Supports short posts AND essays."""
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header, Query, BackgroundTasks
from pydantic import BaseModel, Field, model_validator

from services.auth_helpers import get_current_user
from services.release_window import next_window, CHICAGO
from services.essay_dispatch import dispatch_essay_to_followers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])

SHORT_POST_MAX = 500
ESSAY_MAX = 50000
ESSAY_PREVIEW_CHARS = 320
MAX_IMAGES_PER_POST = 4
MAX_TAGS_PER_POST = 10

# Hashtag pattern: # followed by 2-30 chars of letters/digits/underscores.
# Word-boundary leading so we don't match "#" inside URLs or code.
TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_]{2,30})\b", flags=re.UNICODE)


def extract_tags(*texts) -> list[str]:
    """Pull hashtags from one or more text fragments. Returns a lowercased,
    deduplicated, length-capped list."""
    seen: set[str] = set()
    out: list[str] = []
    for t in texts:
        if not t:
            continue
        for m in TAG_RE.findall(t):
            tag = m.lower()
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
            if len(out) >= MAX_TAGS_PER_POST:
                return out
    return out


class MediaItem(BaseModel):
    kind: Literal["image", "video", "audio", "embed"]
    path: Optional[str] = None  # storage path for uploaded media
    mime: Optional[str] = None
    thumbnail_path: Optional[str] = None
    duration_s: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    hls_path: Optional[str] = None  # HLS .m3u8 storage path for transcoded long videos
    # For embeds
    provider: Optional[Literal["youtube", "vimeo"]] = None
    video_id: Optional[str] = None
    embed_url: Optional[str] = None
    thumbnail_url: Optional[str] = None  # external thumbnail url for embeds

    @model_validator(mode="after")
    def _validate(self):
        if self.kind == "embed":
            if not self.embed_url or not self.provider:
                raise ValueError("Embed media requires provider and embed_url")
        else:
            if not (self.path or self.hls_path):
                raise ValueError(f"{self.kind} media requires a storage path")
        return self


class PostCreate(BaseModel):
    kind: Literal["post", "essay"] = "post"
    text: str = Field(min_length=1, max_length=ESSAY_MAX)
    title: Optional[str] = Field(default=None, max_length=160)
    subtitle: Optional[str] = Field(default=None, max_length=240)
    image_path: Optional[str] = None  # legacy single-image (still respected)
    media: List[MediaItem] = Field(default_factory=list)
    scheduled_at: Optional[str] = None  # ISO UTC, only valid for essays
    prompt_id: Optional[str] = Field(default=None, max_length=40)  # Subject of the Week link

    @model_validator(mode="after")
    def _validate_kind(self):
        # Limit media composition
        images = [m for m in self.media if m.kind == "image"]
        videos = [m for m in self.media if m.kind == "video"]
        audios = [m for m in self.media if m.kind == "audio"]
        embeds = [m for m in self.media if m.kind == "embed"]
        if len(images) > MAX_IMAGES_PER_POST:
            raise ValueError(f"At most {MAX_IMAGES_PER_POST} images per post")
        if len(videos) > 1:
            raise ValueError("Only one video per post")
        if len(audios) > 1:
            raise ValueError("Only one audio per post")
        if len(embeds) > 1:
            raise ValueError("Only one embed per post")
        if videos and embeds:
            raise ValueError("Choose either an uploaded video or a URL embed, not both")

        if self.kind == "post":
            if len(self.text) > SHORT_POST_MAX:
                raise ValueError(f"Short posts must be {SHORT_POST_MAX} characters or fewer")
            if self.title or self.subtitle:
                self.title = None
                self.subtitle = None
            self.scheduled_at = None
        else:  # essay
            if not (self.title and self.title.strip()):
                raise ValueError("Essays require a title")
            if len(self.text.strip()) < 100:
                raise ValueError("Essays must be at least 100 characters")
            if self.scheduled_at:
                try:
                    sched = datetime.fromisoformat(self.scheduled_at.replace("Z", "+00:00"))
                    if sched.tzinfo is None:
                        sched = sched.replace(tzinfo=timezone.utc)
                    if sched <= datetime.now(timezone.utc):
                        raise ValueError("scheduled_at must be in the future")
                    self.scheduled_at = sched.astimezone(timezone.utc).isoformat()
                except ValueError as e:
                    raise ValueError(f"Invalid scheduled_at: {e}")
        return self


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview_text(body: str, limit: int = ESSAY_PREVIEW_CHARS) -> str:
    body = (body or "").strip()
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut + "..."


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
        prompt_ids = list({p["prompt_id"] for p in items if p.get("prompt_id")})
        prompt_map = {}
        if prompt_ids:
            prows = await db.prompts.find({"prompt_id": {"$in": prompt_ids}}, {"_id": 0, "prompt_id": 1, "title": 1}).to_list(100)
            prompt_map = {x["prompt_id"]: x for x in prows}
        now_iso = _now_iso()
        pipeline = [
            {"$match": {"post_id": {"$in": post_ids}, "release_at": {"$lte": now_iso}, "status": {"$ne": "hidden"}}},
            {"$group": {"_id": "$post_id", "count": {"$sum": 1}}},
        ]
        agg = await db.replies.aggregate(pipeline).to_list(1000)
        reply_map = {a["_id"]: a["count"] for a in agg}

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
                "is_supporter": (usr.get("supporter_until") or "") > now_iso,
            }
            p["reply_count"] = reply_map.get(p["post_id"], 0)
            p["is_released"] = p.get("release_at", "") <= now_iso
            p["viewer_flagged"] = p["post_id"] in flagged_ids
            p["is_pete_pick"] = bool(p.get("is_pete_pick"))
            p["kind"] = p.get("kind") or "post"
            if p.get("prompt_id") and p["prompt_id"] in prompt_map:
                p["prompt"] = prompt_map[p["prompt_id"]]
            # Back-compat: synthesize media list from legacy image_path if missing
            if not p.get("media"):
                if p.get("image_path"):
                    p["media"] = [{"kind": "image", "path": p["image_path"]}]
                else:
                    p["media"] = []
            if p["kind"] == "essay":
                # In feeds, only return the preview to keep payload small
                p["preview"] = _preview_text(p.get("text") or "")
                # Don't ship the full essay body in lists
                p.pop("text", None)
        return items

    @router.post("")
    async def create_post(payload: PostCreate, background_tasks: BackgroundTasks, user=Depends(_user)):
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        if user.get("suspended"):
            raise HTTPException(status_code=403, detail="Account suspended")
        post_id = f"post_{uuid.uuid4().hex[:12]}"
        now_iso = _now_iso()

        if payload.kind == "essay":
            if payload.scheduled_at:
                release_at = payload.scheduled_at
                status = "scheduled"
            else:
                release_at = now_iso
                status = "approved"
        else:
            release_at = next_window(datetime.now(CHICAGO)).astimezone(timezone.utc).isoformat()
            status = "pending_release"

        # Normalize media: if legacy image_path provided and no media, treat as a single image
        media_payload = [m.model_dump(exclude_none=True) for m in payload.media]
        if payload.image_path and not any(m.get("kind") == "image" for m in media_payload):
            media_payload.insert(0, {"kind": "image", "path": payload.image_path})

        # Validate prompt_id (Subject of the Week) if provided
        prompt_snapshot = None
        if payload.prompt_id:
            prompt_row = await db.prompts.find_one({"prompt_id": payload.prompt_id}, {"_id": 0})
            if not prompt_row:
                raise HTTPException(status_code=400, detail="Subject not found")
            prompt_snapshot = {
                "prompt_id": prompt_row["prompt_id"],
                "title": prompt_row["title"],
            }

        doc = {
            "post_id": post_id,
            "user_id": user["user_id"],
            "kind": payload.kind,
            "title": payload.title,
            "subtitle": payload.subtitle,
            "text": payload.text.strip(),
            "tags": extract_tags(payload.text, payload.title, payload.subtitle),
            "image_path": payload.image_path or (media_payload[0]["path"] if media_payload and media_payload[0]["kind"] == "image" else None),
            "media": media_payload,
            "status": status,
            "created_at": now_iso,
            "release_at": release_at,
            "prompt_id": payload.prompt_id if prompt_snapshot else None,
        }
        await db.posts.insert_one(doc)

        if payload.kind == "essay" and status == "approved":
            # Dispatch follower email in background only for instant essays.
            # Scheduled essays will be dispatched by the per-minute scheduler job.
            background_tasks.add_task(dispatch_essay_to_followers, db, post_id)

        # Clear the user's draft on successful publish/schedule
        try:
            await db.drafts.delete_one({"user_id": user["user_id"]})
        except Exception:
            pass

        return {
            "post_id": post_id,
            "created_at": now_iso,
            "release_at": release_at,
            "status": status,
            "kind": payload.kind,
        }

    @router.get("/search")
    async def search_posts(
        q: str = Query(..., min_length=2, max_length=120),
        kind: Optional[Literal["post", "essay"]] = None,
        market: Optional[str] = Query(default=None, max_length=80),
        limit: int = Query(30, le=50),
        user=Depends(_user),
    ):
        """Members-only full-text search across released posts.
        Uses the Mongo text index on (text, title, subtitle). Returns the same
        shape as the feed (with author + reply_count attached)."""
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        now_iso = _now_iso()
        suspended = await _suspended_user_ids()
        query: dict = {
            "$text": {"$search": q.strip()},
            "release_at": {"$lte": now_iso},
            "status": {"$nin": ["declined", "hidden"]},
            "user_id": {"$nin": list(suspended)},
        }
        if kind:
            query["kind"] = kind
        if market:
            prof_rows = await db.profiles.find(
                {"market": {"$regex": market.strip(), "$options": "i"}},
                {"_id": 0, "user_id": 1},
            ).to_list(2000)
            allowed_ids = [p["user_id"] for p in prof_rows]
            if not allowed_ids:
                return {"items": [], "q": q}
            query["user_id"] = {"$in": allowed_ids, "$nin": list(suspended)}
        cur = (
            db.posts.find(query, {"_id": 0, "score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"}), ("release_at", -1)])
            .limit(limit)
        )
        items = await cur.to_list(limit)
        for it in items:
            it.pop("score", None)
        items = await _attach_meta(items, viewer_id=user["user_id"])
        return {"items": items, "q": q}

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

    @router.get("/by-tag/{tag}")
    async def by_tag(
        tag: str,
        limit: int = Query(30, le=50),
        offset: int = Query(0, ge=0),
        user=Depends(_user),
    ):
        """Members-only: posts tagged with #tag (case-insensitive). Same shape
        as the public feed (author + reply_count attached)."""
        if user.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Membership not approved")
        tag_norm = tag.lower().lstrip("#").strip()
        if not re.match(r"^[a-z0-9_]{2,30}$", tag_norm):
            raise HTTPException(status_code=400, detail="Invalid tag")
        now_iso = _now_iso()
        suspended = await _suspended_user_ids()
        q = {
            "tags": tag_norm,
            "release_at": {"$lte": now_iso},
            "status": {"$nin": ["declined", "hidden"]},
            "user_id": {"$nin": list(suspended)},
        }
        cur = (
            db.posts.find(q, {"_id": 0})
            .sort("release_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cur.to_list(limit)
        items = await _attach_meta(items, viewer_id=user["user_id"])
        total = await db.posts.count_documents(q)
        return {"items": items, "tag": tag_norm, "total": total, "offset": offset, "limit": limit}

    @router.get("/tags/popular")
    async def popular_tags(days: int = Query(30, ge=1, le=180), limit: int = Query(20, le=50), user=Depends(_user)):
        """Top tags by frequency across recently-released posts."""
        if user.get("status") != "approved":
            return {"items": []}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        pipeline = [
            {"$match": {
                "release_at": {"$lte": _now_iso(), "$gte": cutoff},
                "status": {"$nin": ["declined", "hidden"]},
                "tags": {"$exists": True, "$ne": []},
            }},
            {"$unwind": "$tags"},
            {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": limit},
        ]
        rows = await db.posts.aggregate(pipeline).to_list(limit)
        return {"items": [{"tag": r["_id"], "count": r["count"]} for r in rows]}

    return router
