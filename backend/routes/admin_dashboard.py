"""Admin Dashboard — single endpoint that returns all the aggregated stats
shown on the unified /admin overview page.

One endpoint instead of 10 keeps the dashboard load fast and the frontend
trivial. All sections are public-by-admin only.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Header, HTTPException

from services.auth_helpers import get_current_user, is_admin_email


def _now() -> datetime:
    return datetime.now(timezone.utc)


def setup(db):
    router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])

    async def _admin(session_token, authorization):
        user = await get_current_user(db, session_token, authorization)
        if not is_admin_email(user["email"]):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/overview")
    async def overview(
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        now = _now()
        d7 = (now - timedelta(days=7)).isoformat()
        d30 = (now - timedelta(days=30)).isoformat()

        # ── Members ──
        members_total      = await db.users.count_documents({})
        members_approved   = await db.users.count_documents({"status": "approved"})
        members_invited    = await db.users.count_documents({"status": "invited"})
        members_pending    = await db.users.count_documents({"status": "pending"})
        members_suspended  = await db.users.count_documents({"suspended": True})
        members_new_7d     = await db.users.count_documents({"created_at": {"$gte": d7}})

        # ── Feed health ──
        publishers = await db.agg_publishers.find(
            {}, {"_id": 0, "id": 1, "slug": 1, "name": 1, "category": 1, "active": 1,
                 "last_fetched_at": 1, "last_fetch_status": 1, "error_count": 1},
        ).sort("name", 1).to_list(200)
        feed_total   = len(publishers)
        feed_active  = sum(1 for p in publishers if p.get("active"))
        feed_failing = sum(1 for p in publishers if (p.get("error_count") or 0) > 0)

        # ── Brief dispatch stats (last 30d, per kind) ──
        async def _brief_stats(kind: str) -> dict:
            q = {"kind": f"brief_{kind}", "created_at": {"$gte": d30}}
            sent    = await db.brief_dispatches.count_documents(q)
            opened  = await db.brief_dispatches.count_documents({**q, "first_opened_at": {"$ne": None}})
            clicked = await db.brief_dispatches.count_documents({**q, "first_clicked_at": {"$ne": None}})
            return {"sent": sent, "opened": opened, "clicked": clicked,
                    "open_rate":  round(opened / sent, 3)  if sent else 0,
                    "click_rate": round(clicked / sent, 3) if sent else 0}
        brief_morning = await _brief_stats("morning")
        brief_evening = await _brief_stats("evening")

        # ── Brevo invites overview ──
        invites_total    = await db.invite_tokens.count_documents({})
        invites_claimed  = await db.invite_tokens.count_documents({"claimed_at": {"$ne": None}})
        invites_pending  = await db.invite_tokens.count_documents({"claimed_at": None, "expires_at": {"$gt": now.isoformat()}})
        invites_expiring = await db.invite_tokens.count_documents({
            "claimed_at": None,
            "expires_at": {"$gt": now.isoformat(), "$lt": (now + timedelta(days=7)).isoformat()},
        })

        # ── Recent post activity (last 20) ──
        recent_posts = await db.posts.find(
            {}, {"_id": 0, "post_id": 1, "user_id": 1, "kind": 1, "status": 1,
                 "title": 1, "text": 1, "created_at": 1, "release_at": 1},
        ).sort("created_at", -1).limit(20).to_list(20)
        user_ids = list({p["user_id"] for p in recent_posts if p.get("user_id")})
        profiles = await db.profiles.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1, "name": 1, "avatar_path": 1, "market": 1},
        ).to_list(500) if user_ids else []
        pmap = {p["user_id"]: p for p in profiles}
        for p in recent_posts:
            prof = pmap.get(p.get("user_id"))
            p["author"] = {"name": (prof or {}).get("name"),
                           "market": (prof or {}).get("market"),
                           "avatar_path": (prof or {}).get("avatar_path")} if prof else None

        # ── Trending tags (last 30d, top 20) ──
        tag_pipeline = [
            {"$match": {"status": "approved", "release_at": {"$gte": d30},
                        "tags": {"$exists": True, "$ne": []}}},
            {"$unwind": "$tags"},
            {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": 20},
        ]
        trending_tags = await db.posts.aggregate(tag_pipeline).to_list(20)
        trending_tags = [{"tag": r["_id"], "count": r["count"]} for r in trending_tags]

        # ── Top members (most-published last 30d, top 10) ──
        top_pipeline = [
            {"$match": {"status": "approved", "release_at": {"$gte": d30}}},
            {"$group": {"_id": "$user_id", "posts": {"$sum": 1},
                        "last_at": {"$max": "$release_at"}}},
            {"$sort": {"posts": -1, "last_at": -1}},
            {"$limit": 10},
        ]
        top_rows = await db.posts.aggregate(top_pipeline).to_list(10)
        top_uids = [r["_id"] for r in top_rows]
        top_profiles = await db.profiles.find(
            {"user_id": {"$in": top_uids}},
            {"_id": 0, "user_id": 1, "name": 1, "avatar_path": 1, "market": 1},
        ).to_list(500) if top_uids else []
        top_pmap = {p["user_id"]: p for p in top_profiles}
        top_members = [
            {"user_id": r["_id"], "posts": r["posts"], "last_at": r["last_at"],
             **(top_pmap.get(r["_id"]) or {"name": "Unknown", "market": None, "avatar_path": None})}
            for r in top_rows
        ]

        # ── Application queue ──
        apps_pending  = await db.applications.count_documents({"status": "pending"})
        apps_approved = await db.applications.count_documents({"status": "approved"})
        apps_declined = await db.applications.count_documents({"status": "declined"})

        # ── Personal Access Tokens ──
        pats_live    = await db.pats.count_documents({"revoked_at": None})
        pats_revoked = await db.pats.count_documents({"revoked_at": {"$ne": None}})

        return {
            "generated_at": now.isoformat(),
            "members": {
                "total": members_total, "approved": members_approved,
                "invited": members_invited, "pending": members_pending,
                "suspended": members_suspended, "new_7d": members_new_7d,
            },
            "feed_health": {
                "total": feed_total, "active": feed_active, "failing": feed_failing,
                "publishers": publishers,
            },
            "briefs": {"morning": brief_morning, "evening": brief_evening},
            "invites": {
                "total": invites_total, "claimed": invites_claimed,
                "pending": invites_pending, "expiring_7d": invites_expiring,
            },
            "recent_posts": recent_posts,
            "trending_tags": trending_tags,
            "top_members": top_members,
            "applications": {
                "pending": apps_pending, "approved": apps_approved,
                "declined": apps_declined,
            },
            "pats": {"live": pats_live, "revoked": pats_revoked},
        }

    return router
