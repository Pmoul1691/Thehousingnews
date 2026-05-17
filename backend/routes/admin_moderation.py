"""Admin moderation queue — flagged posts/essays/replies for human review.

A human admin reviews items flagged by Claude (`status == "flagged_by_ai"`)
and either:
  • Overrides Claude (restores the original status — content publishes).
  • Confirms the decline (status -> "declined" — content stays hidden).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header, Query
from pydantic import BaseModel

from services.auth_helpers import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/moderation", tags=["admin-moderation"])


class AdminDecision(BaseModel):
    decision: str  # "approve_override" | "confirm_decline"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptUpdate(BaseModel):
    value: str


def setup(db):
    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        u = await get_current_user(db, session_token, authorization)
        if not u.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin only")
        return u

    @router.get("/queue")
    async def queue(
        admin=Cookie(default=None),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
        kind: Optional[str] = Query(default=None,
                                    description="post|essay|reply (all if omitted)"),
        decided: bool = Query(default=False,
                              description="Include items admin already decided"),
        limit: int = Query(default=50, ge=1, le=200),
    ):
        # Auth
        await _admin(session_token, authorization)

        match: dict = {"verdict": {"$in": ["flag", "decline"]}}
        if kind:
            match["target_kind"] = kind
        if not decided:
            match["admin_decision"] = None

        reviews = await db.moderation_reviews.find(
            match, {"_id": 0},
        ).sort("reviewed_at", -1).limit(limit).to_list(limit)

        # Hydrate target snippets + author identity
        post_ids = [r["target_id"] for r in reviews if r["target_kind"] in ("post", "essay")]
        reply_ids = [r["target_id"] for r in reviews if r["target_kind"] == "reply"]
        user_ids = list({r["user_id"] for r in reviews if r.get("user_id")})

        posts_by_id: dict = {}
        if post_ids:
            async for p in db.posts.find(
                {"post_id": {"$in": post_ids}},
                {"_id": 0, "post_id": 1, "title": 1, "kind": 1, "status": 1, "created_at": 1},
            ):
                posts_by_id[p["post_id"]] = p
        replies_by_id: dict = {}
        if reply_ids:
            async for r in db.replies.find(
                {"reply_id": {"$in": reply_ids}},
                {"_id": 0, "reply_id": 1, "post_id": 1, "status": 1, "created_at": 1},
            ):
                replies_by_id[r["reply_id"]] = r
        users_by_id: dict = {}
        if user_ids:
            async for u in db.users.find(
                {"user_id": {"$in": user_ids}},
                {"_id": 0, "user_id": 1, "name": 1, "email": 1},
            ):
                users_by_id[u["user_id"]] = u

        for r in reviews:
            if r["target_kind"] in ("post", "essay"):
                r["target"] = posts_by_id.get(r["target_id"])
            else:
                r["target"] = replies_by_id.get(r["target_id"])
            r["author"] = users_by_id.get(r.get("user_id"))

        return {"items": reviews, "count": len(reviews)}

    @router.get("/stats")
    async def stats(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        pending = await db.moderation_reviews.count_documents(
            {"verdict": {"$in": ["flag", "decline"]}, "admin_decision": None},
        )
        flagged_24h = await db.moderation_reviews.count_documents(
            {"reviewed_at": {"$gte": cutoff}, "verdict": "flag"},
        )
        declined_24h = await db.moderation_reviews.count_documents(
            {"reviewed_at": {"$gte": cutoff}, "verdict": "decline"},
        )
        reviewed_24h = await db.moderation_reviews.count_documents(
            {"reviewed_at": {"$gte": cutoff}},
        )
        return {
            "pending": pending,
            "flagged_24h": flagged_24h,
            "declined_24h": declined_24h,
            "reviewed_24h": reviewed_24h,
        }

    @router.get("/patterns")
    async def patterns(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
        days: int = Query(default=30, ge=1, le=180),
    ):
        """Aggregate signal across the moderation_reviews audit trail.

        Returns:
          - top_categories: top 5 violation categories in the window
          - top_flagged_users: members generating the most flags/declines
          - daily_volume: per-day counts of reviewed/flagged/declined
          - claude_accuracy: how often the admin agreed with Claude's verdict
                             (i.e. admin chose `confirm_decline` on decisions),
                             vs. how often the admin overrode Claude
        """
        await _admin(session_token, authorization)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Top categories
        cat_pipeline = [
            {"$match": {"reviewed_at": {"$gte": cutoff},
                        "verdict": {"$in": ["flag", "decline"]}}},
            {"$unwind": "$categories"},
            {"$match": {"categories": {"$ne": "none"}}},
            {"$group": {"_id": "$categories", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ]
        cat_rows = await db.moderation_reviews.aggregate(cat_pipeline).to_list(8)
        top_categories = [{"category": r["_id"], "count": r["count"]} for r in cat_rows]

        # Top flagged users
        user_pipeline = [
            {"$match": {"reviewed_at": {"$gte": cutoff},
                        "verdict": {"$in": ["flag", "decline"]}}},
            {"$group": {
                "_id": "$user_id",
                "flags": {"$sum": {"$cond": [{"$eq": ["$verdict", "flag"]}, 1, 0]}},
                "declines": {"$sum": {"$cond": [{"$eq": ["$verdict", "decline"]}, 1, 0]}},
                "total": {"$sum": 1},
            }},
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ]
        user_rows = await db.moderation_reviews.aggregate(user_pipeline).to_list(5)
        uids = [r["_id"] for r in user_rows if r["_id"]]
        users_by_id: dict = {}
        if uids:
            async for u in db.users.find(
                {"user_id": {"$in": uids}},
                {"_id": 0, "user_id": 1, "name": 1, "email": 1},
            ):
                users_by_id[u["user_id"]] = u
        top_flagged_users = [{
            "user_id": r["_id"],
            "name": (users_by_id.get(r["_id"]) or {}).get("name") or "—",
            "email": (users_by_id.get(r["_id"]) or {}).get("email") or "",
            "flags": r["flags"],
            "declines": r["declines"],
            "total": r["total"],
        } for r in user_rows]

        # Daily volume (last 14 days for the bar)
        bar_cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        daily_pipeline = [
            {"$match": {"reviewed_at": {"$gte": bar_cutoff}}},
            {"$project": {
                "day": {"$substr": ["$reviewed_at", 0, 10]},
                "verdict": 1,
            }},
            {"$group": {
                "_id": "$day",
                "reviewed": {"$sum": 1},
                "flagged": {"$sum": {"$cond": [{"$eq": ["$verdict", "flag"]}, 1, 0]}},
                "declined": {"$sum": {"$cond": [{"$eq": ["$verdict", "decline"]}, 1, 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]
        daily_rows = await db.moderation_reviews.aggregate(daily_pipeline).to_list(14)
        daily_volume = [{
            "day": r["_id"], "reviewed": r["reviewed"],
            "flagged": r["flagged"], "declined": r["declined"],
        } for r in daily_rows]

        # Claude accuracy — among decided reviews
        decided_total = await db.moderation_reviews.count_documents({
            "reviewed_at": {"$gte": cutoff},
            "admin_decision": {"$in": ["approve_override", "confirm_decline"]},
        })
        admin_agreed = await db.moderation_reviews.count_documents({
            "reviewed_at": {"$gte": cutoff},
            "admin_decision": "confirm_decline",
        })
        admin_overrode = await db.moderation_reviews.count_documents({
            "reviewed_at": {"$gte": cutoff},
            "admin_decision": "approve_override",
        })
        accuracy = round(100 * admin_agreed / decided_total) if decided_total else None

        return {
            "window_days": days,
            "top_categories": top_categories,
            "top_flagged_users": top_flagged_users,
            "daily_volume": daily_volume,
            "claude_accuracy": {
                "decided_total": decided_total,
                "admin_agreed": admin_agreed,
                "admin_overrode": admin_overrode,
                "agreement_pct": accuracy,
            },
        }

    @router.post("/{review_id}/decide")
    async def decide(
        review_id: str,
        body: AdminDecision,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        admin = await _admin(session_token, authorization)
        decision = body.decision
        if decision not in ("approve_override", "confirm_decline"):
            raise HTTPException(status_code=400, detail="Invalid decision")

        review = await db.moderation_reviews.find_one({"id": review_id}, {"_id": 0})
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        if review.get("admin_decision"):
            raise HTTPException(status_code=409, detail="Already decided")

        target_kind = review["target_kind"]
        target_id = review["target_id"]
        coll = db.posts if target_kind in ("post", "essay") else db.replies
        id_field = "post_id" if target_kind in ("post", "essay") else "reply_id"

        if decision == "approve_override":
            # Restore the target to a publishable state. Posts/replies that
            # were intercepted before release go back to pending_release;
            # essays that were already due go to approved.
            target_doc = await coll.find_one({id_field: target_id}, {"_id": 0})
            if not target_doc:
                raise HTTPException(status_code=404, detail="Target gone")
            release_at = target_doc.get("release_at")
            new_status = "approved"
            if target_kind == "essay":
                new_status = "approved"
            else:
                # Decide based on whether release window has passed
                if release_at and release_at > _now_iso():
                    new_status = "pending_release"
                else:
                    new_status = "approved"
            await coll.update_one(
                {id_field: target_id},
                {"$set": {"status": new_status,
                          "moderation_override_by": admin["user_id"]}},
            )
        else:  # confirm_decline
            await coll.update_one(
                {id_field: target_id},
                {"$set": {"status": "declined"}},
            )

        await db.moderation_reviews.update_one(
            {"id": review_id},
            {"$set": {
                "admin_decision": decision,
                "admin_user_id": admin["user_id"],
                "admin_decided_at": _now_iso(),
            }},
        )
        return {"ok": True, "decision": decision}

    @router.get("/prompt")
    async def get_prompt(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        from services.moderation import SYSTEM_PROMPT, _get_active_prompt
        active = await _get_active_prompt(db)
        row = await db.moderation_settings.find_one(
            {"key": "system_prompt"}, {"_id": 0, "value": 1, "updated_at": 1, "updated_by": 1},
        )
        return {
            "active": active,
            "default": SYSTEM_PROMPT,
            "is_custom": active.strip() != SYSTEM_PROMPT.strip(),
            "updated_at": (row or {}).get("updated_at"),
            "updated_by": (row or {}).get("updated_by"),
        }

    @router.put("/prompt")
    async def update_prompt(
        body: PromptUpdate,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        admin = await _admin(session_token, authorization)
        value = (body.value or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        if len(value) > 20000:
            raise HTTPException(status_code=400, detail="Prompt too long (max 20k chars)")
        await db.moderation_settings.update_one(
            {"key": "system_prompt"},
            {"$set": {
                "key": "system_prompt",
                "value": value,
                "updated_at": _now_iso(),
                "updated_by": admin["user_id"],
            }},
            upsert=True,
        )
        return {"ok": True, "len": len(value)}

    @router.post("/prompt/reset")
    async def reset_prompt(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        await db.moderation_settings.delete_one({"key": "system_prompt"})
        return {"ok": True}

    @router.get("/prompt/suggestions")
    async def prompt_suggestions(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Surface concrete tuning suggestions from the audit trail.

        Looks at: (a) categories where admins overrode Claude most often
        (Claude is too aggressive on these — relax the rule), and
        (b) categories where the override rate is 0% on multiple decisions
        (Claude is calibrated well).
        """
        await _admin(session_token, authorization)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        rows = await db.moderation_reviews.find(
            {"reviewed_at": {"$gte": cutoff},
             "admin_decision": {"$in": ["approve_override", "confirm_decline"]}},
            {"_id": 0, "categories": 1, "admin_decision": 1},
        ).to_list(2000)

        # Per-category override rate
        per_cat: dict = {}
        for r in rows:
            for c in (r.get("categories") or []):
                if c == "none":
                    continue
                per_cat.setdefault(c, {"total": 0, "overridden": 0})
                per_cat[c]["total"] += 1
                if r["admin_decision"] == "approve_override":
                    per_cat[c]["overridden"] += 1

        too_aggressive = []
        well_calibrated = []
        for cat, s in per_cat.items():
            if s["total"] < 3:
                continue  # Not enough data
            rate = s["overridden"] / s["total"]
            entry = {"category": cat, "total": s["total"],
                     "overridden": s["overridden"], "override_rate": round(rate * 100)}
            if rate >= 0.5:
                too_aggressive.append(entry)
            elif rate == 0 and s["total"] >= 5:
                well_calibrated.append(entry)

        too_aggressive.sort(key=lambda x: -x["override_rate"])
        return {
            "too_aggressive": too_aggressive[:5],
            "well_calibrated": well_calibrated[:5],
            "window_days": 60,
            "sample_size": len(rows),
        }

    @router.post("/regression-test")
    async def regression_test(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Run all canonical cases through the live moderation pipeline and
        return per-case pass/fail. Uses the currently active prompt — useful
        right after editing the prompt to confirm nothing regressed.

        ⚠️ Each run costs ~$0.02 in Claude credits (one call per case).
        """
        await _admin(session_token, authorization)
        from services.moderation import review_content
        from services.moderation_cases import CANONICAL_CASES, case_passes
        import asyncio

        async def run_one(c):
            try:
                verdict = await review_content(
                    db=db,
                    target_kind=c["target_kind"],
                    text=c["text"],
                    title=c["title"] or None,
                )
                passed = case_passes(c, verdict)
                return {
                    "name": c["name"],
                    "description": c["description"],
                    "expected_verdict": c["expected_verdict"],
                    "expected_categories": c["expected_categories"],
                    "got_verdict": verdict.get("verdict"),
                    "got_categories": verdict.get("categories"),
                    "got_score": verdict.get("risk_score"),
                    "got_reasoning": verdict.get("reasoning"),
                    "passed": passed,
                }
            except Exception as exc:
                logger.exception(f"regression case {c['name']} failed")
                return {
                    "name": c["name"],
                    "description": c["description"],
                    "expected_verdict": c["expected_verdict"],
                    "passed": False,
                    "error": str(exc),
                }

        # Run cases concurrently — they don't share state.
        results = await asyncio.gather(*[run_one(c) for c in CANONICAL_CASES])
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(100 * passed / total) if total else 0,
            "results": results,
            "run_at": _now_iso(),
        }

    return router
