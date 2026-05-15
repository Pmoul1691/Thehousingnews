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
        return {"items": items, "total": total, "hours": hours, "offset": offset, "limit": limit}

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
        with `article: null` so the grid stays uniform."""
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
        # Publishers with articles first (sorted by recency), then those without.
        items.sort(
            key=lambda r: (r["article"] is None, -(0 if r["article"] is None else 1), (r["article"] or {}).get("published_at", "")),
            reverse=False,
        )
        # Stable: with-article rows by published_at desc, no-article rows alpha.
        with_articles = [it for it in items if it["article"]]
        with_articles.sort(key=lambda r: r["article"]["published_at"], reverse=True)
        without = [it for it in items if not it["article"]]
        without.sort(key=lambda r: r["publisher"]["name"].lower())
        return {"items": with_articles + without, "hours": hours, "total": len(items)}

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

    return router
