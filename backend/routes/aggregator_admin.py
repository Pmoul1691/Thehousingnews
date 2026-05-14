"""Admin endpoints for the public aggregator. Restricted to admin emails via
the existing Emergent Google Auth (allowlist in services.auth_helpers).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email
from services.rss_ingest import ingest_publisher, test_feed, _now_iso

logger = logging.getLogger(__name__)


class PublisherCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    category: str = Field(min_length=1, max_length=40)
    feed_url: str = Field(min_length=8, max_length=600)
    homepage_url: Optional[str] = Field(default=None, max_length=600)
    logo_url: Optional[str] = Field(default=None, max_length=600)
    display_mode: str = Field(default="headline_and_snippet")
    permission_status: str = Field(default="pending")
    refresh_minutes: int = Field(default=30, ge=5, le=720)


class PublisherUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    feed_url: Optional[str] = None
    homepage_url: Optional[str] = None
    logo_url: Optional[str] = None
    display_mode: Optional[str] = None
    permission_status: Optional[str] = None
    refresh_minutes: Optional[int] = Field(default=None, ge=5, le=720)
    active: Optional[bool] = None


class TestFeedPayload(BaseModel):
    feed_url: str = Field(min_length=8, max_length=600)
    display_mode: Optional[str] = "headline_and_snippet"


def setup(db):
    router = APIRouter(prefix="/api/agg/admin", tags=["aggregator-admin"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/publishers")
    async def list_publishers(_admin=Depends(_admin)):
        """List all publishers with 7-day article counts attached."""
        pubs = await db.agg_publishers.find({}, {"_id": 0}).sort("name", 1).to_list(500)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        agg = await db.agg_articles.aggregate([
            {"$match": {"published_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$publisher_id", "n": {"$sum": 1}}},
        ]).to_list(500)
        counts = {r["_id"]: r["n"] for r in agg}
        for p in pubs:
            p["items_last_7d"] = counts.get(p["id"], 0)
        return {"items": pubs}

    @router.post("/publishers")
    async def create_publisher(payload: PublisherCreate, _admin=Depends(_admin)):
        existing = await db.agg_publishers.find_one({"slug": payload.slug})
        if existing:
            raise HTTPException(status_code=400, detail="Slug already in use")
        doc = {
            "id": str(uuid.uuid4()),
            **payload.dict(),
            "active": False,  # require explicit activation after test
            "last_fetched_at": None,
            "last_fetch_status": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.agg_publishers.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.patch("/publishers/{pub_id}")
    async def update_publisher(pub_id: str, payload: PublisherUpdate, _admin=Depends(_admin)):
        updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="Nothing to update")
        updates["updated_at"] = _now_iso()
        res = await db.agg_publishers.update_one({"id": pub_id}, {"$set": updates})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Publisher not found")
        pub = await db.agg_publishers.find_one({"id": pub_id}, {"_id": 0})
        return pub

    @router.delete("/publishers/{pub_id}")
    async def delete_publisher(pub_id: str, _admin=Depends(_admin)):
        # Soft: deactivate. Hard delete also wipes articles.
        await db.agg_publishers.update_one({"id": pub_id}, {"$set": {"active": False, "updated_at": _now_iso()}})
        return {"deactivated": True}

    @router.post("/publishers/{pub_id}/refresh")
    async def refresh_publisher(pub_id: str, _admin=Depends(_admin)):
        pub = await db.agg_publishers.find_one({"id": pub_id}, {"_id": 0})
        if not pub:
            raise HTTPException(status_code=404, detail="Publisher not found")
        stats = await ingest_publisher(db, pub)
        return stats

    @router.post("/test-feed")
    async def test_feed_endpoint(payload: TestFeedPayload, _admin=Depends(_admin)):
        """Used by the Add/Edit publisher form to validate a feed before activation."""
        return await test_feed(payload.feed_url, display_mode=payload.display_mode or "headline_and_snippet")

    @router.get("/articles")
    async def list_articles(
        q: Optional[str] = Query(default=None, max_length=200),
        publisher_id: Optional[str] = None,
        hidden: Optional[bool] = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
        _admin=Depends(_admin),
    ):
        query: dict = {}
        if publisher_id:
            query["publisher_id"] = publisher_id
        if hidden is not None:
            query["hidden"] = hidden
        if q:
            query["title"] = {"$regex": q.strip(), "$options": "i"}
        cur = db.agg_articles.find(query, {"_id": 0}).sort("published_at", -1).skip(offset).limit(limit)
        items = await cur.to_list(limit)
        total = await db.agg_articles.count_documents(query)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    @router.post("/articles/{art_id}/hide")
    async def hide_article(art_id: str, _admin=Depends(_admin)):
        res = await db.agg_articles.update_one({"id": art_id}, {"$set": {"hidden": True}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Article not found")
        return {"hidden": True}

    @router.delete("/articles/{art_id}")
    async def delete_article(art_id: str, _admin=Depends(_admin)):
        res = await db.agg_articles.delete_one({"id": art_id})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Article not found")
        return {"deleted": True}

    return router
