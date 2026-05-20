"""Site analytics — admin-only metrics dashboard.

Covers four areas:
  • Acquisition  — new members, sources, funnel
  • Engagement   — daily active members, posts/replies created, briefing opens
  • Retention    — at-risk and churned (inactive 30/60/90+ days)
  • Traffic      — pageviews + unique visitors per day (from analytics_events)

All data is derived from existing collections plus a tiny new
`analytics_events` collection populated by `POST /api/events/pageview`.
"""
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Cookie, Header, HTTPException

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/site-analytics", tags=["admin-analytics"])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _days_ago(n: int) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(days=n))


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        u = await get_current_user(db, session_token, authorization)
        if not u.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin only")
        return u

    @router.get("")
    async def overview(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)

        d7 = _days_ago(7)
        d30 = _days_ago(30)
        d60 = _days_ago(60)
        d90 = _days_ago(90)

        # ── ACQUISITION ────────────────────────────────────────────────
        total_members = await db.users.count_documents({"status": "approved"})
        suspended = await db.users.count_documents({"suspended": True, "status": "approved"})
        new_7 = await db.users.count_documents({"created_at": {"$gte": d7}})
        new_30 = await db.users.count_documents({"created_at": {"$gte": d30}})
        new_90 = await db.users.count_documents({"created_at": {"$gte": d90}})
        pending = await db.users.count_documents({"status": "pending"})
        invited = await db.users.count_documents({"status": "invited"})
        declined = await db.users.count_documents({"status": "declined"})

        # Funnel: count by status
        funnel = {
            "applied":  await db.users.count_documents({"status": "needs_application"}),
            "pending":  pending,
            "invited":  invited,
            "approved": total_members,
            "declined": declined,
            "suspended": suspended,
        }

        # Source breakdown
        sources: Counter = Counter()
        async for u in db.users.find({}, {"_id": 0, "source": 1}):
            sources[u.get("source") or "unknown"] += 1
        source_breakdown = [{"source": s, "count": c} for s, c in sources.most_common(10)]

        # ── ENGAGEMENT ─────────────────────────────────────────────────
        # Active members = signed in within window
        active_7  = await db.users.count_documents({"last_login_at": {"$gte": d7}})
        active_30 = await db.users.count_documents({"last_login_at": {"$gte": d30}})
        active_90 = await db.users.count_documents({"last_login_at": {"$gte": d90}})

        # Content created (last 30d)
        essays_30 = await db.posts.count_documents({"kind": "essay", "created_at": {"$gte": d30}})
        posts_30  = await db.posts.count_documents({"kind": "post",  "created_at": {"$gte": d30}})
        replies_30 = await db.replies.count_documents({"created_at": {"$gte": d30}})
        reads_30 = await db.reads.count_documents({"created_at": {"$gte": d30}})

        # Lifetime content
        essays_total = await db.posts.count_documents({"kind": "essay"})
        posts_total = await db.posts.count_documents({"kind": "post"})
        replies_total = await db.replies.count_documents({})

        # Daily content volume — last 14 days
        content_volume = await db.posts.aggregate([
            {"$match": {"created_at": {"$gte": _days_ago(14)}}},
            {"$project": {"day": {"$substr": ["$created_at", 0, 10]}, "kind": 1}},
            {"$group": {
                "_id": "$day",
                "essays": {"$sum": {"$cond": [{"$eq": ["$kind", "essay"]}, 1, 0]}},
                "posts":  {"$sum": {"$cond": [{"$eq": ["$kind", "post"]}, 1, 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]).to_list(14)

        # ── RETENTION / CHURN ──────────────────────────────────────────
        # We treat anyone approved who hasn't logged in for 60+ days as
        # "at risk", 90+ as "churned proxy". Real churn would require a
        # paid-subscription model — for now this is a behavioural proxy.
        at_risk_30 = await db.users.count_documents({
            "status": "approved",
            "suspended": {"$ne": True},
            "last_login_at": {"$lt": d30, "$gte": d60},
        })
        at_risk_60 = await db.users.count_documents({
            "status": "approved",
            "suspended": {"$ne": True},
            "last_login_at": {"$lt": d60, "$gte": d90},
        })
        churned_90 = await db.users.count_documents({
            "status": "approved",
            "suspended": {"$ne": True},
            "last_login_at": {"$lt": d90},
        })
        ever_logged_in = await db.users.count_documents({
            "status": "approved", "last_login_at": {"$ne": None},
        })
        churn_rate_pct = round(100 * churned_90 / ever_logged_in) if ever_logged_in else 0

        # ── TRAFFIC (from analytics_events) ────────────────────────────
        pv_pipeline_14 = [
            {"$match": {"kind": "pageview", "created_at": {"$gte": _days_ago(14)}}},
            {"$project": {
                "day": {"$substr": ["$created_at", 0, 10]},
                "session_id": 1, "user_id": 1, "path": 1,
            }},
            {"$group": {
                "_id": "$day",
                "pageviews": {"$sum": 1},
                "unique_sessions": {"$addToSet": "$session_id"},
                "unique_users": {"$addToSet": "$user_id"},
            }},
            {"$project": {
                "day": "$_id", "_id": 0, "pageviews": 1,
                "unique_sessions": {"$size": "$unique_sessions"},
                "unique_users": {"$size": "$unique_users"},
            }},
            {"$sort": {"day": 1}},
        ]
        traffic_daily = await db.analytics_events.aggregate(pv_pipeline_14).to_list(14)

        # "Today" window. We anchor on the UTC calendar day — same anchor
        # the daily aggregation above uses (substring of created_at). That
        # keeps the totals consistent across stats vs. chart and avoids
        # the off-by-one issue between server-local and UTC midnight.
        today_str = _iso(datetime.now(timezone.utc))[:10]
        today_row = next(
            (r for r in traffic_daily if r.get("day") == today_str),
            {"pageviews": 0, "unique_sessions": 0, "unique_users": 0},
        )

        # Hourly breakdown for today — drives the new daily-visitor chart.
        # 24 bars, hours 0..23 UTC, zero-filled so empty hours render flat.
        hourly_rows = await db.analytics_events.aggregate([
            {"$match": {
                "kind": "pageview",
                "created_at": {"$gte": f"{today_str}T00:00:00",
                               "$lte": f"{today_str}T23:59:59.999999"},
            }},
            {"$project": {
                "hour": {"$toInt": {"$substr": ["$created_at", 11, 2]}},
                "session_id": 1, "user_id": 1,
            }},
            {"$group": {
                "_id": "$hour",
                "pageviews": {"$sum": 1},
                "unique_sessions": {"$addToSet": "$session_id"},
                "unique_users": {"$addToSet": "$user_id"},
            }},
        ]).to_list(24)
        hourly_lookup = {r["_id"]: r for r in hourly_rows}
        hourly_today = []
        for h in range(24):
            row = hourly_lookup.get(h)
            hourly_today.append({
                "hour": h,
                "pageviews": (row or {}).get("pageviews", 0),
                "unique_sessions": len((row or {}).get("unique_sessions") or []),
                "unique_users": len((row or {}).get("unique_users") or []),
            })

        pv_7 = await db.analytics_events.count_documents(
            {"kind": "pageview", "created_at": {"$gte": d7}},
        )
        pv_30 = await db.analytics_events.count_documents(
            {"kind": "pageview", "created_at": {"$gte": d30}},
        )

        # Top paths last 30d
        top_paths_rows = await db.analytics_events.aggregate([
            {"$match": {"kind": "pageview", "created_at": {"$gte": d30}}},
            {"$group": {"_id": "$path", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 10},
        ]).to_list(10)
        top_paths = [{"path": r["_id"] or "(unknown)", "views": r["n"]} for r in top_paths_rows]

        # ── TOP CONTRIBUTORS ───────────────────────────────────────────
        contributor_rows = await db.posts.aggregate([
            {"$match": {"status": "approved", "kind": "essay"}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 5},
        ]).to_list(5)
        cuids = [r["_id"] for r in contributor_rows if r["_id"]]
        names: dict = {}
        if cuids:
            async for u in db.users.find(
                {"user_id": {"$in": cuids}},
                {"_id": 0, "user_id": 1, "name": 1, "email": 1},
            ):
                names[u["user_id"]] = {"name": u.get("name") or "—", "email": u.get("email")}
        top_contributors = [{
            "user_id": r["_id"],
            "name": names.get(r["_id"], {}).get("name", "—"),
            "email": names.get(r["_id"], {}).get("email"),
            "essays": r["n"],
        } for r in contributor_rows]

        return {
            "as_of": _iso(datetime.now(timezone.utc)),
            "acquisition": {
                "total_members": total_members,
                "new_7d": new_7, "new_30d": new_30, "new_90d": new_90,
                "funnel": funnel,
                "source_breakdown": source_breakdown,
            },
            "engagement": {
                "active_7d": active_7, "active_30d": active_30, "active_90d": active_90,
                "essays_30d": essays_30, "posts_30d": posts_30,
                "replies_30d": replies_30, "reads_30d": reads_30,
                "essays_total": essays_total, "posts_total": posts_total,
                "replies_total": replies_total,
                "content_volume_14d": [{
                    "day": r["_id"], "essays": r["essays"], "posts": r["posts"],
                } for r in content_volume],
                "top_contributors": top_contributors,
            },
            "retention": {
                "at_risk_30_60": at_risk_30,
                "at_risk_60_90": at_risk_60,
                "churned_90plus": churned_90,
                "ever_logged_in": ever_logged_in,
                "churn_rate_pct": churn_rate_pct,
                "suspended": suspended,
            },
            "traffic": {
                "pageviews_today": today_row["pageviews"],
                "sessions_today": today_row["unique_sessions"],
                "members_today": today_row["unique_users"],
                "hourly_today": hourly_today,
                "pageviews_7d": pv_7,
                "pageviews_30d": pv_30,
                "daily_14d": traffic_daily,
                "top_paths_30d": top_paths,
            },
        }

    return router
