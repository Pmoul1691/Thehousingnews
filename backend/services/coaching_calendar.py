"""Getting the prep notes into the calendar.

Three delivery paths, because no single one covers every case:

  1. ICS subscription  — `/api/coaching/calendar.ics?token=…`. Zero setup:
     paste the URL into Google Calendar's "From URL". Every coaching session
     shows up with the full agenda in the event description. The catch is
     Google's own refresh schedule for external feeds, which can run hours
     behind — fine for the standing agenda, too slow for a same-day edit.

  2. Webhook push      — set COACHING_CALENDAR_WEBHOOK_URL to a Zapier/Make
     hook that writes the description onto the *real* Google Calendar event.
     This is the one that updates an existing invite in place, in seconds.
     The payload carries `calendar_event_id` so the automation can target the
     exact event, and the merged description so it can write it verbatim.

  3. Copy block        — the same text, exposed on the API and behind a copy
     button in the UI, for when a human just wants to paste it.

All three render the identical block from `coaching_core.render_agenda_text`,
wrapped in markers so re-syncing replaces the previous block instead of
stacking a second copy under it.
"""
import logging
import os
import re

import requests

from services.coaching_core import (
    build_ics,
    iso,
    now_utc,
    render_agenda_text,
)

logger = logging.getLogger(__name__)

NOTE_START = "———— COACHING PREP (auto-generated) ————"
NOTE_END = "———— end coaching prep ————"

_BLOCK_RE = re.compile(
    re.escape(NOTE_START) + r".*?" + re.escape(NOTE_END),
    re.DOTALL,
)

def webhook_configured() -> bool:
    return bool(os.environ.get("COACHING_CALENDAR_WEBHOOK_URL", ""))


# ------------------------------------------------------------- note blocks

def note_block(agenda: dict) -> str:
    """The marker-wrapped prep block written into an event description."""
    return f"{NOTE_START}\n{render_agenda_text(agenda).rstrip()}\n{NOTE_END}"


def merge_description(existing: str, block: str) -> str:
    """Splice the prep block into whatever description the event already has.

    Idempotent by construction: if a previous block is present it is replaced
    in place, so syncing the same meeting nightly for a month leaves exactly
    one block — and never disturbs the Zoom link or the notes a human typed
    above it.
    """
    current = existing or ""
    if _BLOCK_RE.search(current):
        return _BLOCK_RE.sub(lambda _m: block, current, count=1)
    if not current.strip():
        return block
    return current.rstrip() + "\n\n" + block


def strip_block(existing: str) -> str:
    """Remove the generated block, leaving the human-authored description."""
    return _BLOCK_RE.sub("", existing or "").strip()


# ---------------------------------------------------------------- webhook

def push_to_calendar(payload: dict) -> dict:
    """POST one meeting's agenda to the configured calendar automation.

    Synchronous `requests` to match the rest of the service layer; async
    callers wrap this in `asyncio.to_thread`.
    """
    url = os.environ.get("COACHING_CALENDAR_WEBHOOK_URL", "")
    if not url:
        return {"skipped": True, "reason": "COACHING_CALENDAR_WEBHOOK_URL not set"}
    headers = {"Content-Type": "application/json"}
    secret = os.environ.get("COACHING_CALENDAR_WEBHOOK_SECRET", "")
    if secret:
        headers["X-Coaching-Secret"] = secret
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code >= 400:
            logger.error("coaching calendar webhook failed %s %s", r.status_code, r.text[:300])
            return {"error": r.text[:300], "status": r.status_code}
        return {"ok": True, "status": r.status_code}
    except Exception as e:
        logger.exception("coaching calendar webhook exception")
        return {"error": str(e)}


def webhook_payload(*, client: dict, meeting: dict, agenda: dict) -> dict:
    """Everything a Zap needs to write the note onto the real event."""
    block = note_block(agenda)
    return {
        "event": "coaching.agenda.sync",
        "client": {
            "client_id": client.get("client_id"),
            "name": client.get("name"),
            "email": client.get("email"),
        },
        "meeting": {
            "meeting_id": meeting.get("meeting_id"),
            "calendar_event_id": meeting.get("calendar_event_id") or "",
            "calendar_id": meeting.get("calendar_id") or "",
            "title": meeting.get("title") or f"Coaching — {client.get('name')}",
            "starts_at": meeting.get("starts_at"),
            "ends_at": meeting.get("ends_at"),
            "location": meeting.get("location") or "",
        },
        "note_block": block,
        "description": merge_description(meeting.get("calendar_description") or "", block),
        "agenda": {
            "trajectory": agenda.get("trajectory"),
            "counts": agenda.get("counts"),
            "checklist": agenda.get("checklist"),
            "commitments_review": agenda.get("commitments_review"),
        },
        "generated_at": iso(now_utc()),
    }


# ------------------------------------------------------------------ syncing

async def sync_meeting(db, meeting: dict, client: dict, agenda: dict, *, push: bool = True) -> dict:
    """Store the rendered note on the meeting and (optionally) push it out.

    The note is always persisted even when no webhook is configured — the ICS
    feed and the copy button both read it from there, so the calendar surface
    works out of the box and the webhook is a pure upgrade.
    """
    import asyncio

    block = note_block(agenda)
    now = now_utc()
    update = {
        "agenda": agenda,
        "note_block": block,
        "note_generated_at": iso(now),
    }

    result: dict = {"pushed": False}
    if push and webhook_configured():
        payload = webhook_payload(client=client, meeting=meeting, agenda=agenda)
        result = await asyncio.to_thread(push_to_calendar, payload)
        if result.get("ok"):
            update["calendar_synced_at"] = iso(now)
            update["calendar_description"] = payload["description"]
            result["pushed"] = True

    await db.coaching_meetings.update_one(
        {"meeting_id": meeting.get("meeting_id")}, {"$set": update}
    )
    return {"meeting_id": meeting.get("meeting_id"), "note_bytes": len(block), **result}


async def sync_upcoming(db, *, horizon_days: int = 14) -> dict:
    """Scheduler job: refresh the calendar note on every meeting inside the
    horizon so the agenda a coach opens is never stale by more than a day."""
    from datetime import timedelta

    from services.coaching_store import (
        get_client,
        meetings_starting_between,
        snapshot_or_refresh,
    )

    now = now_utc()
    meetings = await meetings_starting_between(db, now, now + timedelta(days=horizon_days))
    synced, failed = 0, 0
    for meeting in meetings:
        try:
            client = await get_client(db, meeting["client_id"])
            if not client:
                continue
            snap = await snapshot_or_refresh(db, meeting["client_id"])
            if not snap:
                continue
            agenda = dict(snap["agenda"])
            # The snapshot's agenda targets the client's *next* meeting; when
            # syncing a later one, restamp the header so the note in that
            # event shows that event's time.
            agenda["meeting"] = {
                "meeting_id": meeting.get("meeting_id"),
                "title": meeting.get("title") or f"Coaching — {client.get('name')}",
                "starts_at": meeting.get("starts_at"),
                "when_label": _when_label(meeting.get("starts_at")),
                "location": meeting.get("location") or "",
            }
            await sync_meeting(db, meeting, client, agenda)
            synced += 1
        except Exception:
            failed += 1
            logger.exception("coaching: calendar sync failed for %s", meeting.get("meeting_id"))
    if synced or failed:
        logger.info("coaching: calendar sync — %s synced, %s failed", synced, failed)
    return {"synced": synced, "failed": failed, "considered": len(meetings)}


def _when_label(starts_at) -> str:
    from services.coaching_core import fmt_when
    return fmt_when(starts_at)


# --------------------------------------------------------------- ICS feeds

def _event_from_meeting(meeting: dict, client: dict, *, include_notes: bool = True) -> dict:
    description = ""
    if include_notes:
        description = meeting.get("note_block") or ""
        if not description and meeting.get("agenda"):
            description = note_block(meeting["agenda"])
    return {
        "uid": f"{meeting.get('meeting_id')}@thehousingnews.com",
        "starts_at": meeting.get("starts_at"),
        "ends_at": meeting.get("ends_at"),
        "title": meeting.get("title") or f"Coaching — {client.get('name')}",
        "description": description,
        "location": meeting.get("location") or "",
    }


async def coach_calendar(db, *, coach_user_id: str | None = None, days_back: int = 60) -> str:
    """Every coaching session on the coach's book, agenda included."""
    from datetime import timedelta

    from services.coaching_store import list_clients

    now = now_utc()
    clients = {c["client_id"]: c for c in await list_clients(db, coach_user_id=coach_user_id, status=None)}
    if not clients:
        return build_ics("Coaching Sessions", [])
    meetings = await db.coaching_meetings.find(
        {
            "client_id": {"$in": list(clients)},
            "starts_at": {"$gte": iso(now - timedelta(days=days_back))},
            "cancelled": {"$ne": True},
        },
        {"_id": 0},
    ).sort("starts_at", 1).to_list(500)
    events = [_event_from_meeting(m, clients[m["client_id"]]) for m in meetings if m.get("client_id") in clients]
    return build_ics("Coaching Sessions", events, now)


async def client_calendar(db, client: dict, *, days_back: int = 60) -> str:
    """The client's own sessions. Carries the agenda but not the coach's
    private prep — the client portal shows them their commitments, not the
    coach's read on the relationship."""
    from datetime import timedelta

    now = now_utc()
    meetings = await db.coaching_meetings.find(
        {
            "client_id": client["client_id"],
            "starts_at": {"$gte": iso(now - timedelta(days=days_back))},
            "cancelled": {"$ne": True},
        },
        {"_id": 0},
    ).sort("starts_at", 1).to_list(200)
    events = []
    for m in meetings:
        ev = _event_from_meeting(m, client, include_notes=False)
        ev["description"] = _client_facing_note(m)
        events.append(ev)
    return build_ics(f"Coaching — {client.get('name')}", events, now)


def _client_facing_note(meeting: dict) -> str:
    """What the client sees on their calendar: their own commitments, no
    trajectory scoring and no coach-side notes."""
    agenda = meeting.get("agenda") or {}
    review = agenda.get("commitments_review") or []
    mine = [c for c in review if c.get("owner") == "client" and c.get("verdict") != "kept"]
    if not mine:
        return "Coaching session."
    lines = ["Before this session — your open commitments:"]
    for c in mine[:10]:
        due = f" (due {c['due_label']})" if c.get("due_label") else ""
        lines.append(f"• {c['title']}{due}")
    return "\n".join(lines)


__all__ = [
    "NOTE_START", "NOTE_END", "note_block", "merge_description", "strip_block",
    "push_to_calendar", "webhook_payload", "webhook_configured",
    "sync_meeting", "sync_upcoming", "coach_calendar", "client_calendar",
]
