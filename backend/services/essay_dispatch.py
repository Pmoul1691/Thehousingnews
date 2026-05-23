"""Essay dispatch: send a per-essay email to each of the writer's followers."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from services.brevo import send_essay_email, app_url as _brevo_app_url

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def dispatch_essay_to_followers(db, post_id: str) -> dict:
    """Find the essay, its author, the author's followers, and email each follower.

    Idempotent: stores rows in essay_dispatches keyed by (post_id, recipient_user_id)
    so re-running this for the same essay does not double-mail.
    """
    post = await db.posts.find_one({"post_id": post_id, "kind": "essay"}, {"_id": 0})
    if not post:
        logger.warning("dispatch_essay: post not found %s", post_id)
        return {"sent": 0, "skipped": 0}

    writer = await db.users.find_one({"user_id": post["user_id"]}, {"_id": 0})
    writer_profile = await db.profiles.find_one({"user_id": post["user_id"]}, {"_id": 0})
    if not writer:
        return {"sent": 0, "skipped": 0}

    writer_name = (writer_profile or {}).get("name") or writer.get("name") or "A member"

    # Followers of this writer
    follows = await db.follows.find({"followed_id": post["user_id"]}, {"_id": 0}).to_list(5000)
    follower_ids = [f["follower_id"] for f in follows]
    if not follower_ids:
        logger.info("dispatch_essay: no followers for %s", post_id)
        return {"sent": 0, "skipped": 0}

    followers = await db.users.find(
        {"user_id": {"$in": follower_ids}, "status": "approved", "suspended": {"$ne": True}},
        {"_id": 0},
    ).to_list(5000)

    app_url = _brevo_app_url()
    sent = 0
    skipped = 0
    for f in followers:
        # Insert the dispatch row FIRST (idempotency guard). If a duplicate exists,
        # the unique index throws and we skip the send entirely.
        dispatch_id = uuid.uuid4().hex
        try:
            await db.essay_dispatches.insert_one({
                "post_id": post_id,
                "writer_id": post["user_id"],
                "recipient_user_id": f["user_id"],
                "recipient_email": f["email"],
                "dispatch_id": dispatch_id,
                "result_status": None,
                "skipped": False,
                "created_at": _now_iso(),
            })
        except Exception:
            # Duplicate key (already dispatched) or other write error
            skipped += 1
            continue

        # Mirror into a unified email_dispatches collection so /api/track/* can update first_opened_at
        try:
            await db.email_dispatches.insert_one({
                "dispatch_id": dispatch_id,
                "kind": "essay",
                "post_id": post_id,
                "writer_id": post["user_id"],
                "recipient_user_id": f["user_id"],
                "recipient_email": f["email"],
                "first_opened_at": None,
                "first_clicked_at": None,
                "created_at": _now_iso(),
            })
        except Exception:
            pass

        result = await asyncio.to_thread(
            send_essay_email,
            f["email"],
            f.get("name") or "",
            writer_name,
            post.get("title") or "(untitled)",
            post.get("subtitle") or "",
            post.get("text") or "",
            f"{app_url}/essays/{post_id}" if app_url else f"/essays/{post_id}",
            dispatch_id,
        )
        await db.essay_dispatches.update_one(
            {"post_id": post_id, "recipient_user_id": f["user_id"]},
            {"$set": {
                "result_status": result.get("status") if isinstance(result, dict) else None,
                "skipped": bool(result.get("skipped")) if isinstance(result, dict) else False,
                "sent_at": _now_iso(),
            }},
        )
        sent += 1

    logger.info("Essay %s dispatched to %s followers (%s skipped via idempotency)", post_id, sent, skipped)
    return {"sent": sent, "skipped": skipped, "total_followers": len(followers)}
