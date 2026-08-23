"""The client's own dashboard.

Each coaching client gets a private URL — `/coaching/portal/<token>` — with no
password and no account to create. The token in the path is the credential:
32 bytes of `secrets.token_urlsafe` entropy, unique per client, rotatable from
the coach's UI the moment a link is shared somewhere it shouldn't be.

What the client sees is deliberately narrower than what the coach sees. They
get the running summary of their own conversations, their own action items
across all three states, and their upcoming session. They do not get the
trajectory score, the coach's prep checklist, or the coach's raw notes — those
are working material, and a number grading the relationship is not something to
put in front of the person being graded without the coach choosing to.
"""
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from services.coaching_calendar import client_calendar
from services.coaching_core import (
    bucket_actions,
    fmt_day,
    fmt_when,
    iso,
    next_meeting,
    normalize_status,
    now_utc,
    status_label,
    theme_frequency,
)
from services.coaching_store import (
    actions_for,
    get_client_by_token,
    meetings_for,
    sessions_for,
    snapshot_or_refresh,
)

logger = logging.getLogger(__name__)

# What the client may set on their own items. They can report progress and
# completion; they cannot drop a commitment unilaterally — that's a
# conversation, not a checkbox.
CLIENT_SETTABLE = ("open", "in_progress", "complete")


class StatusUpdate(BaseModel):
    status: Literal["open", "in_progress", "complete"]
    note: str = Field(default="", max_length=600)


def _public_action(action: dict, now) -> dict:
    """Strip an action down to what the client needs to see."""
    from services.coaching_core import days_overdue

    return {
        "action_id": action.get("action_id"),
        "title": action.get("title"),
        "detail": action.get("detail") or "",
        "status": normalize_status(action.get("status")),
        "status_label": status_label(action.get("status")),
        "owner": action.get("owner"),
        "due_date": action.get("due_date"),
        "due_label": fmt_day(action.get("due_date")) if action.get("due_date") else "",
        "days_overdue": days_overdue(action, now),
        "completed_at": action.get("completed_at"),
        "created_at": action.get("created_at"),
    }


def _public_session(session: dict) -> dict:
    """Session summaries are shared; the coach's raw notes are not."""
    return {
        "session_id": session.get("session_id"),
        "occurred_at": session.get("occurred_at"),
        "when_label": fmt_day(session.get("occurred_at")),
        "title": session.get("title") or "Coaching session",
        "summary": session.get("summary") or "",
        "themes": session.get("themes") or [],
    }


def setup(db):
    router = APIRouter(prefix="/api/coaching/portal", tags=["coaching-portal"])

    async def _client_or_404(token: str) -> dict:
        client = await get_client_by_token(db, token)
        if not client:
            # Same response for a bad token and an archived client — a portal
            # URL should never confirm that it used to be valid.
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return client

    @router.get("/{token}")
    async def dashboard(token: str, response: Response):
        """Everything on the client's dashboard in one request."""
        response.headers["Cache-Control"] = "private, no-store"
        client = await _client_or_404(token)
        now = now_utc()
        cid = client["client_id"]

        sessions = await sessions_for(db, cid)
        actions = await actions_for(db, cid)
        meetings = await meetings_for(db, cid, upcoming_only=True, limit=5)
        snap = await snapshot_or_refresh(db, cid)

        buckets = bucket_actions(actions, now)
        # The client's own list. Items the coach owes them are shown
        # separately so nobody chases the wrong homework.
        mine = [a for a in actions if (a.get("owner") or "client") == "client"]
        theirs = [a for a in actions if a.get("owner") == "coach"]
        my_buckets = bucket_actions(mine, now)
        upcoming = next_meeting(meetings, now)
        narrative = (snap or {}).get("narrative") or {}

        return {
            "client": {
                "client_id": cid,
                "name": client.get("name"),
                "company": client.get("company") or "",
                "objectives": client.get("objectives") or [],
                "focus_areas": client.get("focus_areas") or [],
                "cadence_days": client.get("cadence_days"),
            },
            "summary": {
                "running": narrative.get("summary") or "",
                "recurring_patterns": narrative.get("recurring_patterns") or [],
                "progress_markers": narrative.get("progress_markers") or [],
                "generated_at": (snap or {}).get("generated_at"),
            },
            "actions": {
                "completed": [_public_action(a, now) for a in my_buckets["completed"]],
                "in_process": [_public_action(a, now) for a in my_buckets["in_process"]],
                "incomplete": [_public_action(a, now) for a in my_buckets["incomplete"]],
                "counts": my_buckets["counts"],
            },
            "coach_owes": [_public_action(a, now) for a in theirs if a.get("status") != "complete"],
            "sessions": [_public_session(s) for s in sessions[:40]],
            "session_count": len(sessions),
            "themes": theme_frequency(sessions, limit=6),
            "next_meeting": {
                "meeting_id": upcoming.get("meeting_id"),
                "title": upcoming.get("title"),
                "starts_at": upcoming.get("starts_at"),
                "when_label": fmt_when(upcoming.get("starts_at")),
                "location": upcoming.get("location") or "",
            } if upcoming else None,
            "totals": {
                "completed": buckets["counts"]["completed"],
                "in_process": buckets["counts"]["in_process"],
                "incomplete": buckets["counts"]["incomplete"],
                "completion_rate": my_buckets["counts"]["completion_rate"],
            },
            "calendar_url": f"/api/coaching/portal/{token}/calendar.ics",
            "generated_at": iso(now),
        }

    @router.patch("/{token}/actions/{action_id}")
    async def update_action(token: str, action_id: str, payload: StatusUpdate):
        """Let the client move their own item between the three states.

        Scoped to their own client_id and their own items — a token cannot
        touch another client's board, and cannot reassign or retitle anything.
        """
        client = await _client_or_404(token)
        action = await db.coaching_actions.find_one(
            {"action_id": action_id, "client_id": client["client_id"]}, {"_id": 0}
        )
        if not action:
            raise HTTPException(status_code=404, detail="Item not found")
        if (action.get("owner") or "client") != "client":
            raise HTTPException(status_code=403, detail="That item belongs to your coach")

        status = normalize_status(payload.status)
        if status not in CLIENT_SETTABLE:
            raise HTTPException(status_code=400, detail="Unsupported status")

        now = now_utc()
        update: dict = {"status": status, "updated_at": iso(now), "updated_by": "client"}
        was_complete = normalize_status(action.get("status")) == "complete"
        if status == "complete" and not was_complete:
            update["completed_at"] = iso(now)
        elif status != "complete" and was_complete:
            update["completed_at"] = None
        if payload.note.strip():
            update["client_note"] = payload.note.strip()

        await db.coaching_actions.update_one({"action_id": action_id}, {"$set": update})
        # The coach's next agenda should reflect this, so drop the cache.
        await db.coaching_snapshots.update_one(
            {"client_id": client["client_id"]}, {"$set": {"generated_at": None}}
        )
        updated = await db.coaching_actions.find_one({"action_id": action_id}, {"_id": 0})
        return {"action": _public_action(updated, now)}

    @router.get("/{token}/calendar.ics")
    async def client_ics(token: str):
        """The client's own sessions, with their open commitments in the
        event description. Coach-side prep is not included."""
        client = await _client_or_404(token)
        ics = await client_calendar(db, client)
        return Response(
            content=ics,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="coaching.ics"',
                "Cache-Control": "private, max-age=300",
            },
        )

    @router.get("/{token}/sessions/{session_id}")
    async def session_detail(token: str, session_id: str, response: Response):
        """One past conversation, as summarised for the client."""
        response.headers["Cache-Control"] = "private, no-store"
        client = await _client_or_404(token)
        session = await db.coaching_sessions.find_one(
            {"session_id": session_id, "client_id": client["client_id"]}, {"_id": 0}
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        now = now_utc()
        related = await db.coaching_actions.find(
            {"session_id": session_id, "client_id": client["client_id"]}, {"_id": 0}
        ).to_list(60)
        return {
            "session": _public_session(session),
            "actions": [_public_action(a, now) for a in related if (a.get("owner") or "client") == "client"],
        }

    return router
