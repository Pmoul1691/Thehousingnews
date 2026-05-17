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

    @router.post("/send-summary-now")
    async def send_summary_now(
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Fire the daily admin summary email immediately. Useful for testing
        the template or pulling a fresh snapshot mid-day."""
        await _admin(session_token, authorization)
        from services.admin_summary import send_admin_summary
        return await send_admin_summary(db)

    @router.get("/members")
    async def list_members(
        q: str | None = None,
        status: str | None = None,
        limit: int = 30,
        offset: int = 0,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        limit = max(1, min(100, limit))
        offset = max(0, offset)
        query: dict = {}
        if status and status in ("approved", "invited", "pending", "needs_application", "declined"):
            query["status"] = status
        if status == "suspended":
            query["suspended"] = True
        if q:
            import re
            safe = re.escape(q.strip())
            query["$or"] = [
                {"email": {"$regex": safe, "$options": "i"}},
                {"name":  {"$regex": safe, "$options": "i"}},
            ]
        total = await db.users.count_documents(query)
        users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
        uids = [u["user_id"] for u in users]
        profiles = await db.profiles.find(
            {"user_id": {"$in": uids}},
            {"_id": 0, "user_id": 1, "avatar_path": 1, "market": 1, "is_stub": 1},
        ).to_list(500) if uids else []
        pmap = {p["user_id"]: p for p in profiles}

        # Bulk-count posts per user in one aggregate
        post_counts = {}
        if uids:
            rows = await db.posts.aggregate([
                {"$match": {"user_id": {"$in": uids}}},
                {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            ]).to_list(500)
            post_counts = {r["_id"]: r["n"] for r in rows}

        out = []
        for u in users:
            prof = pmap.get(u["user_id"]) or {}
            out.append({
                "user_id": u["user_id"],
                "email": u["email"],
                "name": u.get("name") or "",
                "status": u.get("status"),
                "suspended": u.get("suspended", False),
                "is_admin": u.get("is_admin", False),
                "source": u.get("source"),
                "created_at": u.get("created_at"),
                "last_login_at": u.get("last_login_at"),
                "market": prof.get("market"),
                "avatar_path": prof.get("avatar_path"),
                "is_stub": prof.get("is_stub", False),
                "posts_total": post_counts.get(u["user_id"], 0),
            })
        return {"items": out, "total": total, "limit": limit, "offset": offset}

    @router.post("/members/bulk")
    async def bulk_action(
        payload: dict,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        """Apply one bulk action to a list of user_ids. Returns per-user
        outcome so the UI can show partial failures.

        Supported actions:
          - suspend / unsuspend       — set/clear `suspended` flag
          - approve_invited           — flip status `invited` → `approved`
        """
        await _admin(session_token, authorization)
        action = (payload or {}).get("action")
        ids = list(payload.get("user_ids") or [])
        if action not in ("suspend", "unsuspend", "approve_invited"):
            raise HTTPException(status_code=400, detail="Unknown action")
        if not ids or len(ids) > 500:
            raise HTTPException(status_code=400, detail="user_ids must be a list of 1–500 ids")
        if action in ("suspend", "unsuspend"):
            update = {"$set": {"suspended": action == "suspend"}}
            filt = {"user_id": {"$in": ids}}
        else:  # approve_invited
            update = {"$set": {"status": "approved"}}
            filt = {"user_id": {"$in": ids}, "status": "invited"}
        res = await db.users.update_many(filt, update)
        return {"ok": True, "matched": res.matched_count, "modified": res.modified_count, "action": action, "count_requested": len(ids)}

    @router.get("/members/{user_id}")
    async def member_detail(
        user_id: str,
        session_token: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ):
        await _admin(session_token, authorization)
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        profile = await db.profiles.find_one({"user_id": user_id}, {"_id": 0}) or {}

        # Post counts by kind + status
        post_rows = await db.posts.aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": {"kind": "$kind", "status": "$status"}, "n": {"$sum": 1}}},
        ]).to_list(50)
        by_kind: dict = {}
        for r in post_rows:
            k = r["_id"].get("kind") or "post"
            s = r["_id"].get("status") or "unknown"
            by_kind.setdefault(k, {"total": 0, "by_status": {}})
            by_kind[k]["total"] += r["n"]
            by_kind[k]["by_status"][s] = by_kind[k]["by_status"].get(s, 0) + r["n"]

        # Replies, reactions, follows, briefs
        replies_count   = await db.replies.count_documents({"user_id": user_id}) if "replies" in await db.list_collection_names() else 0
        reactions_count = await db.reactions.count_documents({"user_id": user_id}) if "reactions" in await db.list_collection_names() else 0

        briefs_sent    = await db.brief_dispatches.count_documents({"recipient_user_id": user_id})
        briefs_opened  = await db.brief_dispatches.count_documents({"recipient_user_id": user_id, "first_opened_at": {"$ne": None}})
        briefs_clicked = await db.brief_dispatches.count_documents({"recipient_user_id": user_id, "first_clicked_at": {"$ne": None}})

        invites_sent_by_user = await db.invite_tokens.count_documents({"sent_by": user_id}) if "invite_tokens" in await db.list_collection_names() else 0

        # PAT counts
        pats_live    = await db.pats.count_documents({"user_id": user_id, "revoked_at": None})
        pats_revoked = await db.pats.count_documents({"user_id": user_id, "revoked_at": {"$ne": None}})

        # Recent posts (last 20)
        recent_posts = await db.posts.find(
            {"user_id": user_id},
            {"_id": 0, "post_id": 1, "kind": 1, "status": 1, "title": 1, "text": 1, "created_at": 1, "release_at": 1, "tags": 1},
        ).sort("created_at", -1).limit(20).to_list(20)

        return {
            "user": {
                "user_id": user["user_id"],
                "email": user["email"],
                "name": user.get("name") or "",
                "picture": user.get("picture"),
                "status": user.get("status"),
                "suspended": user.get("suspended", False),
                "is_admin": user.get("is_admin", False),
                "source": user.get("source"),
                "created_at": user.get("created_at"),
                "last_login_at": user.get("last_login_at"),
                "tos_accepted_at": user.get("tos_accepted_at"),
                "brief_morning_optout": user.get("brief_morning_optout", False),
                "brief_evening_optout": user.get("brief_evening_optout", False),
                "supporter_until": user.get("supporter_until"),
                "partner_tier": user.get("partner_tier"),
            },
            "profile": {
                "name": profile.get("name"),
                "market": profile.get("market"),
                "bio": profile.get("bio"),
                "avatar_path": profile.get("avatar_path"),
                "linkedin_url": profile.get("linkedin_url"),
                "is_stub": profile.get("is_stub", False),
                "objectives": profile.get("objectives") or [],
                "updated_at": profile.get("updated_at"),
            },
            "stats": {
                "posts_by_kind": by_kind,
                "replies": replies_count,
                "reactions": reactions_count,
                "briefs_sent": briefs_sent,
                "briefs_opened": briefs_opened,
                "briefs_clicked": briefs_clicked,
                "invites_sent": invites_sent_by_user,
                "pats_live": pats_live,
                "pats_revoked": pats_revoked,
            },
            "recent_posts": recent_posts,
        }

    return router
