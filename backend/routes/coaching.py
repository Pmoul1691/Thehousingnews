"""Coach-side API for the coaching dashboard.

Admin-only. Everything the coach does — roster, session notes, action items,
meetings, the master dashboard, the manual job triggers — lives here. The
client-facing half is in `routes/coaching_portal.py` and is authenticated by
an unguessable per-client token instead of a session.
"""
import logging
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Header, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field

from services import coaching_ai, coaching_calendar
from services.auth_helpers import get_current_user, is_user_admin
from services.brevo import app_url
from services.coaching_core import (
    DEFAULT_CADENCE_DAYS,
    bucket_actions,
    iso,
    normalize_owner,
    normalize_status,
    now_utc,
    parse_dt,
    render_agenda_text,
)
from services.coaching_email import (
    build_portal_invite_html,
    send_meeting_prep,
    send_weekly_report,
)
from services.coaching_store import (
    actions_for,
    client_bundle,
    get_client,
    list_clients,
    master_rows,
    meetings_for,
    new_id,
    new_portal_token,
    refresh_snapshot,
    sessions_for,
    snapshot_or_refresh,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- payloads

class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    company: str = Field(default="", max_length=160)
    cadence_days: int = Field(default=DEFAULT_CADENCE_DAYS, ge=1, le=365)
    objectives: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)


class ClientPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=160)
    cadence_days: Optional[int] = Field(default=None, ge=1, le=365)
    objectives: Optional[list[str]] = None
    focus_areas: Optional[list[str]] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["active", "paused", "archived"]] = None


class SessionIn(BaseModel):
    occurred_at: Optional[str] = None          # ISO; defaults to now
    title: str = Field(default="", max_length=200)
    notes: str = Field(min_length=1, max_length=120_000)
    summarize: bool = True                     # run the notes through the model
    create_actions: bool = True                # open action items for what was committed


class SessionPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=120_000)
    summary: Optional[str] = Field(default=None, max_length=4000)
    themes: Optional[list[str]] = None
    occurred_at: Optional[str] = None


class ActionIn(BaseModel):
    client_id: str
    session_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=2000)
    owner: str = Field(default="client")
    status: str = Field(default="open")
    due_date: Optional[str] = None


class ActionPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    detail: Optional[str] = Field(default=None, max_length=2000)
    owner: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None


class MeetingIn(BaseModel):
    client_id: str
    starts_at: str
    ends_at: Optional[str] = None
    title: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=300)
    calendar_event_id: str = Field(default="", max_length=200)
    calendar_id: str = Field(default="", max_length=200)


class MeetingPatch(BaseModel):
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=300)
    calendar_event_id: Optional[str] = Field(default=None, max_length=200)
    calendar_id: Optional[str] = Field(default=None, max_length=200)
    cancelled: Optional[bool] = None


class MeetingImportRow(BaseModel):
    """One event from an external calendar. Matched to a client by
    `client_id` when known, otherwise by attendee email."""
    starts_at: str
    ends_at: Optional[str] = None
    title: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=300)
    calendar_event_id: str = Field(default="", max_length=200)
    calendar_id: str = Field(default="", max_length=200)
    client_id: Optional[str] = None
    attendee_email: Optional[str] = None


class MeetingImport(BaseModel):
    events: list[MeetingImportRow] = Field(default_factory=list, max_length=500)


# ------------------------------------------------------------------ router

def setup(db):
    router = APIRouter(prefix="/api/coaching", tags=["coaching"])

    async def _admin(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        if not is_user_admin(user):
            raise HTTPException(status_code=403, detail="Admin only")
        return user

    async def _require_client(client_id: str) -> dict:
        client = await get_client(db, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client

    def _clean_list(values, limit: int = 20, size: int = 300) -> list[str]:
        return [str(v).strip()[:size] for v in (values or []) if str(v).strip()][:limit]

    async def _touch(client_id: str) -> None:
        """Any write invalidates the cached snapshot — clearing the stamp is
        enough, the next read recomputes."""
        await db.coaching_snapshots.update_one(
            {"client_id": client_id}, {"$set": {"generated_at": None}}
        )

    # ------------------------------------------------------------- clients

    @router.get("/clients")
    async def get_clients(
        response: Response,
        status: Optional[str] = Query(default="active"),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        response.headers["Cache-Control"] = "private, no-store"
        clients = await list_clients(db, status=None if status == "all" else status)
        return {"clients": clients, "count": len(clients)}

    @router.post("/clients")
    async def create_client(
        payload: ClientIn,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await _admin(session_token, authorization)
        now = iso(now_utc())
        client = {
            "client_id": new_id("cli"),
            "coach_user_id": user["user_id"],
            "name": payload.name.strip(),
            "email": (payload.email or "").lower() or None,
            "company": payload.company.strip(),
            "cadence_days": payload.cadence_days,
            "objectives": _clean_list(payload.objectives),
            "focus_areas": _clean_list(payload.focus_areas, limit=12, size=80),
            "notes": payload.notes.strip(),
            "status": "active",
            "portal_token": new_portal_token(),
            "created_at": now,
            "updated_at": now,
        }
        await db.coaching_clients.insert_one(dict(client))
        return {"client": client}

    @router.patch("/clients/{client_id}")
    async def patch_client(
        client_id: str,
        payload: ClientPatch,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        await _require_client(client_id)
        update: dict = {"updated_at": iso(now_utc())}
        if payload.name is not None:
            update["name"] = payload.name.strip()
        if payload.email is not None:
            update["email"] = str(payload.email).lower()
        if payload.company is not None:
            update["company"] = payload.company.strip()
        if payload.cadence_days is not None:
            update["cadence_days"] = payload.cadence_days
        if payload.objectives is not None:
            update["objectives"] = _clean_list(payload.objectives)
        if payload.focus_areas is not None:
            update["focus_areas"] = _clean_list(payload.focus_areas, limit=12, size=80)
        if payload.notes is not None:
            update["notes"] = payload.notes.strip()
        if payload.status is not None:
            update["status"] = payload.status
        await db.coaching_clients.update_one({"client_id": client_id}, {"$set": update})
        await _touch(client_id)
        return {"client": await get_client(db, client_id)}

    @router.get("/clients/{client_id}")
    async def get_client_detail(
        client_id: str,
        response: Response,
        refresh: bool = Query(default=False),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """The coach's full workspace for one client: history, every action
        item, the running summary, the trajectory read and the next agenda."""
        await _admin(session_token, authorization)
        response.headers["Cache-Control"] = "private, no-store"
        bundle = await client_bundle(db, client_id)
        if not bundle:
            raise HTTPException(status_code=404, detail="Client not found")

        snap = (
            await refresh_snapshot(db, client_id, force=True)
            if refresh
            else await snapshot_or_refresh(db, client_id)
        )
        return {
            **bundle,
            "buckets": bucket_actions(bundle["actions"]),
            "snapshot": snap,
            "portal_url": f"{app_url()}/coaching/portal/{bundle['client'].get('portal_token')}",
            "ai_enabled": coaching_ai.enabled(),
        }

    @router.post("/clients/{client_id}/rotate-token")
    async def rotate_token(
        client_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Invalidates the old dashboard link immediately."""
        await _admin(session_token, authorization)
        await _require_client(client_id)
        token = new_portal_token()
        await db.coaching_clients.update_one(
            {"client_id": client_id},
            {"$set": {"portal_token": token, "updated_at": iso(now_utc())}},
        )
        return {"portal_token": token, "portal_url": f"{app_url()}/coaching/portal/{token}"}

    @router.post("/clients/{client_id}/send-portal-link")
    async def send_portal_link(
        client_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Emails the client their dashboard link. Explicit, never automatic —
        the coach decides when a client gets contacted."""
        import asyncio

        from services.brevo import send_email
        from services.coaching_store import log_email

        user = await _admin(session_token, authorization)
        client = await _require_client(client_id)
        if not client.get("email"):
            raise HTTPException(status_code=400, detail="Client has no email address on file")
        url = f"{app_url()}/coaching/portal/{client['portal_token']}"
        html = build_portal_invite_html(client, url, user.get("name") or "")
        result = await asyncio.to_thread(
            send_email, client["email"], client.get("name") or "",
            "Your coaching dashboard", html, ["coaching", "coaching_portal_invite"],
        )
        await log_email(db, kind="coaching_portal_invite", to_email=client["email"],
                        client_id=client_id, result=result)
        if result.get("error"):
            raise HTTPException(status_code=502, detail="Email provider rejected the send")
        return {"sent": True, "to": client["email"]}

    # ------------------------------------------------------------ sessions

    @router.get("/clients/{client_id}/sessions")
    async def get_sessions(
        client_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        return {"sessions": await sessions_for(db, client_id)}

    @router.post("/clients/{client_id}/sessions")
    async def create_session(
        client_id: str,
        payload: SessionIn,
        background: BackgroundTasks,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Log a session. The notes go through the model for a summary, themes
        and the commitments made — each of which becomes an open action item so
        the next call's agenda writes itself."""
        user = await _admin(session_token, authorization)
        client = await _require_client(client_id)

        occurred = parse_dt(payload.occurred_at) or now_utc()
        session_id = new_id("cses")
        now = now_utc()

        prior = await sessions_for(db, client_id, limit=1)
        prior_summary = (prior[0].get("summary") if prior else "") or ""

        enrichment = (
            await coaching_ai.summarize_session(
                payload.notes, client_name=client.get("name") or "", prior_summary=prior_summary
            )
            if payload.summarize
            else {"summary": "", "themes": [], "sentiment": "steady", "headline": "",
                  "direction_note": "", "action_items": [], "open_questions": [], "ai_generated": False}
        )

        doc = {
            "session_id": session_id,
            "client_id": client_id,
            "occurred_at": iso(occurred),
            "title": payload.title.strip() or enrichment.get("headline") or "Coaching session",
            "notes": payload.notes,
            "summary": enrichment.get("summary") or "",
            "headline": enrichment.get("headline") or "",
            "themes": enrichment.get("themes") or [],
            "sentiment": enrichment.get("sentiment") or "steady",
            "direction_note": enrichment.get("direction_note") or "",
            "open_questions": enrichment.get("open_questions") or [],
            "ai_generated": bool(enrichment.get("ai_generated")),
            "created_by": user["user_id"],
            "created_at": iso(now),
            "updated_at": iso(now),
        }
        await db.coaching_sessions.insert_one(dict(doc))

        created_actions = []
        if payload.create_actions:
            for item in enrichment.get("action_items") or []:
                action = {
                    "action_id": new_id("cact"),
                    "client_id": client_id,
                    "session_id": session_id,
                    "title": item["title"],
                    "detail": item.get("detail", ""),
                    "owner": normalize_owner(item.get("owner")),
                    "status": "open",
                    "due_date": _resolve_due(item.get("due_hint"), occurred),
                    "source": "ai_extracted",
                    "created_at": iso(now),
                    "updated_at": iso(now),
                    "completed_at": None,
                }
                await db.coaching_actions.insert_one(dict(action))
                created_actions.append(action)

        # Recompute the narrative out of band so logging a session returns fast.
        background.add_task(_refresh_bg, db, client_id)
        return {
            "session": doc,
            "actions_created": created_actions,
            "ai_generated": bool(enrichment.get("ai_generated")),
        }

    @router.patch("/sessions/{session_id}")
    async def patch_session(
        session_id: str,
        payload: SessionPatch,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        existing = await db.coaching_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Session not found")
        update: dict = {"updated_at": iso(now_utc())}
        if payload.title is not None:
            update["title"] = payload.title.strip()
        if payload.notes is not None:
            update["notes"] = payload.notes
        if payload.summary is not None:
            update["summary"] = payload.summary.strip()
        if payload.themes is not None:
            update["themes"] = _clean_list(payload.themes, limit=8, size=40)
        if payload.occurred_at is not None:
            when = parse_dt(payload.occurred_at)
            if not when:
                raise HTTPException(status_code=400, detail="occurred_at is not a valid date")
            update["occurred_at"] = iso(when)
        await db.coaching_sessions.update_one({"session_id": session_id}, {"$set": update})
        await _touch(existing["client_id"])
        return {"session": await db.coaching_sessions.find_one({"session_id": session_id}, {"_id": 0})}

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        existing = await db.coaching_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.coaching_sessions.delete_one({"session_id": session_id})
        # Action items outlive the note they came from — unlink, don't delete.
        await db.coaching_actions.update_many(
            {"session_id": session_id}, {"$set": {"session_id": None}}
        )
        await _touch(existing["client_id"])
        return {"deleted": True}

    # ------------------------------------------------------------- actions

    @router.get("/clients/{client_id}/actions")
    async def get_actions(
        client_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        actions = await actions_for(db, client_id)
        return {"actions": actions, "buckets": bucket_actions(actions)}

    @router.post("/actions")
    async def create_action(
        payload: ActionIn,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        await _require_client(payload.client_id)
        now = iso(now_utc())
        status = normalize_status(payload.status)
        action = {
            "action_id": new_id("cact"),
            "client_id": payload.client_id,
            "session_id": payload.session_id,
            "title": payload.title.strip(),
            "detail": payload.detail.strip(),
            "owner": normalize_owner(payload.owner),
            "status": status,
            "due_date": iso(d) if (d := parse_dt(payload.due_date)) else None,
            "source": "manual",
            "created_at": now,
            "updated_at": now,
            "completed_at": now if status == "complete" else None,
        }
        await db.coaching_actions.insert_one(dict(action))
        await _touch(payload.client_id)
        return {"action": action}

    @router.patch("/actions/{action_id}")
    async def patch_action(
        action_id: str,
        payload: ActionPatch,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        existing = await db.coaching_actions.find_one({"action_id": action_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Action not found")
        update = _action_update(payload, existing)
        await db.coaching_actions.update_one({"action_id": action_id}, {"$set": update})
        await _touch(existing["client_id"])
        return {"action": await db.coaching_actions.find_one({"action_id": action_id}, {"_id": 0})}

    @router.delete("/actions/{action_id}")
    async def delete_action(
        action_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        existing = await db.coaching_actions.find_one({"action_id": action_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Action not found")
        await db.coaching_actions.delete_one({"action_id": action_id})
        await _touch(existing["client_id"])
        return {"deleted": True}

    # ------------------------------------------------------------ meetings

    @router.get("/meetings")
    async def get_meetings(
        client_id: Optional[str] = Query(default=None),
        days: int = Query(default=30, ge=1, le=365),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        if client_id:
            return {"meetings": await meetings_for(db, client_id)}
        now = now_utc()
        rows = await db.coaching_meetings.find(
            {
                "starts_at": {"$gte": iso(now - timedelta(days=1)), "$lte": iso(now + timedelta(days=days))},
                "cancelled": {"$ne": True},
            },
            {"_id": 0},
        ).sort("starts_at", 1).to_list(300)
        return {"meetings": rows}

    @router.post("/meetings")
    async def create_meeting(
        payload: MeetingIn,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        client = await _require_client(payload.client_id)
        starts = parse_dt(payload.starts_at)
        if not starts:
            raise HTTPException(status_code=400, detail="starts_at is not a valid date")
        ends = parse_dt(payload.ends_at) or (starts + timedelta(hours=1))
        now = iso(now_utc())
        meeting = {
            "meeting_id": new_id("cmtg"),
            "client_id": payload.client_id,
            "starts_at": iso(starts),
            "ends_at": iso(ends),
            "title": payload.title.strip() or f"Coaching — {client.get('name')}",
            "location": payload.location.strip(),
            "calendar_event_id": payload.calendar_event_id.strip(),
            "calendar_id": payload.calendar_id.strip(),
            "cancelled": False,
            "prep_sent_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.coaching_meetings.insert_one(dict(meeting))
        return {"meeting": meeting}

    @router.patch("/meetings/{meeting_id}")
    async def patch_meeting(
        meeting_id: str,
        payload: MeetingPatch,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        await _admin(session_token, authorization)
        existing = await db.coaching_meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Meeting not found")
        update: dict = {"updated_at": iso(now_utc())}
        if payload.starts_at is not None:
            when = parse_dt(payload.starts_at)
            if not when:
                raise HTTPException(status_code=400, detail="starts_at is not a valid date")
            update["starts_at"] = iso(when)
            # A moved meeting earns a fresh prep mail against the new time.
            update["prep_sent_at"] = None
        if payload.ends_at is not None:
            when = parse_dt(payload.ends_at)
            if when:
                update["ends_at"] = iso(when)
        for field in ("title", "location", "calendar_event_id", "calendar_id"):
            value = getattr(payload, field)
            if value is not None:
                update[field] = value.strip()
        if payload.cancelled is not None:
            update["cancelled"] = payload.cancelled
        await db.coaching_meetings.update_one({"meeting_id": meeting_id}, {"$set": update})
        return {"meeting": await db.coaching_meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})}

    @router.post("/meetings/import")
    async def import_meetings(
        payload: MeetingImport,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Bulk upsert from an external calendar.

        Built for a Zapier/Make Zap watching the coach's Google Calendar: post
        each coaching event here and it lands on the right client, matched by
        `client_id` or by attendee email. Upserted on `calendar_event_id`, so
        replaying the same feed never duplicates a meeting.
        """
        await _admin(session_token, authorization)
        clients = await list_clients(db, status=None)
        by_email = {c["email"].lower(): c for c in clients if c.get("email")}
        by_id = {c["client_id"]: c for c in clients}

        created, updated, unmatched = 0, 0, []
        for row in payload.events:
            client = by_id.get(row.client_id or "") or by_email.get((row.attendee_email or "").lower())
            if not client:
                unmatched.append(row.attendee_email or row.client_id or row.title)
                continue
            starts = parse_dt(row.starts_at)
            if not starts:
                unmatched.append(row.title or row.starts_at)
                continue
            ends = parse_dt(row.ends_at) or (starts + timedelta(hours=1))
            now = iso(now_utc())

            key = (
                {"calendar_event_id": row.calendar_event_id}
                if row.calendar_event_id
                else {"client_id": client["client_id"], "starts_at": iso(starts)}
            )
            existing = await db.coaching_meetings.find_one(key, {"_id": 0})
            doc = {
                "client_id": client["client_id"],
                "starts_at": iso(starts),
                "ends_at": iso(ends),
                "title": row.title.strip() or f"Coaching — {client.get('name')}",
                "location": row.location.strip(),
                "calendar_event_id": row.calendar_event_id.strip(),
                "calendar_id": row.calendar_id.strip(),
                "cancelled": False,
                "updated_at": now,
            }
            if existing:
                # A rescheduled event needs its prep mail re-armed.
                if existing.get("starts_at") != doc["starts_at"]:
                    doc["prep_sent_at"] = None
                await db.coaching_meetings.update_one(
                    {"meeting_id": existing["meeting_id"]}, {"$set": doc}
                )
                updated += 1
            else:
                doc.update({"meeting_id": new_id("cmtg"), "prep_sent_at": None, "created_at": now})
                await db.coaching_meetings.insert_one(dict(doc))
                created += 1

        return {"created": created, "updated": updated, "unmatched": unmatched}

    # ----------------------------------------------------- master dashboard

    @router.get("/master")
    async def get_master(
        response: Response,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Pete's view: every active client, worst trajectory first, each with
        last week's commitments and the checklist for the next call."""
        await _admin(session_token, authorization)
        response.headers["Cache-Control"] = "private, no-store"
        now = now_utc()
        rows = await master_rows(db)
        week_ahead = [
            r for r in rows
            if (m := r.get("next_meeting")) and (d := parse_dt(m.get("starts_at")))
            and d <= now + timedelta(days=7)
        ]
        return {
            "generated_at": iso(now),
            "clients": rows,
            "totals": {
                "clients": len(rows),
                "meetings_this_week": len(week_ahead),
                "open": sum(r["counts"]["open_total"] for r in rows),
                "overdue": sum(r["counts"]["overdue"] for r in rows),
                "completed_recent": sum(len(r.get("wins") or []) for r in rows),
                "at_risk": sum(1 for r in rows if r["trajectory"]["score"] < 55),
            },
            "ai_enabled": coaching_ai.enabled(),
            "calendar_webhook": coaching_calendar.webhook_configured(),
        }

    @router.get("/clients/{client_id}/agenda")
    async def get_agenda(
        client_id: str,
        response: Response,
        refresh: bool = Query(default=False),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """The prep sheet for the next call, plus the exact text block that
        gets written into the calendar event."""
        await _admin(session_token, authorization)
        response.headers["Cache-Control"] = "private, no-store"
        await _require_client(client_id)
        snap = (
            await refresh_snapshot(db, client_id, force=True)
            if refresh else await snapshot_or_refresh(db, client_id)
        )
        if not snap:
            raise HTTPException(status_code=404, detail="Client not found")
        agenda = snap["agenda"]
        return {
            "agenda": agenda,
            "text": render_agenda_text(agenda),
            "calendar_note": coaching_calendar.note_block(agenda),
        }

    # ------------------------------------------------------ calendar + jobs

    @router.get("/calendar.ics")
    async def coach_ics(
        token: str = Query(..., min_length=20),
    ):
        """Subscribable feed of every coaching session with its agenda.

        Guarded by a query-string secret (COACHING_CALENDAR_TOKEN) rather than
        a session cookie: Google fetches a subscribed feed unattended, with no
        way to carry one. The feed exposes the coach's private prep notes, so
        the secret is dedicated to this endpoint and is not any client's portal
        token. Unset means the endpoint is closed.
        """
        import os

        expected = os.environ.get("COACHING_CALENDAR_TOKEN", "")
        if not expected or token != expected:
            raise HTTPException(status_code=403, detail="Invalid calendar token")
        ics = await coaching_calendar.coach_calendar(db)
        return Response(
            content=ics,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="coaching.ics"',
                "Cache-Control": "private, max-age=300",
            },
        )

    @router.post("/meetings/{meeting_id}/sync-calendar")
    async def sync_calendar(
        meeting_id: str,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Push this meeting's agenda into the calendar event now."""
        await _admin(session_token, authorization)
        meeting = await db.coaching_meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        client = await _require_client(meeting["client_id"])
        snap = await snapshot_or_refresh(db, meeting["client_id"])
        if not snap:
            raise HTTPException(status_code=404, detail="Client not found")
        result = await coaching_calendar.sync_meeting(db, meeting, client, snap["agenda"])
        return {"result": result, "webhook_configured": coaching_calendar.webhook_configured()}

    @router.post("/run/{job}")
    async def run_job(
        job: Literal["weekly-report", "meeting-prep", "calendar-sync", "refresh"],
        client_id: Optional[str] = Query(default=None),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        """Fire a scheduled job by hand — for testing the wiring, and for the
        Monday morning when you want the report before 9."""
        await _admin(session_token, authorization)
        if job == "weekly-report":
            return await send_weekly_report(db)
        if job == "meeting-prep":
            return await send_meeting_prep(db)
        if job == "calendar-sync":
            return await coaching_calendar.sync_upcoming(db)
        if not client_id:
            raise HTTPException(status_code=400, detail="refresh needs ?client_id=")
        snap = await refresh_snapshot(db, client_id, force=True)
        if not snap:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"refreshed": client_id, "generated_at": snap["generated_at"]}

    return router


# ------------------------------------------------------------- module helpers

def _action_update(payload, existing: dict) -> dict:
    """Build the $set for an action patch, keeping `completed_at` honest: it
    is stamped on the transition into `complete` and cleared on the way out,
    so a reopened item stops counting as a win."""
    update: dict = {"updated_at": iso(now_utc())}
    if payload.title is not None:
        update["title"] = payload.title.strip()
    if payload.detail is not None:
        update["detail"] = payload.detail.strip()
    if payload.owner is not None:
        update["owner"] = normalize_owner(payload.owner)
    if payload.due_date is not None:
        update["due_date"] = iso(d) if (d := parse_dt(payload.due_date)) else None
    if payload.status is not None:
        status = normalize_status(payload.status)
        update["status"] = status
        was_complete = normalize_status(existing.get("status")) == "complete"
        if status == "complete" and not was_complete:
            update["completed_at"] = iso(now_utc())
        elif status != "complete" and was_complete:
            update["completed_at"] = None
    return update


def _resolve_due(hint: str | None, anchor: datetime) -> str | None:
    """Turn the model's `due_hint` into a real date.

    Accepts an explicit YYYY-MM-DD, or the handful of phrases that actually
    show up in coaching notes. Anything else returns None — an item with no
    date is honest; an invented date is not.
    """
    text = (hint or "").strip().lower()
    if not text:
        return None
    explicit = parse_dt(text[:10]) if len(text) >= 10 and text[4] == "-" else None
    if explicit:
        return iso(explicit)
    offsets = {
        "tomorrow": 1,
        "this week": 5,
        "end of week": 5,
        "next week": 7,
        "two weeks": 14,
        "next two weeks": 14,
        "this month": 30,
        "next month": 30,
        "before the next call": 7,
        "by the next call": 7,
        "next session": 7,
    }
    for phrase, days in offsets.items():
        if phrase in text:
            return iso(anchor + timedelta(days=days))
    return None


async def _refresh_bg(db, client_id: str) -> None:
    """BackgroundTask wrapper — a failed narrative regeneration must never
    surface as a failed session save."""
    try:
        await refresh_snapshot(db, client_id, force=True)
    except Exception:
        logger.exception("coaching: background snapshot refresh failed for %s", client_id)
