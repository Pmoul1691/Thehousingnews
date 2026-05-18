"""One-time public-launch announcement broadcast.

Sends a single styled magazine-aesthetic email to every approved member
announcing that The Housing News is officially live, with deep links to
The Daily (news river), the Member Directory, the Composer, and the
current Subject of the Week.

Idempotency: a row is written to `email_dispatches` with kind
"launch_broadcast" for every recipient, so re-firing the endpoint will
skip anyone who already received it (unless the caller passes force=True).
"""
import logging
import os
import uuid
from datetime import datetime, timezone

from services.brevo import send_email
from services.release_window import next_window

logger = logging.getLogger(__name__)

DEFAULT_SUBJECT = "We are live. Welcome to The Housing News."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    return os.environ.get("APP_PUBLIC_URL", "").rstrip("/") or "https://thehousingnews.com"


def _greeting_name(name: str | None) -> str:
    if not name:
        return "there"
    first = (name or "").strip().split(" ")[0]
    return first or "there"


async def build_launch_payload(db) -> dict:
    """Collect a tiny snapshot used to personalize the launch email."""
    # Active Subject of the Week, if any
    prompt = await db.prompts.find_one(
        {"status": "active"},
        {"_id": 0, "prompt_id": 1, "title": 1, "subtitle": 1},
        sort=[("created_at", -1)],
    )
    # Member counts (kept for the preview UI / future analytics)
    total_members = await db.users.count_documents({"status": "approved", "suspended": {"$ne": True}})
    publishers = await db.agg_publishers.count_documents({"active": True})
    try:
        from services.podcasts_directory import PODCASTS
        podcasts = len(PODCASTS)
    except Exception:
        podcasts = 10
    return {
        "prompt": prompt,
        "total_members": total_members,
        "publishers": publishers,
        "podcasts": podcasts,
        "next_window_iso": next_window().isoformat(),
    }


def render_launch_html(member_name: str, payload: dict) -> str:
    base = _base_url()
    greeting = _greeting_name(member_name)
    logo_block = ""
    prompt = payload.get("prompt") or {}
    prompt_block = ""
    if prompt.get("title"):
        prompt_block = f"""
        <div style="margin-top:28px; padding:18px 20px; border-left:3px solid #AD893E; background:#FBF6E8;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:6px;">Subject of the week</div>
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:18px; color:#2C2410;">{prompt['title']}</div>
          {f'<div style="font-family:Georgia, serif; font-style:italic; color:#5C4A1F; font-size:14px; margin-top:4px;">{prompt.get("subtitle", "")}</div>' if prompt.get("subtitle") else ""}
          <a href="{base}/prompts/{prompt.get('prompt_id', '')}" style="display:inline-block; margin-top:10px; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.14em; text-transform:uppercase; color:#AD893E; text-decoration:none;">Write a response &rarr;</a>
        </div>
        """

    pub = payload.get("publishers") or 0
    pod = payload.get("podcasts") or 0

    return f"""
    <div style="font-family: Georgia, serif; color:#2C2410; background:#FDFAF4; padding:32px 0; margin:0;">
      <div style="max-width:600px; margin:0 auto; background:#FDFAF4; border:1px solid #E8D4A0; padding:40px;">

        <div style="text-align:center; margin-bottom:28px;">
          {logo_block}
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; color:#AD893E; letter-spacing:0.22em; text-transform:uppercase; font-size:11px;">The Housing News</div>
          <div style="font-family:Georgia, serif; font-style:italic; color:#5C4A1F; font-size:13px; margin-top:6px;">A daily magazine for the real estate industry.</div>
        </div>

        <h1 style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:30px; line-height:1.2; color:#2C2410; margin:0 0 16px 0;">We are live.</h1>

        <p style="font-family:Georgia, serif; font-size:16px; line-height:1.6; color:#2C2410; margin:0 0 14px 0;">
          {greeting},
        </p>
        <p style="font-family:Georgia, serif; font-size:16px; line-height:1.6; color:#2C2410; margin:0 0 14px 0;">
          The doors are open. As one of the first approved members, you helped shape what this is — a calmer, slower, members-only magazine for the people who actually close deals.
        </p>
        <p style="font-family:Georgia, serif; font-size:16px; line-height:1.6; color:#2C2410; margin:0 0 28px 0;">
          Here is the shortest possible tour.
        </p>

        <!-- The Daily -->
        <div style="border-top:1px solid #E8D4A0; padding-top:20px; margin-bottom:24px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:4px;">Read</div>
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:18px; color:#2C2410;">The Daily</div>
          <div style="font-family:Georgia, serif; font-size:14px; color:#5C4A1F; margin:6px 0 12px 0; line-height:1.55;">
            What the housing industry is reading today. {pub} publishers and {pod} podcasts, refreshed every fifteen minutes.
          </div>
          <a href="{base}/news" style="display:inline-block; background:#AD893E; color:#FDFAF4; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px; padding:10px 18px; border-radius:2px; text-decoration:none;">Open The Daily &rarr;</a>
        </div>

        <!-- Composer -->
        <div style="border-top:1px solid #E8D4A0; padding-top:20px; margin-bottom:24px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:4px;">Write</div>
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:18px; color:#2C2410;">Open the desk</div>
          <div style="font-family:Georgia, serif; font-size:14px; color:#5C4A1F; margin:6px 0 12px 0; line-height:1.55;">
            Short posts release twice a day at 8:30am and 5:30pm Chicago time. Essays publish instantly to your followers. Both are batched, calm, and visible to the network.
          </div>
          <a href="{base}/write" style="display:inline-block; background:#AD893E; color:#FDFAF4; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px; padding:10px 18px; border-radius:2px; text-decoration:none;">Open the desk &rarr;</a>
        </div>

        <!-- Directory -->
        <div style="border-top:1px solid #E8D4A0; padding-top:20px; margin-bottom:24px;">
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#AD893E; margin-bottom:4px;">Find</div>
          <div style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:18px; color:#2C2410;">The network</div>
          <div style="font-family:Georgia, serif; font-size:14px; color:#5C4A1F; margin:6px 0 12px 0; line-height:1.55;">
            See who else made it through the door. Career details and recent essays are right on each profile.
          </div>
          <a href="{base}/members" style="display:inline-block; background:#AD893E; color:#FDFAF4; font-family:'Plus Jakarta Sans', Arial, sans-serif; font-weight:600; font-size:13px; padding:10px 18px; border-radius:2px; text-decoration:none;">Open the directory &rarr;</a>
        </div>

        {prompt_block}

        <p style="font-family:Georgia, serif; font-size:15px; line-height:1.6; color:#2C2410; margin:32px 0 0 0;">
          Take what is useful. Skip the rest.
        </p>
        <p style="font-family:Georgia, serif; font-size:15px; line-height:1.6; color:#2C2410; margin:6px 0 0 0;">
          &mdash; The Editors
        </p>

        <p style="font-family:'Plus Jakarta Sans', Arial, sans-serif; font-size:11px; color:#9A8654; margin-top:36px; padding-top:16px; border-top:1px solid #E8D4A0; text-align:center; letter-spacing:0.05em;">
          You are receiving this because you are an approved member of The Housing News.<br/>
          <a href="{base}/settings" style="color:#AD893E; text-decoration:none;">Manage your email preferences &rarr;</a>
        </p>
      </div>
    </div>
    """


async def send_launch_broadcast(db, force: bool = False, recipient_email: str | None = None) -> dict:
    """Send the launch announcement.

    - If `recipient_email` is set, sends a single TEST copy to that address
      (no dispatch row written, no idempotency check).
    - Otherwise, fans out to every approved + non-suspended member who
      hasn't already received one (unless `force=True`).
    """
    payload = await build_launch_payload(db)

    # TEST mode: single email to caller's chosen address.
    if recipient_email:
        html = render_launch_html("there", payload)
        result = send_email(
            to_email=recipient_email,
            to_name="Test recipient",
            subject=f"[TEST] {DEFAULT_SUBJECT}",
            html=html,
            tags=["thehousingnews", "launch_broadcast", "test"],
        )
        return {"mode": "test", "to": recipient_email, "brevo_result": result}

    # Real broadcast.
    members = await db.users.find(
        {"status": "approved", "suspended": {"$ne": True}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(5000)

    sent = 0
    skipped = 0
    errors: list[dict] = []

    for m in members:
        if not m.get("email"):
            skipped += 1
            continue

        # Idempotency: skip if already received unless force=True
        if not force:
            existing = await db.email_dispatches.find_one({
                "kind": "launch_broadcast",
                "recipient_user_id": m["user_id"],
            })
            if existing:
                skipped += 1
                continue

        dispatch_id = uuid.uuid4().hex
        try:
            await db.email_dispatches.insert_one({
                "dispatch_id": dispatch_id,
                "kind": "launch_broadcast",
                "recipient_user_id": m["user_id"],
                "recipient_email": m["email"],
                "first_opened_at": None,
                "first_clicked_at": None,
                "created_at": _now_iso(),
            })
        except Exception:
            logger.exception("Could not record dispatch row for %s", m["email"])

        html = render_launch_html(m.get("name") or "there", payload)
        result = send_email(
            to_email=m["email"],
            to_name=m.get("name") or "Member",
            subject=DEFAULT_SUBJECT,
            html=html,
            tags=["thehousingnews", "launch_broadcast"],
            dispatch_id=dispatch_id,
        )
        if isinstance(result, dict) and (result.get("error") or result.get("status", 0) >= 400):
            errors.append({"email": m["email"], "error": result})
        else:
            sent += 1

    return {
        "mode": "broadcast",
        "force": force,
        "members_total": len(members),
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
    }
