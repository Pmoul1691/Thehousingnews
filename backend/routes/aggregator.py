"""Public aggregator API. Read-only. No auth.

Routes:
- GET /api/agg/articles                         river of items (paginated)
- GET /api/agg/publishers                        list active publishers (name, slug, category)
- GET /api/agg/publishers/{slug}                 publisher detail + recent items
- GET /api/agg/categories                        category counts
- POST /api/agg/newsletter/signup                capture email locally + push to provider
"""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.agg_seed import CATEGORIES
from services.brevo import add_to_list as brevo_add_to_list
from services.trending import compute_trending

NEWSLETTER_LIST_NAME = os.environ.get("AGG_NEWSLETTER_LIST_NAME", "The Housing News Daily")

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

# In-process cache for /publishers-latest. Key: f"pl:{hours}" -> (result, expires_ts).
# 5-minute TTL — RSS ingest cron runs every 15 min so freshness is fine.
_PL_CACHE: dict = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignupPayload(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    source_page: Optional[str] = Field(default=None, max_length=200)


def setup(db):
    router = APIRouter(prefix="/api/agg", tags=["aggregator-public"])

    @router.get("/articles")
    async def list_articles(
        category: Optional[str] = Query(default=None),
        publisher_slug: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, min_length=2, max_length=120),
        hours: int = Query(default=48, ge=1, le=336),  # max 14d window
        offset: int = Query(default=0, ge=0, le=5000),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ):
        """River of items, newest first, attributed to publisher. No internal article view."""
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pub_q: dict = {"active": True}
        if category and category in CATEGORIES:
            pub_q["category"] = category
        if publisher_slug:
            pub_q["slug"] = publisher_slug
        publishers = await db.agg_publishers.find(
            pub_q,
            {"_id": 0, "id": 1, "slug": 1, "name": 1, "category": 1, "logo_url": 1, "homepage_url": 1},
        ).to_list(200)
        pub_index = {p["id"]: p for p in publishers}
        if not pub_index:
            return {"items": [], "total": 0, "hours": hours}

        art_q = {
            "publisher_id": {"$in": list(pub_index.keys())},
            "published_at": {"$gte": cutoff_iso},
            "hidden": {"$ne": True},
        }
        if search:
            # Case-insensitive substring across title + snippet. Escape regex
            # metacharacters so e.g. "rates+yields" doesn't crash.
            safe = re.escape(search.strip())
            art_q["$or"] = [
                {"title": {"$regex": safe, "$options": "i"}},
                {"snippet": {"$regex": safe, "$options": "i"}},
            ]
        cur = (
            db.agg_articles.find(art_q, {"_id": 0})
            .sort("published_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cur.to_list(limit)
        # Attach publisher attribution to each item (denormalized into response only)
        for it in items:
            p = pub_index.get(it["publisher_id"])
            it["publisher"] = {
                "slug": p["slug"], "name": p["name"], "category": p["category"],
                "logo_url": p.get("logo_url"), "homepage_url": p.get("homepage_url"),
            } if p else None
        total = await db.agg_articles.count_documents(art_q)
        return {"items": items, "total": total, "hours": hours, "offset": offset, "limit": limit, "search": search}

    @router.get("/publishers")
    async def list_publishers():
        cur = db.agg_publishers.find(
            {"active": True},
            {"_id": 0, "id": 1, "slug": 1, "name": 1, "category": 1, "logo_url": 1, "homepage_url": 1, "permission_status": 1},
        ).sort("name", 1)
        items = await cur.to_list(500)
        return {"items": items}

    @router.get("/publishers-latest")
    async def publishers_latest(hours: int = Query(default=168, ge=1, le=720)):
        """Every active publisher with its most recent (non-hidden) article in
        the last `hours` window. Used by the home page grid: one card per
        publisher featuring its latest headline + a link to the publisher
        archive. Publishers with no article in the window are still returned
        with `article: null` so the grid stays uniform.

        Results are cached in-process for 5 minutes; the RSS ingest cron runs
        every 15 minutes so 5 minutes is well inside the freshness budget.
        """
        import time as _time
        cache_key = f"pl:{hours}"
        cached = _PL_CACHE.get(cache_key)
        now_ts = _time.time()
        if cached and cached[1] > now_ts:
            return cached[0]

        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        publishers = await db.agg_publishers.find(
            {"active": True},
            {"_id": 0, "id": 1, "slug": 1, "name": 1, "category": 1, "logo_url": 1, "homepage_url": 1},
        ).sort("name", 1).to_list(500)
        if not publishers:
            return {"items": [], "hours": hours}

        pub_ids = [p["id"] for p in publishers]
        # One aggregation pass: most recent article per publisher_id.
        pipeline = [
            {"$match": {
                "publisher_id": {"$in": pub_ids},
                "published_at": {"$gte": cutoff_iso},
                "hidden": {"$ne": True},
            }},
            {"$sort": {"published_at": -1}},
            {"$group": {
                "_id": "$publisher_id",
                "article": {"$first": {
                    "id": "$id",
                    "title": "$title",
                    "snippet": "$snippet",
                    "original_url": "$original_url",
                    "published_at": "$published_at",
                    "thumbnail_url": "$thumbnail_url",
                }},
            }},
        ]
        rows = await db.agg_articles.aggregate(pipeline).to_list(500)
        latest_by_pub = {r["_id"]: r["article"] for r in rows}

        items = []
        for p in publishers:
            items.append({
                "publisher": p,
                "article": latest_by_pub.get(p["id"]),
            })
        # Stable: with-article rows by published_at desc, no-article rows alpha.
        with_articles = [it for it in items if it["article"]]
        with_articles.sort(key=lambda r: r["article"]["published_at"], reverse=True)
        without = [it for it in items if not it["article"]]
        without.sort(key=lambda r: r["publisher"]["name"].lower())
        result = {"items": with_articles + without, "hours": hours, "total": len(items)}
        _PL_CACHE[cache_key] = (result, now_ts + 300)  # 5 min
        return result

    @router.get("/publishers/{slug}")
    async def publisher_detail(slug: str, limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        pub = await db.agg_publishers.find_one({"slug": slug, "active": True}, {"_id": 0})
        if not pub:
            raise HTTPException(status_code=404, detail="Publisher not found")
        art_q = {"publisher_id": pub["id"], "hidden": {"$ne": True}}
        cur = (
            db.agg_articles.find(art_q, {"_id": 0})
            .sort("published_at", -1)
            .skip(offset).limit(limit)
        )
        items = await cur.to_list(limit)
        total = await db.agg_articles.count_documents(art_q)
        return {"publisher": pub, "items": items, "total": total, "offset": offset, "limit": limit}

    @router.get("/categories")
    async def categories():
        # Count active publishers per category
        pipeline = [
            {"$match": {"active": True}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        ]
        rows = await db.agg_publishers.aggregate(pipeline).to_list(20)
        counts = {r["_id"]: r["count"] for r in rows}
        return {
            "categories": [
                {"key": c, "count": counts.get(c, 0)} for c in CATEGORIES
            ]
        }

    @router.get("/network-stats")
    async def network_stats():
        """Live source-count + most-recently-added publishers for the /news
        hero subtext. The frontend renders something like
        "Recently added: r/RealEstate · Inman · WSJ Real Estate" under the
        stat block — concrete social proof that the network keeps growing.
        """
        pub_total = await db.agg_publishers.count_documents({"active": True})
        pod_total = await db.agg_podcasts.count_documents({"active": True})
        recent = await db.agg_publishers.find(
            {"active": True, "created_at": {"$exists": True}},
            {"_id": 0, "name": 1, "slug": 1, "created_at": 1},
        ).sort("created_at", -1).limit(3).to_list(3)
        return {
            "publishers": pub_total,
            "podcasts": pod_total,
            "recently_added": [
                {"name": r.get("name"), "slug": r.get("slug")} for r in recent
            ],
        }

    @router.get("/trending")
    async def trending(
        hours: int = Query(default=24, ge=1, le=168),
        limit: int = Query(default=8, ge=1, le=20),
    ):
        """Trending topics today: top bigrams / trigrams across article titles
        from the last `hours` window. No auth, fully public."""
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pub_ids = [
            p["id"]
            async for p in db.agg_publishers.find({"active": True}, {"_id": 0, "id": 1})
        ]
        if not pub_ids:
            return {"items": [], "hours": hours}
        cur = db.agg_articles.find(
            {
                "publisher_id": {"$in": pub_ids},
                "published_at": {"$gte": cutoff_iso},
                "hidden": {"$ne": True},
            },
            {"_id": 0, "title": 1},
        ).sort("published_at", -1).limit(2000)
        titles = [a.get("title") or "" async for a in cur]
        items = compute_trending(titles, limit=limit)
        return {"items": items, "hours": hours, "sample_size": len(titles)}

    @router.post("/newsletter/signup")
    async def newsletter_signup(payload: SignupPayload, request: Request):
        email = (payload.email or "").strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email.")
        # Idempotent upsert on email
        await db.agg_newsletter_signups.update_one(
            {"email": email},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "email": email,
                "source_page": (payload.source_page or "")[:200],
                "ip": request.client.host if request.client else None,
                "created_at": _now_iso(),
                "brevo_status": None,
            }},
            upsert=True,
        )
        # Push to Brevo. Failure to push does NOT fail the request — we always
        # have the email captured locally so we can re-sync later if needed.
        brevo_result = brevo_add_to_list(email, NEWSLETTER_LIST_NAME, attributes={"SOURCE": payload.source_page or "thehousingnews.com"})
        # Stamp result so admins can spot un-synced rows.
        await db.agg_newsletter_signups.update_one(
            {"email": email},
            {"$set": {"brevo_status": brevo_result, "brevo_synced_at": _now_iso()}},
        )
        return {"ok": True, "email": email}

    @router.get("/newsletter/signup")
    async def newsletter_signup_get():
        # Some browsers / link checkers do GET on this URL — return a soft no-op.
        return {"ok": True}

    @router.get("/trending-tags")
    async def trending_tags(
        days: int = Query(default=14, ge=1, le=90),
        limit: int = Query(default=8, ge=1, le=30),
    ):
        """Public-safe top N hashtags across approved member posts in the last
        `days`. No auth — used by the Landing page social-proof strip to show
        what real estate professionals on the platform are writing about.
        """
        from datetime import datetime as _dt
        cutoff = (_dt.now(timezone.utc) - timedelta(days=days)).isoformat()
        pipeline = [
            {"$match": {
                "status": "approved",
                "release_at": {"$gte": cutoff},
                "tags": {"$exists": True, "$ne": []},
            }},
            {"$unwind": "$tags"},
            {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": limit},
        ]
        rows = await db.posts.aggregate(pipeline).to_list(limit)
        return {"items": [{"tag": r["_id"], "count": r["count"]} for r in rows], "days": days}

    @router.get("/recent-members")
    async def recent_members(limit: int = Query(default=8, ge=1, le=30)):
        """Public-safe list of recently-active members for the Landing page.
        Returns only name, market, avatar_path, and a short snippet from the
        member's most recent approved post. No emails, no IDs that aren't
        already exposed via /profile/{user_id}.

        "Recently active" = has at least one approved post within the last 30
        days. Sorted by most-recent post timestamp, descending.
        """
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        # Pull recent approved posts, newest first; we'll group client-side by user_id.
        pipeline = [
            {"$match": {"status": "approved", "release_at": {"$gte": cutoff_iso}}},
            {"$sort": {"release_at": -1}},
            {"$group": {
                "_id": "$user_id",
                "last_post_at": {"$first": "$release_at"},
                "last_text": {"$first": "$text"},
                "last_title": {"$first": "$title"},
                "last_post_id": {"$first": "$post_id"},
                "last_kind": {"$first": "$kind"},
            }},
            {"$sort": {"last_post_at": -1}},
            {"$limit": limit * 3},  # over-fetch in case some profiles are missing
        ]
        rows = await db.posts.aggregate(pipeline).to_list(limit * 3)
        if not rows:
            return {"items": []}
        user_ids = [r["_id"] for r in rows]
        # Only show approved + non-suspended + non-stub members with a profile and an avatar.
        users = await db.users.find(
            {
                "user_id": {"$in": user_ids},
                "status": "approved",
                "suspended": {"$ne": True},
            },
            {"_id": 0, "user_id": 1},
        ).to_list(500)
        approved_ids = {u["user_id"] for u in users}
        profiles = await db.profiles.find(
            {"user_id": {"$in": list(approved_ids)}, "is_stub": {"$ne": True}},
            {"_id": 0, "user_id": 1, "name": 1, "market": 1, "avatar_path": 1},
        ).to_list(500)
        pmap = {p["user_id"]: p for p in profiles}

        items = []
        for r in rows:
            uid = r["_id"]
            if uid not in approved_ids:
                continue
            prof = pmap.get(uid)
            if not prof:
                continue
            snippet_src = (r.get("last_title") or r.get("last_text") or "").strip()
            snippet = snippet_src[:140].rstrip()
            if len(snippet_src) > 140:
                snippet = snippet.rstrip() + "…"
            items.append({
                "user_id": uid,
                "name": prof.get("name") or "",
                "market": prof.get("market") or "",
                "avatar_path": prof.get("avatar_path"),
                "last_post_at": r["last_post_at"],
                "last_kind": r.get("last_kind"),
                "last_post_id": r.get("last_post_id"),
                "snippet": snippet,
            })
            if len(items) >= limit:
                break
        return {"items": items}

    @router.get("/new-members")
    async def new_members(
        days: int = Query(default=14, ge=1, le=90),
        limit: int = Query(default=5, ge=1, le=20),
    ):
        """Public list of members who joined recently — for the Landing
        "Members joined this week" strip. Sorted by most-recent join
        timestamp. Only returns approved + non-suspended + non-stub
        members with a real profile. No emails, no IDs beyond what is
        already exposed via /profile/{user_id}.
        """
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        users = await db.users.find(
            {
                "status": "approved",
                "suspended": {"$ne": True},
                "created_at": {"$gte": cutoff_iso},
            },
            {"_id": 0, "user_id": 1, "created_at": 1},
        ).sort("created_at", -1).to_list(limit * 4)
        if not users:
            return {"items": [], "days": days}

        uids = [u["user_id"] for u in users]
        profiles = await db.profiles.find(
            {"user_id": {"$in": uids}, "is_stub": {"$ne": True}},
            {"_id": 0, "user_id": 1, "name": 1, "market": 1,
             "avatar_path": 1, "linkedin_data": 1},
        ).to_list(500)
        pmap = {p["user_id"]: p for p in profiles}

        items: list[dict] = []
        for u in users:
            uid = u["user_id"]
            prof = pmap.get(uid)
            if not prof:
                continue
            li = prof.get("linkedin_data") or {}
            items.append({
                "user_id": uid,
                "name": prof.get("name") or "",
                "market": prof.get("market") or "",
                "avatar_path": prof.get("avatar_path"),
                "headline": (li.get("headline") or "")[:140],
                "joined_at": u.get("created_at"),
            })
            if len(items) >= limit:
                break
        return {"items": items, "days": days}

    return router
