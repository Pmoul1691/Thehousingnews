"""Day 3 / 7 / 14 onboarding drip emails.

Pre-staged behind the `ONBOARDING_DRIP_ENABLED` env flag so we can deploy now
and flip on the moment Brevo lifts the account validation hold. While the
flag is unset (default), the daily sweep runs but every send is a no-op.

The sweep:
  1. Finds approved users created exactly 3, 7, or 14 days ago (UTC date).
  2. Looks up the matching template.
  3. Records an idempotency row in `onboarding_dispatches` BEFORE sending so
     a retry or scheduler glitch never double-mails the same member.
  4. Calls `services.brevo.send_email` (which is already preview-URL-guarded).
"""
import logging
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

from services.brevo import send_email, app_url

logger = logging.getLogger(__name__)


DRIP_ENABLED = (os.environ.get("ONBOARDING_DRIP_ENABLED") or "").lower() in (
    "1", "true", "yes", "on"
)

# (day_offset, dispatch_key, subject, body_template)
# Templates use {first_name} and {app_url}. No em/en dashes, first-person
# Pete voice. Single CTA per email so the action is unambiguous.
DRIP_STEPS = [
    (
        3,
        "drip_day_3",
        "How's the first week going?",
        """
        <p>Hi {first_name},</p>
        <p>It's been three days since you joined The Housing News. I built
        this place for the same reason you joined: I wanted one calm room
        for what actually matters in housing, without the noise.</p>
        <p>If you have a minute, the fastest way to see the value is to skim
        today's Daily and read one essay from another member. That's it.
        You'll know in five minutes whether this room is for you.</p>
        <p style="margin-top:24px;">
          <a href="{app_url}/news" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:12px 24px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600;">Open The Daily</a>
        </p>
        <p style="font-family:Georgia, serif; color:#2C2410;">Pete</p>
        """,
    ),
    (
        7,
        "drip_day_7",
        "The essays I'd start with",
        """
        <p>Hi {first_name},</p>
        <p>You've been a member for a week. The thing that surprises most
        new members is how much signal sits inside the member essays. They
        are the part you can't get from any other newsroom: the operator's
        view, in their own words.</p>
        <p>Browse what's been published this month. A handful will probably
        change how you think about something.</p>
        <p style="margin-top:24px;">
          <a href="{app_url}/essays" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:12px 24px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600;">Browse the essays</a>
        </p>
        <p style="font-family:Georgia, serif; color:#2C2410;">Pete</p>
        """,
    ),
    (
        14,
        "drip_day_14",
        "Your turn to write",
        """
        <p>Hi {first_name},</p>
        <p>Two weeks in. The members who get the most out of this network
        are the ones who post at least one essay in their first month.
        Other members read it, follow you, and a conversation starts.</p>
        <p>You don't need a thesis. A 200 word take on what you're seeing
        in your market this week is more valuable than a polished piece
        nobody reads. Posts release together at 8:30 AM and 5:30 PM CT, so
        whatever you write today sits next to the rest of the room.</p>
        <p style="margin-top:24px;">
          <a href="{app_url}/write" style="display:inline-block; background:#AD893E; color:#FDFAF4; padding:12px 24px; text-decoration:none; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600;">Write your first post</a>
        </p>
        <p style="font-family:Georgia, serif; color:#2C2410;">Pete</p>
        """,
    ),
]


def _wrap(body_html: str) -> str:
    """Same cream-+-gold visual frame as the rest of our transactional mail."""
    return f"""
    <div style="background:#FDFAF4; padding:40px 24px; font-family:'Plus Jakarta Sans', Arial, sans-serif; color:#2C2410;">
      <div style="max-width:560px; margin:0 auto; background:#fff; border:1px solid #E8D4A0; padding:36px 32px;">
        <p style="font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin:0 0 24px 0;">The Housing News</p>
        <div style="font-size:15px; line-height:1.6;">{body_html}</div>
        <p style="font-size:11px; color:#988a6a; margin-top:32px;">
          You receive these check-ins because you joined the network. You can
          adjust your email preferences from your profile.
        </p>
      </div>
    </div>
    """


async def _first_name(user: dict) -> str:
    name = (user.get("name") or "").strip()
    if name:
        return name.split()[0]
    return "there"


async def run_drip_sweep(db) -> dict:
    """One pass of the drip. Idempotent. Safe to schedule daily.

    Returns a summary dict for ops logging:
      {ran: ts, candidates: N, sent: N, skipped_already_sent: N, skipped_flag_off: N}
    """
    now = datetime.now(timezone.utc)
    summary = {
        "ran": now.isoformat(),
        "candidates": 0,
        "sent": 0,
        "skipped_already_sent": 0,
        "skipped_flag_off": 0,
        "errors": 0,
        "by_step": {},
    }

    for day_offset, dispatch_key, subject, template in DRIP_STEPS:
        # Approved users whose age in days falls in [day_offset, day_offset+1):
        # i.e., they crossed the day-N anniversary in the past 24h. A rolling
        # window (not midnight-aligned) so a sweep that runs once a day always
        # catches every user exactly once.
        window_end = now - timedelta(days=day_offset)
        window_start = now - timedelta(days=day_offset + 1)
        users = await db.users.find(
            {
                "status": "approved",
                "created_at": {
                    "$gte": window_start.isoformat(),
                    "$lt": window_end.isoformat(),
                },
            },
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(2000)
        summary["by_step"][dispatch_key] = {"candidates": len(users), "sent": 0}

        for u in users:
            summary["candidates"] += 1
            user_id = u.get("user_id")
            email = (u.get("email") or "").strip()
            if not user_id or not email:
                continue

            # Idempotency: insert-first, send-second. The unique index on
            # (user_id, kind) ensures a concurrent run can never double-send.
            try:
                await db.onboarding_dispatches.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "kind": dispatch_key,
                    "email": email,
                    "queued_at": now.isoformat(),
                    "status": "queued",
                })
            except Exception:
                # Duplicate key = already queued/sent for this user. Skip.
                summary["skipped_already_sent"] += 1
                continue

            if not DRIP_ENABLED:
                # Flag off: leave the row in `queued` state so when we flip
                # the flag on, we don't suddenly blast every backfilled user.
                # Operators must manually re-run or delete these rows.
                summary["skipped_flag_off"] += 1
                continue

            first_name = await _first_name(u)
            body = template.format(first_name=first_name, app_url=app_url())
            html = _wrap(body)
            try:
                result = await asyncio.to_thread(
                    send_email,
                    email,
                    u.get("name") or email,
                    subject,
                    html,
                    ["thehousingnews", "onboarding_drip", dispatch_key],
                )
                if result.get("error") or result.get("blocked"):
                    summary["errors"] += 1
                    await db.onboarding_dispatches.update_one(
                        {"user_id": user_id, "kind": dispatch_key},
                        {"$set": {"status": "error", "error": str(result)[:500], "sent_at": now.isoformat()}},
                    )
                else:
                    summary["sent"] += 1
                    summary["by_step"][dispatch_key]["sent"] += 1
                    await db.onboarding_dispatches.update_one(
                        {"user_id": user_id, "kind": dispatch_key},
                        {"$set": {"status": "sent", "sent_at": now.isoformat()}},
                    )
            except Exception as e:
                summary["errors"] += 1
                logger.exception("drip send crashed for %s/%s: %s", user_id, dispatch_key, e)

    logger.info("onboarding drip sweep: %s", summary)
    return summary
