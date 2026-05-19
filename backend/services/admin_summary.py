"""Once-daily admin summary email.

Runs at 7:00 AM America/Chicago and sends a compact HTML digest of the
current dashboard state, with week-over-week deltas, to every email in
ADMIN_EMAILS.

Persists yesterday's snapshot in `admin_summary_history` so the next day's
email can show "+12 members vs yesterday" etc.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from services.brevo import send_email, app_url as _brevo_app_url

logger = logging.getLogger(__name__)

ADMIN_EMAILS = [e.strip() for e in (os.environ.get("ADMIN_EMAILS") or "").split(",") if e.strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _delta(curr: int, prev: int) -> str:
    if prev is None:
        return ""
    diff = curr - prev
    if diff == 0:
        return "—"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff} vs yest."


async def _snapshot(db) -> dict:
    """Compute today's snapshot — same shape we'll diff tomorrow against."""
    now = datetime.now(timezone.utc)
    d7 = (now - timedelta(days=7)).isoformat()
    d30 = (now - timedelta(days=30)).isoformat()
    members_total    = await db.users.count_documents({})
    members_approved = await db.users.count_documents({"status": "approved"})
    members_invited  = await db.users.count_documents({"status": "invited"})
    members_pending  = await db.users.count_documents({"status": "pending"})
    members_new_7d   = await db.users.count_documents({"created_at": {"$gte": d7}})

    posts_30d = await db.posts.count_documents({"status": "approved", "release_at": {"$gte": d30}})
    posts_7d  = await db.posts.count_documents({"status": "approved", "release_at": {"$gte": d7}})

    feed_total   = await db.agg_publishers.count_documents({})
    feed_failing = await db.agg_publishers.count_documents({"error_count": {"$gt": 0}})

    invites_pending  = await db.invite_tokens.count_documents({"claimed_at": None, "expires_at": {"$gt": now.isoformat()}})
    invites_claimed_7d = await db.invite_tokens.count_documents({"claimed_at": {"$gte": d7}})

    apps_pending = await db.applications.count_documents({"status": "pending"})

    async def _brief_stat(kind: str) -> dict:
        q = {"kind": f"brief_{kind}", "created_at": {"$gte": d7}}
        sent    = await db.brief_dispatches.count_documents(q)
        opened  = await db.brief_dispatches.count_documents({**q, "first_opened_at": {"$ne": None}})
        clicked = await db.brief_dispatches.count_documents({**q, "first_clicked_at": {"$ne": None}})
        return {"sent": sent, "opened": opened, "clicked": clicked}

    return {
        "captured_at": now.isoformat(),
        "members_total": members_total,
        "members_approved": members_approved,
        "members_invited": members_invited,
        "members_pending": members_pending,
        "members_new_7d": members_new_7d,
        "posts_30d": posts_30d,
        "posts_7d": posts_7d,
        "feed_total": feed_total,
        "feed_failing": feed_failing,
        "invites_pending": invites_pending,
        "invites_claimed_7d": invites_claimed_7d,
        "apps_pending": apps_pending,
        "brief_morning_7d": await _brief_stat("morning"),
        "brief_evening_7d": await _brief_stat("evening"),
    }


def _row(label: str, value, delta: str = "") -> str:
    delta_html = f'<span style="font-family:ui-monospace,monospace; font-size:11px; color:#AD893E; margin-left:8px;">{delta}</span>' if delta else ""
    return (
        f'<tr><td style="padding:8px 12px; border-bottom:1px solid #E8D4A0; font-family:Georgia,serif; font-size:14px; color:#2C2410;">{label}</td>'
        f'<td style="padding:8px 12px; border-bottom:1px solid #E8D4A0; text-align:right; font-family:\'Plus Jakarta Sans\',Arial,sans-serif; font-weight:600; font-size:15px; color:#2C2410;">{value}{delta_html}</td></tr>'
    )


def _render_html(snap: dict, prev: dict | None, app_url: str) -> str:
    p = prev or {}
    rows = []
    rows.append(_row("Total members",           snap["members_total"],      _delta(snap["members_total"], p.get("members_total"))))
    rows.append(_row("• Approved",              snap["members_approved"],   _delta(snap["members_approved"], p.get("members_approved"))))
    rows.append(_row("• Invited (trial)",       snap["members_invited"],    _delta(snap["members_invited"], p.get("members_invited"))))
    rows.append(_row("• Pending app",           snap["members_pending"],    _delta(snap["members_pending"], p.get("members_pending"))))
    rows.append(_row("New signups · 7d",        snap["members_new_7d"],     _delta(snap["members_new_7d"], p.get("members_new_7d"))))
    rows.append(_row("Approved posts · 7d",     snap["posts_7d"],           _delta(snap["posts_7d"], p.get("posts_7d"))))
    rows.append(_row("Approved posts · 30d",    snap["posts_30d"],          _delta(snap["posts_30d"], p.get("posts_30d"))))
    rows.append(_row("Feed publishers",         snap["feed_total"],         _delta(snap["feed_total"], p.get("feed_total"))))
    rows.append(_row("• Failing fetches",       snap["feed_failing"],       _delta(snap["feed_failing"], p.get("feed_failing"))))
    rows.append(_row("Pending applications",    snap["apps_pending"],       _delta(snap["apps_pending"], p.get("apps_pending"))))
    rows.append(_row("Invites pending",         snap["invites_pending"],    _delta(snap["invites_pending"], p.get("invites_pending"))))
    rows.append(_row("Invites claimed · 7d",    snap["invites_claimed_7d"], _delta(snap["invites_claimed_7d"], p.get("invites_claimed_7d"))))

    bm = snap["brief_morning_7d"]
    be = snap["brief_evening_7d"]
    rows.append(_row("Morning Brief · 7d sends", bm["sent"], ""))
    rows.append(_row("• opens / clicks",         f'{bm["opened"]} / {bm["clicked"]}', ""))
    rows.append(_row("Evening Brief · 7d sends", be["sent"], ""))
    rows.append(_row("• opens / clicks",         f'{be["opened"]} / {be["clicked"]}', ""))

    today = datetime.now(timezone.utc).astimezone().strftime("%a %b %-d")
    return f"""
    <div style="font-family:Georgia,serif; color:#2C2410; background:#FDFAF4; padding:24px 0;">
      <div style="max-width:560px; margin:0 auto; background:#FDFAF4;">
        <div style="text-align:center; padding-bottom:16px; border-bottom:2px solid #2C2410;">
          <div style="font-family:'Plus Jakarta Sans',Arial,sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.28em; text-transform:uppercase; font-size:11px;">The Housing News · Operator</div>
          <div style="font-family:'Plus Jakarta Sans',Arial,sans-serif; font-weight:600; color:#2C2410; font-size:24px; margin-top:6px;">Daily Summary</div>
          <div style="font-family:Georgia,serif; font-style:italic; color:#AD893E; font-size:13px; margin-top:4px;">{today} · 7:00 AM CT</div>
        </div>
        <table style="width:100%; border-collapse:collapse; margin-top:8px;">{''.join(rows)}</table>
        <div style="margin-top:24px; text-align:center;">
          <a href="{app_url}/admin" style="display:inline-block; background:#2C2410; color:#FDFAF4; padding:10px 22px; text-decoration:none; font-family:'Plus Jakarta Sans',Arial,sans-serif; font-weight:600; font-size:12px; letter-spacing:0.05em;">Open Admin Dashboard →</a>
        </div>
      </div>
    </div>
    """


async def send_admin_summary(db) -> dict:
    """Compute today's snapshot, fetch yesterday's, render + send to ADMIN_EMAILS,
    then persist today's snapshot for tomorrow's diff."""
    if not ADMIN_EMAILS:
        logger.warning("admin summary skipped: ADMIN_EMAILS not configured")
        return {"sent": 0, "reason": "no_admin_emails"}

    snap = await _snapshot(db)
    prev = await db.admin_summary_history.find_one(
        {}, {"_id": 0}, sort=[("captured_at", -1)],
    )
    app_url = _brevo_app_url()
    html = _render_html(snap, prev, app_url)
    today_label = datetime.now(timezone.utc).astimezone().strftime("%a %b %-d")
    subject = f"Housing News · Operator Summary · {today_label}"

    sent = 0
    for to in ADMIN_EMAILS:
        try:
            send_email(to, "Operator", subject, html,
                       tags=["thehousingnews", "admin_summary"],
                       sender_email=os.environ.get("BRIEF_SENDER_EMAIL", "briefs@thehousingnews.com"),
                       sender_name="The Housing News")
            sent += 1
        except Exception:
            logger.exception("admin summary send failed for %s", to)
    try:
        await db.admin_summary_history.insert_one(dict(snap))
    except Exception:
        logger.exception("admin summary history insert failed")
    # Strip any _id Mongo might have leaked into the snapshot ref above.
    snap.pop("_id", None)
    logger.info("admin summary sent to %s recipients", sent)
    return {"sent": sent, "recipients": ADMIN_EMAILS, "snapshot": snap}
