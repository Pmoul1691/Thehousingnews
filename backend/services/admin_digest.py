"""Weekly admin engagement digest.

Sends one email per admin user every Sunday 8am Chicago time summarizing the
last 7 days: signups, applications, active members, posts, essays, top
replies, Pete picks, top suggestion votes, and email open/click rates.
"""
import logging
import uuid
import os
from datetime import datetime, timezone, timedelta

from services.brevo import send_email, SENDER_EMAIL
from services.release_window import CHICAGO

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_count(n: int) -> str:
    return f"{n:,}"


async def build_admin_digest(db) -> dict:
    """Aggregate the past-7-day metrics. Returns a dict ready to template into HTML."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=7)).isoformat()

    # Applications
    apps = await db.applications.find({"created_at": {"$gte": cutoff}}, {"_id": 0}).to_list(500)
    apps_pending = sum(1 for a in apps if a.get("status") == "pending")
    apps_approved = sum(1 for a in apps if a.get("status") == "approved")
    apps_declined = sum(1 for a in apps if a.get("status") == "declined")

    # Members
    total_approved = await db.users.count_documents({"status": "approved"})
    active_7d = await db.users.count_documents({"last_login_at": {"$gte": cutoff}})

    # Posts + essays
    posts_7d = await db.posts.find(
        {"release_at": {"$gte": cutoff, "$lte": now.isoformat()}, "status": {"$nin": ["declined", "hidden"]}},
        {"_id": 0},
    ).to_list(2000)
    short_count = sum(1 for p in posts_7d if (p.get("kind") or "post") == "post")
    essay_count = sum(1 for p in posts_7d if p.get("kind") == "essay")

    # Top 3 posts by reply count
    top_replies = []
    if posts_7d:
        post_ids = [p["post_id"] for p in posts_7d]
        agg = await db.replies.aggregate([
            {"$match": {"post_id": {"$in": post_ids}, "status": {"$nin": ["declined", "hidden"]}}},
            {"$group": {"_id": "$post_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 3},
        ]).to_list(3)
        rmap = {r["_id"]: r["n"] for r in agg}
        for p in posts_7d:
            p["reply_count"] = rmap.get(p["post_id"], 0)
        top_replies = sorted([p for p in posts_7d if p.get("reply_count", 0) > 0],
                             key=lambda p: -p.get("reply_count", 0))[:3]

    # Top 3 essays this week (by reply count, then recency)
    top_essays = []
    essay_posts = [p for p in posts_7d if p.get("kind") == "essay"]
    if essay_posts:
        essay_ids = [p["post_id"] for p in essay_posts]
        agg_e = await db.replies.aggregate([
            {"$match": {"post_id": {"$in": essay_ids}, "status": {"$nin": ["declined", "hidden"]}}},
            {"$group": {"_id": "$post_id", "n": {"$sum": 1}}},
        ]).to_list(len(essay_ids))
        emap = {r["_id"]: r["n"] for r in agg_e}
        for p in essay_posts:
            p["reply_count"] = emap.get(p["post_id"], 0)
        top_essays = sorted(
            essay_posts,
            key=lambda p: (-p.get("reply_count", 0), p.get("release_at") or ""),
            reverse=False,
        )
        # Secondary sort: among ties on reply_count, prefer more-recent release_at
        top_essays.sort(key=lambda p: p.get("release_at") or "", reverse=True)
        top_essays.sort(key=lambda p: -p.get("reply_count", 0))
        top_essays = top_essays[:3]

    # Biggest mover: the member whose released-post count grew the most vs the
    # prior 7-day window. Quiet, fun signal.
    prev_cutoff = (now - timedelta(days=14)).isoformat()
    biggest_mover = None
    try:
        this_week = await db.posts.aggregate([
            {"$match": {
                "release_at": {"$gte": cutoff, "$lte": now.isoformat()},
                "status": {"$nin": ["declined", "hidden"]},
            }},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]).to_list(2000)
        prev_week = await db.posts.aggregate([
            {"$match": {
                "release_at": {"$gte": prev_cutoff, "$lt": cutoff},
                "status": {"$nin": ["declined", "hidden"]},
            }},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]).to_list(2000)
        prev_map = {r["_id"]: r["n"] for r in prev_week}
        deltas = [
            (r["_id"], r["n"] - prev_map.get(r["_id"], 0), r["n"])
            for r in this_week
        ]
        deltas.sort(key=lambda x: -x[1])
        if deltas and deltas[0][1] > 0:
            uid, delta, total = deltas[0]
            prof = await db.profiles.find_one({"user_id": uid}, {"_id": 0, "name": 1, "market": 1}) or {}
            biggest_mover = {
                "user_id": uid,
                "name": prof.get("name") or "Member",
                "market": prof.get("market"),
                "delta": delta,
                "total": total,
            }
    except Exception as _e:
        logger.warning("biggest mover calc failed: %s", _e)

    # Pete picks count
    picks_7d = await db.posts.count_documents({
        "is_pete_pick": True,
        "release_at": {"$gte": cutoff},
    })

    # Top suggestion (most recent open)
    suggestions = await db.prompt_suggestions.find(
        {"status": "open"}, {"_id": 0},
    ).sort("created_at", -1).limit(3).to_list(3)

    # Email engagement (delegate to the aggregation already proven in analytics)
    dispatches = await db.email_dispatches.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": None,
            "sent": {"$sum": 1},
            "opened": {"$sum": {"$cond": [{"$ifNull": ["$first_opened_at", False]}, 1, 0]}},
            "clicked": {"$sum": {"$cond": [{"$ifNull": ["$first_clicked_at", False]}, 1, 0]}},
        }},
    ]).to_list(1)
    eng = dispatches[0] if dispatches else {"sent": 0, "opened": 0, "clicked": 0}
    open_rate = round((eng["opened"] / eng["sent"]) * 100, 1) if eng["sent"] else 0
    click_rate = round((eng["clicked"] / eng["sent"]) * 100, 1) if eng["sent"] else 0

    return {
        "apps": {"pending": apps_pending, "approved": apps_approved, "declined": apps_declined, "total": len(apps)},
        "members": {"total_approved": total_approved, "active_7d": active_7d},
        "posts": {"short": short_count, "essays": essay_count, "top_replies": top_replies, "top_essays": top_essays},
        "picks_7d": picks_7d,
        "biggest_mover": biggest_mover,
        "suggestions": suggestions,
        "email": {"sent": eng["sent"], "opened": eng["opened"], "clicked": eng["clicked"], "open_rate": open_rate, "click_rate": click_rate},
        "window": {"from": cutoff, "to": now.isoformat()},
    }


def render_admin_digest_html(data: dict) -> str:
    base = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")
    apps = data["apps"]
    mem = data["members"]
    po = data["posts"]
    em = data["email"]

    def _row(label, value, hint=""):
        return f"""
        <tr>
          <td style="padding:8px 0; font-family:Georgia, serif; color:#5C4A1F; font-size:14px;">{label}</td>
          <td style="padding:8px 0; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#2C2410; font-size:16px; text-align:right;">{value}{f'<span style="color:#5C4A1F; font-weight:400; font-size:12px;"> {hint}</span>' if hint else ''}</td>
        </tr>
        """

    top_replies_html = ""
    if po["top_replies"]:
        items = ""
        for p in po["top_replies"]:
            title = p.get("title") or (p.get("text", "")[:80] + ("..." if len(p.get("text", "")) > 80 else ""))
            url = f"{base}/essays/{p['post_id']}" if p.get("kind") == "essay" and base else "#"
            items += f'<li style="margin:6px 0; font-family:Georgia, serif; color:#2C2410;"><a href="{url}" style="color:#2C2410; text-decoration:none;">{title}</a> <span style="color:#5C4A1F; font-size:12px;">. {p["reply_count"]} replies</span></li>'
        top_replies_html = f"""
        <div style="margin-top:16px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Top conversations</div>
          <ul style="margin:0; padding-left:18px;">{items}</ul>
        </div>
        """

    top_essays_html = ""
    if po.get("top_essays"):
        items = ""
        for p in po["top_essays"]:
            title = p.get("title") or (p.get("text", "")[:80] + ("..." if len(p.get("text", "")) > 80 else "")) or "Untitled essay"
            url = f"{base}/essays/{p['post_id']}" if base else "#"
            replies_note = f' <span style="color:#5C4A1F; font-size:12px;">. {p.get("reply_count", 0)} replies</span>' if p.get("reply_count") else ""
            items += f'<li style="margin:6px 0; font-family:Georgia, serif; color:#2C2410;"><a href="{url}" style="color:#2C2410; text-decoration:none;">{title}</a>{replies_note}</li>'
        top_essays_html = f"""
        <div style="margin-top:16px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Top essays this week</div>
          <ul style="margin:0; padding-left:18px;">{items}</ul>
        </div>
        """

    mover = data.get("biggest_mover")
    mover_html = ""
    if mover:
        market_html = f' <span style="color:#5C4A1F; font-size:12px;">{mover["market"]}</span>' if mover.get("market") else ""
        mover_html = f"""
        <div style="margin-top:20px; padding:14px 18px; border-left:3px solid #AD893E; background:#FBF6E8;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Biggest mover</div>
          <div style="font-family:Georgia, serif; color:#2C2410; font-size:15px;">
            <strong style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600;">{mover["name"]}</strong>{market_html}
            <div style="margin-top:4px; color:#5C4A1F; font-size:13px;">+{mover["delta"]} more posts than the prior week ({mover["total"]} total).</div>
          </div>
        </div>
        """

    sugg_html = ""
    if data["suggestions"]:
        items = ""
        for s in data["suggestions"][:3]:
            items += f'<li style="margin:6px 0; font-family:Georgia, serif; color:#2C2410;"><span style="color:#5C4A1F; font-size:12px;">{s.get("user_name", "Member")}:</span> {s["text"]}</li>'
        sugg_html = f"""
        <div style="margin-top:20px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Member subject suggestions</div>
          <ul style="margin:0; padding-left:18px;">{items}</ul>
        </div>
        """

    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px 0;">
      <div style="max-width:600px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:32px;">
        {('<div style="text-align:center; margin-bottom:16px;"><img src="' + base + '/brand/logo-mark.png" alt="The Housing News" width="64" height="64" style="display:inline-block; width:64px; height:64px; max-width:64px;" /></div>') if base else ''}
        <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.12em; text-transform:uppercase; font-size:11px; margin-bottom:8px; text-align:center;">Editors' Sunday brief</div>
        <h1 style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:24px; color:#2C2410; margin:0 0 24px 0; text-align:center;">The last seven days, in numbers.</h1>

        <table cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse; border-top:1px solid #E8D4A0;">
          <tr><td colspan="2" style="padding:14px 0 6px 0;"><div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E;">Applications</div></td></tr>
          {_row("Pending review", _fmt_count(apps["pending"]))}
          {_row("Approved this week", _fmt_count(apps["approved"]))}
          {_row("Declined this week", _fmt_count(apps["declined"]))}
        </table>

        <table cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse; margin-top:24px; border-top:1px solid #E8D4A0;">
          <tr><td colspan="2" style="padding:14px 0 6px 0;"><div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E;">Members</div></td></tr>
          {_row("Approved total", _fmt_count(mem["total_approved"]))}
          {_row("Active in past 7 days", _fmt_count(mem["active_7d"]))}
        </table>

        <table cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse; margin-top:24px; border-top:1px solid #E8D4A0;">
          <tr><td colspan="2" style="padding:14px 0 6px 0;"><div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E;">Writing</div></td></tr>
          {_row("Short posts released", _fmt_count(po["short"]))}
          {_row("Essays released", _fmt_count(po["essays"]))}
          {_row("Staff picks added", _fmt_count(data["picks_7d"]))}
        </table>
        {top_essays_html}
        {top_replies_html}
        {mover_html}

        <table cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse; margin-top:24px; border-top:1px solid #E8D4A0;">
          <tr><td colspan="2" style="padding:14px 0 6px 0;"><div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E;">Email engagement</div></td></tr>
          {_row("Emails sent", _fmt_count(em["sent"]))}
          {_row("Opens", _fmt_count(em["opened"]), f"{em['open_rate']}%")}
          {_row("Clicks", _fmt_count(em["clicked"]), f"{em['click_rate']}%")}
        </table>

        {sugg_html}

        <p style="font-family:Georgia, serif; color:#5C4A1F; font-size:13px; margin-top:32px;">
          Take what is useful. Skip the rest.<br/>
          <a href="{base}/admin" style="color:#AD893E;">Open the admin dashboard →</a>
        </p>
      </div>
    </div>
    """


async def send_admin_digest(db) -> dict:
    """Aggregate + send the Sunday digest to every admin user."""
    data = await build_admin_digest(db)
    html = render_admin_digest_html(data)
    admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1, "user_id": 1}).to_list(50)
    # Subject: stamp the week so admins can skim their inbox at a glance.
    try:
        from datetime import datetime as _dt
        wk_end = _dt.fromisoformat(data["window"]["to"].replace("Z", "+00:00"))
        week_label = wk_end.strftime("%b %-d")
    except Exception:
        week_label = "this week"
    apps = data.get("apps") or {}
    pending = apps.get("pending") or 0
    if pending > 0:
        subject = f"Sunday brief - {week_label} - {pending} application{'s' if pending != 1 else ''} pending"
    else:
        subject = f"Sunday brief - {week_label}"

    sent = 0
    for a in admins:
        if not a.get("email"):
            continue
        dispatch_id = uuid.uuid4().hex
        try:
            await db.email_dispatches.insert_one({
                "dispatch_id": dispatch_id,
                "kind": "admin_digest",
                "window_label": data["window"]["from"][:10],
                "recipient_user_id": a["user_id"],
                "recipient_email": a["email"],
                "first_opened_at": None,
                "first_clicked_at": None,
                "created_at": _now_iso(),
            })
        except Exception:
            pass
        send_email(
            to_email=a["email"],
            to_name=a.get("name") or "Admin",
            subject=subject,
            html=html,
            tags=["ultradian_network", "admin_digest"],
            dispatch_id=dispatch_id,
        )
        sent += 1
    return {"admins_emailed": sent, "data": data}
