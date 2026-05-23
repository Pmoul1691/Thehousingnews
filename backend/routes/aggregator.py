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

from fastapi import APIRouter, HTTPException, Query, Request, Response, Cookie, Header
from pydantic import BaseModel, Field

from services.agg_seed import CATEGORIES
from services.brevo import add_to_list as brevo_add_to_list
from services.trending import compute_trending

NEWSLETTER_LIST_NAME = os.environ.get("AGG_NEWSLETTER_LIST_NAME", "The Housing News Daily")

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def _set_public_cache(response: Response, max_age: int = 60) -> None:
    """Tell Cloudflare (and the browser) that this response can be served from
    edge cache for `max_age` seconds. We also opt into stale-while-revalidate
    so a stale value can be served instantly while the edge refreshes in the
    background — perceived latency stays at 0ms for the user."""
    response.headers["Cache-Control"] = (
        f"public, max-age={max_age}, s-maxage={max_age}, stale-while-revalidate=60"
    )

# In-process cache for /publishers-latest. Key: f"pl:{hours}" -> (result, expires_ts).
# 5-minute TTL — RSS ingest cron runs every 15 min so freshness is fine.
_PL_CACHE: dict = {}

# Cache for the slow public aggregations driving the landing page. Each entry
# is `key -> (result, expires_ts)`. Cleared on process restart. We don't need
# cross-process invalidation because the inputs (posts, members) change on
# human time-scales (minutes-to-hours) and a 60-90s staleness is invisible.
_PUBLIC_CACHE: dict = {}


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
    async def publishers_latest(response: Response, hours: int = Query(default=168, ge=1, le=720)):
        """Every active publisher with its most recent (non-hidden) article in
        the last `hours` window. Used by the home page grid: one card per
        publisher featuring its latest headline + a link to the publisher
        archive. Publishers with no article in the window are still returned
        with `article: null` so the grid stays uniform.

        Results are cached in-process for 5 minutes; the RSS ingest cron runs
        every 15 minutes so 5 minutes is well inside the freshness budget.
        """
        _set_public_cache(response, 60)
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

    # ─── Article engagement tracking ──────────────────────────────────────
    # Two cheap signals: clicks (strong intent) and impressions (volume). Used
    # for the public 🔥 badge on the most-clicked article in the last 24h and
    # for the admin "what's hot right now" overlay on /news.

    class ClickPayload(BaseModel):
        session_id: Optional[str] = Field(default=None, max_length=80)

    class ImpressionsPayload(BaseModel):
        article_ids: list[str] = Field(default_factory=list)
        session_id: Optional[str] = Field(default=None, max_length=80)

    @router.post("/articles/{article_id}/click")
    async def record_article_click(article_id: str, payload: ClickPayload, request: Request):
        """Record a click on an aggregator article. Dedup'd at one click per
        (session_id, article_id) per 5 minutes so reload abuse can't inflate
        the leaderboard. Fire-and-forget from the frontend — failures here
        must never block the user's navigation to the publisher's site."""
        # Validate the article exists (and isn't hidden) but only loosely;
        # we don't want to pay a round-trip on the hot path so we skip the
        # check and let the analytics endpoint filter on join.
        if not article_id or len(article_id) > 80:
            return {"ok": False}
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        session_id = (payload.session_id or "")[:80]
        # Dedupe key: identical clicks within 5 min are dropped at insert time.
        # We use a unique partial index — see server.py startup.
        bucket_5m = now.strftime("%Y%m%d%H") + str(now.minute // 5)
        doc = {
            "article_id": article_id,
            "session_id": session_id,
            "bucket_5m": bucket_5m,
            "clicked_at": now_iso,
        }
        try:
            await db.agg_article_clicks.insert_one(doc)
        except Exception:
            # Duplicate key from the unique index — exactly what we want.
            return {"ok": True, "deduped": True}
        return {"ok": True}

    @router.post("/articles/impressions")
    async def record_article_impressions(payload: ImpressionsPayload):
        """Batch-record impressions for the article cards that just rendered.
        Cheap volume signal — used in the admin overlay; not used for the
        public 🔥 badge so impression-spamming can't move that needle."""
        ids = [a for a in (payload.article_ids or []) if isinstance(a, str) and a and len(a) <= 80][:200]
        if not ids:
            return {"ok": True, "count": 0}
        now_iso = datetime.now(timezone.utc).isoformat()
        session_id = (payload.session_id or "")[:80]
        rows = [{"article_id": a, "session_id": session_id, "seen_at": now_iso} for a in ids]
        try:
            await db.agg_article_impressions.insert_many(rows, ordered=False)
        except Exception:
            logger.exception("impression batch insert failed")
        return {"ok": True, "count": len(rows)}

    @router.get("/articles/top-clicked")
    async def top_clicked_article(response: Response, hours: int = Query(default=24, ge=1, le=72)):
        """Single most-clicked article in the last `hours`. Powers the public
        🔥 badge on /news. Cached for 60s — the badge moves on human time
        scales, not per-request. Public, no auth."""
        _set_public_cache(response, 60)
        import time as _time
        cache_key = f"tc:{hours}"
        cached = _PUBLIC_CACHE.get(cache_key)
        now_ts = _time.time()
        if cached and cached[1] > now_ts:
            return cached[0]
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pipeline = [
            {"$match": {"clicked_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$article_id", "clicks": {"$sum": 1}}},
            {"$sort": {"clicks": -1}},
            {"$limit": 1},
        ]
        rows = await db.agg_article_clicks.aggregate(pipeline).to_list(1)
        result = {
            "article_id": rows[0]["_id"] if rows else None,
            "clicks": rows[0]["clicks"] if rows else 0,
            "hours": hours,
        }
        _PUBLIC_CACHE[cache_key] = (result, now_ts + 60)
        return result

    @router.get("/admin/news-pulse")
    async def admin_news_pulse(
        request: Request,
        hours: int = Query(default=24, ge=1, le=72),
        limit: int = Query(default=10, ge=1, le=50),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Admin-only overlay payload: top articles by clicks today,
        impressions, and a rough "currently viewing" count (distinct sessions
        with a pageview/impression in the last 60s).
        """
        from services.auth_helpers import get_current_user, is_user_admin
        try:
            user = await get_current_user(db, session_token, authorization)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Sign in required")
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        live_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()

        # Top articles by clicks in window
        click_pipeline = [
            {"$match": {"clicked_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$article_id", "clicks": {"$sum": 1}}},
            {"$sort": {"clicks": -1}},
            {"$limit": limit},
        ]
        click_rows = await db.agg_article_clicks.aggregate(click_pipeline).to_list(limit)
        top_ids = [r["_id"] for r in click_rows]

        # Impression counts for the same set
        impressions_by_id: dict = {}
        if top_ids:
            imp_rows = await db.agg_article_impressions.aggregate([
                {"$match": {"article_id": {"$in": top_ids}, "seen_at": {"$gte": cutoff}}},
                {"$group": {"_id": "$article_id", "impressions": {"$sum": 1}}},
            ]).to_list(len(top_ids))
            impressions_by_id = {r["_id"]: r["impressions"] for r in imp_rows}

        # Hydrate article + publisher info
        articles_by_id: dict = {}
        publishers_by_id: dict = {}
        if top_ids:
            arts = await db.agg_articles.find(
                {"id": {"$in": top_ids}},
                {"_id": 0, "id": 1, "title": 1, "publisher_id": 1, "original_url": 1, "published_at": 1},
            ).to_list(len(top_ids))
            articles_by_id = {a["id"]: a for a in arts}
            pub_ids = list({a["publisher_id"] for a in arts})
            pubs = await db.agg_publishers.find(
                {"id": {"$in": pub_ids}},
                {"_id": 0, "id": 1, "name": 1, "slug": 1},
            ).to_list(len(pub_ids))
            publishers_by_id = {p["id"]: p for p in pubs}

        items = []
        for r in click_rows:
            aid = r["_id"]
            art = articles_by_id.get(aid)
            if not art:
                # Click on an article we no longer have (purged) — skip.
                continue
            pub = publishers_by_id.get(art.get("publisher_id"), {})
            items.append({
                "article_id": aid,
                "title": art.get("title"),
                "original_url": art.get("original_url"),
                "published_at": art.get("published_at"),
                "publisher": {"id": pub.get("id"), "name": pub.get("name"), "slug": pub.get("slug")},
                "clicks": r["clicks"],
                "impressions": impressions_by_id.get(aid, 0),
            })

        # Currently viewing = distinct sessions in the last 60s across both
        # impressions and clicks. This is a cheap proxy; not an exact figure.
        live_sessions: set = set()
        async for row in db.agg_article_impressions.find(
            {"seen_at": {"$gte": live_cutoff}}, {"_id": 0, "session_id": 1},
        ):
            sid = row.get("session_id")
            if sid:
                live_sessions.add(sid)
        async for row in db.agg_article_clicks.find(
            {"clicked_at": {"$gte": live_cutoff}}, {"_id": 0, "session_id": 1},
        ):
            sid = row.get("session_id")
            if sid:
                live_sessions.add(sid)

        # Window totals (the "overall room" numbers above the table)
        totals = {
            "clicks": sum(r["clicks"] for r in click_rows),
            "impressions": sum(impressions_by_id.values()),
            "live_visitors": len(live_sessions),
        }
        return {
            "hours": hours,
            "items": items,
            "totals": totals,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

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
        # Push to Resend. Failure to push does NOT fail the request — we always
        # have the email captured locally so we can re-sync later if needed.
        # Run the blocking HTTP call in a thread so a slow Resend call doesn't
        # freeze the entire async event loop (and every other in-flight request).
        import asyncio as _asyncio
        brevo_result = await _asyncio.to_thread(
            brevo_add_to_list,
            email, NEWSLETTER_LIST_NAME, {"SOURCE": payload.source_page or "thehousingnews.com"},
        )
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
        response: Response,
        days: int = Query(default=14, ge=1, le=90),
        limit: int = Query(default=8, ge=1, le=30),
    ):
        """Public-safe top N hashtags across approved member posts in the last
        `days`. No auth — used by the Landing page social-proof strip to show
        what real estate professionals on the platform are writing about.
        Cached in-process for 90 seconds.
        """
        _set_public_cache(response, 90)
        import time as _time
        cache_key = f"tt:{days}:{limit}"
        cached = _PUBLIC_CACHE.get(cache_key)
        now_ts = _time.time()
        if cached and cached[1] > now_ts:
            return cached[0]
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
        result = {"items": [{"tag": r["_id"], "count": r["count"]} for r in rows], "days": days}
        _PUBLIC_CACHE[cache_key] = (result, now_ts + 90)
        return result

    @router.get("/recent-members")
    async def recent_members(response: Response, limit: int = Query(default=8, ge=1, le=30)):
        """Public-safe list of recently-active members for the Landing page.
        Returns only name, market, avatar_path, and a short snippet from the
        member's most recent approved post. No emails, no IDs that aren't
        already exposed via /profile/{user_id}.

        "Recently active" = has at least one approved post within the last 30
        days. Sorted by most-recent post timestamp, descending.

        Cached in-process for 90 seconds to keep landing-page load fast.
        """
        _set_public_cache(response, 90)
        import time as _time
        cache_key = f"rm:{limit}"
        cached = _PUBLIC_CACHE.get(cache_key)
        now_ts = _time.time()
        if cached and cached[1] > now_ts:
            return cached[0]
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
        # Only show approved + non-suspended + non-test + non-stub members
        # with a profile. The `is_test_email` filter is defence-in-depth — a
        # missed call to the suspend script must never leak e2e fixtures
        # onto the public landing page.
        from services.test_email_filter import is_test_email
        users = await db.users.find(
            {
                "user_id": {"$in": user_ids},
                "status": "approved",
                "suspended": {"$ne": True},
            },
            {"_id": 0, "user_id": 1, "email": 1},
        ).to_list(500)
        approved_ids = {u["user_id"] for u in users if not is_test_email(u.get("email", ""))}
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
        result = {"items": items}
        _PUBLIC_CACHE[cache_key] = (result, now_ts + 90)
        return result

    @router.get("/new-members")
    async def new_members(
        response: Response,
        days: int = Query(default=14, ge=1, le=90),
        limit: int = Query(default=5, ge=1, le=20),
    ):
        """Public list of members who joined recently — for the Landing
        "Members joined this week" strip. Sorted by most-recent join
        timestamp. Only returns approved + non-suspended + non-stub
        members with a real profile. No emails, no IDs beyond what is
        already exposed via /profile/{user_id}. Cached for 90s.
        """
        _set_public_cache(response, 90)
        import time as _time
        cache_key = f"nm:{days}:{limit}"
        cached = _PUBLIC_CACHE.get(cache_key)
        now_ts = _time.time()
        if cached and cached[1] > now_ts:
            return cached[0]
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        from services.test_email_filter import is_test_email
        users = await db.users.find(
            {
                "status": "approved",
                "suspended": {"$ne": True},
                "created_at": {"$gte": cutoff_iso},
            },
            {"_id": 0, "user_id": 1, "created_at": 1, "email": 1},
        ).sort("created_at", -1).to_list(limit * 4)
        if not users:
            return {"items": [], "days": days}

        uids = [u["user_id"] for u in users if not is_test_email(u.get("email", ""))]
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
        result = {"items": items, "days": days}
        _PUBLIC_CACHE[cache_key] = (result, now_ts + 90)
        return result

    return router
