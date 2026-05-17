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

    return router
