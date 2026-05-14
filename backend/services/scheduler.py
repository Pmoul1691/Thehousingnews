"""APScheduler jobs: flip pending_release posts/replies to approved, send AM/PM digests, plus a per-minute job for scheduled essays."""
import logging
import uuid
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.release_window import CHICAGO, previous_window, window_kind, window_label
from services.brevo import send_digest_email
from services.essay_dispatch import dispatch_essay_to_followers
from services.admin_digest import send_admin_digest
from services.substack_import import import_substack_feed
from services.rss_ingest import ingest_all_active as agg_ingest_all_active, prune_expired as agg_prune_expired
from routes.prompts import advance_weekly_prompt

logger = logging.getLogger(__name__)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def process_scheduled_essays(db) -> dict:
    """Flip scheduled essays whose release_at <= now to approved and dispatch follower emails.

    Runs every minute. Cheap when there is nothing to do.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    due = await db.posts.find(
        {"kind": "essay", "status": "scheduled", "release_at": {"$lte": now_iso}},
        {"_id": 0},
    ).to_list(200)
    if not due:
        return {"released": 0}
    for essay in due:
        result = await db.posts.update_one(
            {"post_id": essay["post_id"], "status": "scheduled"},
            {"$set": {"status": "approved"}},
        )
        # Only dispatch if we actually flipped this row (avoid double-fire across overlapping runs)
        if result.modified_count == 1:
            try:
                await dispatch_essay_to_followers(db, essay["post_id"])
            except Exception:
                logger.exception("Scheduled essay dispatch failed for %s", essay["post_id"])
    logger.info("Released %s scheduled essays", len(due))
    return {"released": len(due)}


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
    # Fetch the current Subject of the Week (best-effort)
    current_prompt = None
    try:
        current_prompt = await db.prompts.find_one({"status": "active"}, {"_id": 0, "prompt_id": 1, "title": 1, "body": 1})
    except Exception:
        current_prompt = None

    sent = 0
    skipped = 0
    for r in recipients:
        prefs = r.get("digest_prefs") or {"am": True, "pm": True}
        if not prefs.get(kind, True):
            skipped += 1
            continue
        dispatch_id = uuid.uuid4().hex
        try:
            await db.email_dispatches.insert_one({
                "dispatch_id": dispatch_id,
                "kind": f"digest_{kind}",
                "window_label": label,
                "posts_count": len(due_posts),
                "recipient_user_id": r["user_id"],
                "recipient_email": r["email"],
                "first_opened_at": None,
                "first_clicked_at": None,
                "created_at": _to_iso(datetime.now(timezone.utc)),
            })
        except Exception:
            pass
        send_digest_email(r["email"], r.get("name") or "", label, kind, due_posts, picks=picks, dispatch_id=dispatch_id, prompt=current_prompt)
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
    scheduler.add_job(
        process_scheduled_essays,
        trigger="interval",
        minutes=1,
        args=[db],
        id="process_scheduled_essays",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        advance_weekly_prompt,
        trigger="cron",
        day_of_week="mon",
        hour=8,
        minute=30,
        args=[db],
        id="advance_weekly_prompt",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        send_admin_digest,
        trigger="cron",
        day_of_week="sun",
        hour=8,
        minute=0,
        args=[db],
        id="send_admin_digest",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        import_substack_feed,
        trigger="cron",
        hour=7,
        minute=0,
        args=[db],
        id="substack_rss_import",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # Public aggregator: pull every active publisher every 15 minutes.
    scheduler.add_job(
        agg_ingest_all_active,
        trigger="interval",
        minutes=15,
        args=[db],
        id="agg_rss_ingest",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # Daily prune: hide >90d items, hard-delete >120d items.
    scheduler.add_job(
        agg_prune_expired,
        trigger="cron",
        hour=3,
        minute=15,
        args=[db],
        id="agg_prune_expired",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    logger.info("Release scheduler started (8:30 AM and 5:30 PM America/Chicago + per-minute scheduled-essays sweep + 7:00 AM daily Substack import + 15-min aggregator ingest)")
    return scheduler
