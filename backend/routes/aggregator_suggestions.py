"""Publisher suggestions — public submission form + admin review.

Visitors can recommend new RSS feeds via the form on /about. Suggestions are
captured into agg_publisher_suggestions and reviewed in /admin/aggregator.
Admins can convert a suggestion into an active publisher with one click.
"""
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
URL_RE = re.compile(r"^https?://", re.I)

# Rate limit: 5 suggestions / IP / hour. In-memory, single-pod.
_BUCKET: dict[str, deque] = defaultdict(deque)
_LIMIT, _WINDOW = 5, 3600.0


def _rate_ok(ip: str) -> bool:
    now = time.time()
    b = _BUCKET[ip]
    while b and now - b[0] > _WINDOW:
        b.popleft()
    if len(b) >= _LIMIT:
        return False
    b.append(now)
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SuggestionPayload(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    publication_name: str = Field(min_length=1, max_length=160)
    feed_url: str = Field(min_length=8, max_length=600)
    homepage_url: Optional[str] = Field(default=None, max_length=600)
    reason: Optional[str] = Field(default=None, max_length=1000)


class ConvertPayload(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    category: str = Field(min_length=1, max_length=40)
    display_mode: str = Field(default="headline_and_snippet")
    permission_status: str = Field(default="pending")


def setup(db):
    router = APIRouter(tags=["aggregator-suggestions"])

    @router.post("/api/agg/publisher-suggestions")
    async def submit(payload: SuggestionPayload, request: Request):
        ip = request.client.host if request.client else "unknown"
        if not _rate_ok(ip):
            raise HTTPException(status_code=429, detail="Too many suggestions. Try again in an hour.")
        email = payload.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email.")
        feed_url = payload.feed_url.strip()
        if not URL_RE.match(feed_url):
            raise HTTPException(status_code=400, detail="Feed URL must start with http:// or https://")
        # Idempotent: dedupe on (email, feed_url)
        doc = {
            "id": str(uuid.uuid4()),
            "email": email,
            "publication_name": payload.publication_name.strip()[:160],
            "feed_url": feed_url,
            "homepage_url": (payload.homepage_url or "").strip()[:600] or None,
            "reason": (payload.reason or "").strip()[:1000] or None,
            "status": "pending",  # pending | approved | declined
            "ip": ip,
            "created_at": _now_iso(),
        }
        res = await db.agg_publisher_suggestions.update_one(
            {"email": email, "feed_url": feed_url},
            {"$setOnInsert": doc},
            upsert=True,
        )
        return {"ok": True, "new": res.upserted_id is not None}

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/api/agg/admin/publisher-suggestions")
    async def list_suggestions(
        status: Optional[str] = Query(default="pending"),
        _admin=Depends(_admin),
    ):
        q = {"status": status} if status else {}
        cur = db.agg_publisher_suggestions.find(q, {"_id": 0}).sort("created_at", -1).limit(200)
        items = await cur.to_list(200)
        return {"items": items}

    @router.post("/api/agg/admin/publisher-suggestions/{sid}/approve")
    async def approve(sid: str, payload: ConvertPayload, _admin=Depends(_admin)):
        sug = await db.agg_publisher_suggestions.find_one({"id": sid}, {"_id": 0})
        if not sug:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        # Slug must be unique
        existing = await db.agg_publishers.find_one({"slug": payload.slug})
        if existing:
            raise HTTPException(status_code=400, detail="Slug already in use")
        pub_doc = {
            "id": str(uuid.uuid4()),
            "name": sug["publication_name"],
            "slug": payload.slug,
            "category": payload.category,
            "feed_url": sug["feed_url"],
            "homepage_url": sug.get("homepage_url"),
            "logo_url": None,
            "display_mode": payload.display_mode,
            "permission_status": payload.permission_status,
            "refresh_minutes": 30,
            "active": False,  # admin must Test then Activate from the table
            "last_fetched_at": None,
            "last_fetch_status": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.agg_publishers.insert_one(pub_doc)
        await db.agg_publisher_suggestions.update_one(
            {"id": sid},
            {"$set": {"status": "approved", "approved_publisher_slug": payload.slug, "approved_at": _now_iso()}},
        )
        pub_doc.pop("_id", None)
        return {"ok": True, "publisher": pub_doc}

    @router.post("/api/agg/admin/publisher-suggestions/{sid}/decline")
    async def decline(sid: str, _admin=Depends(_admin)):
        res = await db.agg_publisher_suggestions.update_one(
            {"id": sid},
            {"$set": {"status": "declined", "declined_at": _now_iso()}},
        )
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        return {"ok": True}

    return router
