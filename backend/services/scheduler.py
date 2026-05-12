"""APScheduler jobs: flip pending_release posts/replies to approved, send AM/PM digests."""
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.release_window import CHICAGO, previous_window, window_kind, window_label
from services.brevo import send_digest_email

logger = logging.getLogger(__name__)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def release_batch(db) -> dict:
    """Flip all pending_release posts and replies whose release_at <= now to approved.

    Build the digest from exactly the posts flipped in this batch, then email
    approved members.
    """
    now = datetime.now(CHICAGO)
    cutoff_iso = _to_iso(now)

    win = previous_window(now)
    kind = window_kind(win)
    label = window_label(win)

    # 1. Snapshot the rows to flip BEFORE updating (so the digest covers only this batch)
    due_posts = await db.posts.find(
        {"status": "pending_release", "release_at": {"$lte": cutoff_iso}},
        {"_id": 0},
    ).sort("release_at", -1).to_list(500)
    due_post_ids = [p["post_id"] for p in due_posts]

    due_replies = await db.replies.find(
        {"status": "pending_release", "release_at": {"$lte": cutoff_iso}},
        {"_id": 0, "reply_id": 1},
    ).to_list(1000)
    due_reply_ids = [r["reply_id"] for r in due_replies]

    # 2. Flip statuses
    if due_post_ids:
        await db.posts.update_many(
            {"post_id": {"$in": due_post_ids}},
            {"$set": {"status": "approved"}},
        )
    if due_reply_ids:
        await db.replies.update_many(
            {"reply_id": {"$in": due_reply_ids}},
            {"$set": {"status": "approved"}},
        )

    logger.info(
        "Release batch for window %s: %s posts, %s replies released",
        label, len(due_post_ids), len(due_reply_ids),
    )

    if not due_posts:
        return {"window": label, "kind": kind, "posts_released": 0, "replies_released": len(due_reply_ids), "emails_sent": 0}

    # 3. Attach author info on the snapshot
    user_ids = list({p["user_id"] for p in due_posts})
    profiles = await db.profiles.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
    users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
    pmap = {p["user_id"]: p for p in profiles}
    umap = {u["user_id"]: u for u in users}
    for p in due_posts:
        prof = pmap.get(p["user_id"])
        usr = umap.get(p["user_id"], {})
        p["author_name"] = (prof or {}).get("name") or usr.get("name") or "Member"
        p["author_market"] = (prof or {}).get("market") or ""

    # 4. Mail every approved member who opted into this window
    # Also load the most recent Pete picks (last 30 days) for the digest sidebar
    from datetime import timedelta as _td
    picks_cutoff = (datetime.now(timezone.utc) - _td(days=30)).astimezone(timezone.utc).isoformat()
    picks = await db.posts.find(
        {
            "is_pete_pick": True,
            "release_at": {"$lte": cutoff_iso, "$gte": picks_cutoff},
            "status": {"$nin": ["declined", "hidden"]},
        },
        {"_id": 0},
    ).sort("pete_picked_at", -1).to_list(3)
    if picks:
        pick_uids = list({p["user_id"] for p in picks})
        ppmap = {p["user_id"]: p for p in await db.profiles.find({"user_id": {"$in": pick_uids}}, {"_id": 0}).to_list(20)}
        pumap = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": pick_uids}}, {"_id": 0}).to_list(20)}
        for p in picks:
            prf = ppmap.get(p["user_id"]) or {}
            usr = pumap.get(p["user_id"]) or {}
            p["author_name"] = prf.get("name") or usr.get("name") or "Member"
            p["author_market"] = prf.get("market") or ""

    recipients = await db.users.find(
        {"status": "approved", "suspended": {"$ne": True}},
        {"_id": 0},
    ).to_list(2000)
    sent = 0
    skipped = 0
    for r in recipients:
        prefs = r.get("digest_prefs") or {"am": True, "pm": True}
        if not prefs.get(kind, True):
            skipped += 1
            continue
        send_digest_email(r["email"], r.get("name") or "", label, kind, due_posts, picks=picks)
        sent += 1

    logger.info("Digest sent for window %s to %s recipients (%s skipped by prefs)", label, sent, skipped)
    return {
        "window": label,
        "kind": kind,
        "posts_released": len(due_posts),
        "replies_released": len(due_reply_ids),
        "emails_sent": sent,
        "emails_skipped": skipped,
    }


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
