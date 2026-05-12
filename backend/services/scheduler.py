"""APScheduler jobs: flip pending_release posts/replies to approved, send AM/PM digests."""
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.release_window import CHICAGO, previous_window, window_kind, window_label
from services.brevo import send_digest_email

logger = logging.getLogger(__name__)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def release_batch(db) -> dict:
    """Flip all pending_release posts and replies whose release_at <= now to approved.

    Then build the AM/PM digest and email approved members.
    Returns a summary dict (used in tests).
    """
    now = datetime.now(CHICAGO)
    cutoff_iso = _to_iso(now)

    # Find the window we just crossed. previous_window returns the most recent < now.
    win = previous_window(now)
    kind = window_kind(win)
    label = window_label(win)

    # Flip posts
    posts_res = await db.posts.update_many(
        {"status": "pending_release", "release_at": {"$lte": cutoff_iso}},
        {"$set": {"status": "approved"}},
    )
    # Flip replies
    replies_res = await db.replies.update_many(
        {"status": "pending_release", "release_at": {"$lte": cutoff_iso}},
        {"$set": {"status": "approved"}},
    )

    logger.info(
        "Release batch ran for window %s: %s posts, %s replies flipped",
        label, posts_res.modified_count, replies_res.modified_count,
    )

    # Build digest of posts released *for this window*. Use a tight ISO range:
    # posts whose release_at is between previous_window-12h and now.
    twelve_hours_ago = win - timedelta(hours=12)
    posts = await db.posts.find(
        {
            "status": "approved",
            "release_at": {"$gte": _to_iso(twelve_hours_ago), "$lte": cutoff_iso},
        },
        {"_id": 0},
    ).sort("release_at", -1).to_list(200)

    if not posts:
        logger.info("No posts to digest for window %s", label)
        return {"window": label, "kind": kind, "posts_released": 0, "emails_sent": 0}

    # Attach author info
    user_ids = list({p["user_id"] for p in posts})
    profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
    users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
    pmap = {p["user_id"]: p for p in profiles}
    umap = {u["user_id"]: u for u in users}
    for p in posts:
        prof = pmap.get(p["user_id"])
        usr = umap.get(p["user_id"], {})
        p["author_name"] = (prof or {}).get("name") or usr.get("name") or "Member"
        p["author_market"] = (prof or {}).get("market") or ""

    # Recipients: all approved members
    recipients = await db.users.find({"status": "approved"}, {"_id": 0}).to_list(2000)

    sent = 0
    for r in recipients:
        send_digest_email(r["email"], r.get("name") or "", label, kind, posts)
        sent += 1

    logger.info("Digest sent for window %s to %s recipients", label, sent)
    return {"window": label, "kind": kind, "posts_released": len(posts), "emails_sent": sent}


def start_scheduler(db) -> AsyncIOScheduler:
    """Configure the two daily cron jobs and start the scheduler."""
    scheduler = AsyncIOScheduler(timezone=CHICAGO)
    scheduler.add_job(
        release_batch,
        trigger="cron",
        hour=8,
        minute=30,
        args=[db],
        id="release_window_am",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        release_batch,
        trigger="cron",
        hour=17,
        minute=30,
        args=[db],
        id="release_window_pm",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    logger.info("Release scheduler started (8:30 AM and 5:30 PM America/Chicago)")
    return scheduler
