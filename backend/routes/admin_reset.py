"""Admin: reset the preview/staging DB to a clean state.

Wipes member-generated content but preserves:
  - admin user rows (so the operator stays signed in)
  - aggregator data (publishers, articles, newsletter signups, suggestions)
  - posts where `source == "substack_import"` (Pete's archive)

Guarded behind admin auth + a literal "RESET" confirmation token so it cannot
fire by accident in a curl misclick. Never available in production deploys —
operators are expected to flip the AGG_ALLOW_DB_RESET env var only on preview.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user, is_admin_email, is_user_admin

logger = logging.getLogger(__name__)


class ResetPayload(BaseModel):
    confirm: str = Field(..., description='Must be the literal string "RESET".')


def setup(db):
    router = APIRouter(prefix="/api/admin/preview-db", tags=["admin-preview"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    @router.get("/preview")
    async def reset_preview(admin=Depends(_admin)):
        """Dry-run: report what a real reset would delete, no writes."""
        # Default OFF — operators must explicitly opt in on preview environments.
        enabled = os.environ.get("AGG_ALLOW_DB_RESET", "false").lower() in ("1", "true", "yes")
        # Find admin user_ids that we will preserve.
        admin_users = await db.users.find(
            {"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1}
        ).to_list(50)
        admin_ids = [u["user_id"] for u in admin_users]
        substack_posts = await db.posts.count_documents({"source": "substack_import"})
        other_posts = await db.posts.count_documents({"source": {"$ne": "substack_import"}})
        return {
            "enabled": enabled,
            "preserves": {
                "admin_users": admin_users,
                "substack_imports": substack_posts,
                "aggregator_publishers": await db.agg_publishers.count_documents({}),
                "aggregator_articles": await db.agg_articles.count_documents({}),
            },
            "will_delete": {
                "posts_not_substack": other_posts,
                "applications": await db.applications.count_documents({}),
                "profiles": await db.profiles.count_documents({"user_id": {"$nin": admin_ids}}),
                "users_non_admin": await db.users.count_documents({"is_admin": {"$ne": True}}),
                "replies": await db.replies.count_documents({}),
                "follows": await db.follows.count_documents({}),
                "flags": await db.flags.count_documents({}),
                "drafts": await db.drafts.count_documents({}),
                "bookmarks": await db.bookmarks.count_documents({}),
                "reads": await db.reads.count_documents({}),
                "essay_dispatches": await db.essay_dispatches.count_documents({}),
                "payment_transactions": await db.payment_transactions.count_documents({}),
                "user_sessions_non_admin": await db.user_sessions.count_documents(
                    {"user_id": {"$nin": admin_ids}}
                ),
                "invite_codes": await db.invite_codes.count_documents({}),
                "prompt_suggestions": await db.prompt_suggestions.count_documents({}),
                "email_dispatches": await db.email_dispatches.count_documents({}),
                "email_events": await db.email_events.count_documents({}),
                "agg_newsletter_signups": await db.agg_newsletter_signups.count_documents({}),
                "agg_suggestions": await db.agg_suggestions.count_documents({}),
            },
        }

    @router.post("/reset")
    async def reset_db(payload: ResetPayload, admin=Depends(_admin)):
        """Destructive. Wipes member-generated content; keeps admin + Substack
        archive + aggregator. Returns counts of rows touched per collection."""
        if os.environ.get("AGG_ALLOW_DB_RESET", "false").lower() not in ("1", "true", "yes"):
            raise HTTPException(
                status_code=403,
                detail="DB reset is disabled in this environment.",
            )
        if (payload.confirm or "").strip() != "RESET":
            raise HTTPException(status_code=400, detail='Confirmation token must be the literal string "RESET".')

        admin_user_ids = [
            u["user_id"]
            async for u in db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1})
        ]

        results = {}
        # Posts: keep substack imports + admin-authored posts.
        r = await db.posts.delete_many({
            "source": {"$ne": "substack_import"},
            "user_id": {"$nin": admin_user_ids},
        })
        results["posts"] = r.deleted_count

        # Replies on deleted posts can stay deleted regardless of author.
        # Easier: any reply by a non-admin user.
        r = await db.replies.delete_many({"user_id": {"$nin": admin_user_ids}})
        results["replies"] = r.deleted_count

        # Profiles, applications: keep admin only.
        results["profiles"] = (await db.profiles.delete_many({"user_id": {"$nin": admin_user_ids}})).deleted_count
        results["applications"] = (await db.applications.delete_many({})).deleted_count

        # Member content collections — wipe in full.
        for coll in [
            "follows", "flags", "drafts", "bookmarks", "reads", "essay_dispatches",
            "payment_transactions", "invite_codes", "prompt_suggestions",
            "email_dispatches", "email_events", "objective_history",
            "agg_newsletter_signups", "agg_suggestions",
        ]:
            try:
                res = await db[coll].delete_many({})
                results[coll] = res.deleted_count
            except Exception as e:  # collection may not exist yet
                logger.warning("reset_db: %s skipped: %s", coll, e)
                results[coll] = 0

        # Sessions: keep admin only.
        results["user_sessions"] = (await db.user_sessions.delete_many({
            "user_id": {"$nin": admin_user_ids},
        })).deleted_count

        # Users last — keep admins only.
        results["users"] = (await db.users.delete_many({"is_admin": {"$ne": True}})).deleted_count

        logger.info("preview DB reset by %s: %s", admin["email"], results)
        return {
            "ok": True,
            "at": datetime.now(timezone.utc).isoformat(),
            "by": admin["email"],
            "deleted": results,
            "preserved": {
                "admin_user_ids": admin_user_ids,
                "substack_post_count": await db.posts.count_documents({"source": "substack_import"}),
            },
        }

    return router
