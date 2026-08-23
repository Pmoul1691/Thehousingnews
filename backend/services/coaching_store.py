"""Mongo access for the coaching dashboard.

Routes and scheduler jobs both need the same reads (load a client's whole
record, recompute the snapshot, find meetings starting soon). They live here
so the two callers can never drift into answering the same question two
different ways.

Collections: coaching_clients, coaching_sessions, coaching_actions,
coaching_meetings, coaching_snapshots, coaching_email_log.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from services import coaching_ai
from services.coaching_core import (
    DEFAULT_CADENCE_DAYS,
    bucket_actions,
    build_agenda,
    fallback_running_summary,
    iso,
    next_meeting,
    now_utc,
    parse_dt,
    theme_frequency,
    trajectory,
)

logger = logging.getLogger(__name__)

SNAPSHOT_TTL_MINUTES = 30


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def new_portal_token() -> str:
    """The client's dashboard URL is the credential. 32 bytes of urlsafe
    entropy, rotatable from the coach's UI if a link ever leaks."""
    return secrets.token_urlsafe(32)


# ------------------------------------------------------------------ reads

async def list_clients(db, *, coach_user_id: str | None = None, status: str | None = "active") -> list[dict]:
    query: dict = {}
    if coach_user_id:
        query["coach_user_id"] = coach_user_id
    if status:
        query["status"] = status
    return await db.coaching_clients.find(query, {"_id": 0}).sort("name", 1).to_list(500)


async def get_client(db, client_id: str) -> dict | None:
    return await db.coaching_clients.find_one({"client_id": client_id}, {"_id": 0})


async def get_client_by_token(db, token: str) -> dict | None:
    if not token or len(token) < 20:
        return None
    return await db.coaching_clients.find_one(
        {"portal_token": token, "status": {"$ne": "archived"}}, {"_id": 0}
    )


async def sessions_for(db, client_id: str, limit: int = 250) -> list[dict]:
    return await db.coaching_sessions.find(
        {"client_id": client_id}, {"_id": 0}
    ).sort("occurred_at", -1).to_list(limit)


async def actions_for(db, client_id: str, limit: int = 800) -> list[dict]:
    return await db.coaching_actions.find(
        {"client_id": client_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)


async def meetings_for(db, client_id: str, *, upcoming_only: bool = False, limit: int = 100) -> list[dict]:
    query: dict = {"client_id": client_id, "cancelled": {"$ne": True}}
    if upcoming_only:
        query["starts_at"] = {"$gte": iso(now_utc())}
    return await db.coaching_meetings.find(query, {"_id": 0}).sort("starts_at", 1).to_list(limit)


async def client_bundle(db, client_id: str) -> dict | None:
    """Everything about one client in a single call."""
    client = await get_client(db, client_id)
    if not client:
        return None
    return {
        "client": client,
        "sessions": await sessions_for(db, client_id),
        "actions": await actions_for(db, client_id),
        "meetings": await meetings_for(db, client_id),
    }


# -------------------------------------------------------------- snapshots

async def get_snapshot(db, client_id: str) -> dict | None:
    return await db.coaching_snapshots.find_one({"client_id": client_id}, {"_id": 0})


def _snapshot_is_fresh(snap: dict | None, now: datetime) -> bool:
    if not snap:
        return False
    made = parse_dt(snap.get("generated_at"))
    return bool(made and (now - made) < timedelta(minutes=SNAPSHOT_TTL_MINUTES))


async def refresh_snapshot(db, client_id: str, *, use_ai: bool = True, force: bool = False) -> dict | None:
    """Recompute a client's running summary, trajectory and next-call agenda,
    and cache the result.

    The deterministic parts (`coaching_core`) are recomputed every time —
    they're cheap. The LLM narrative is only regenerated when the cache has
    gone stale or `force` is set, so opening the dashboard ten times in an
    afternoon costs one model call, not ten.
    """
    now = now_utc()
    bundle = await client_bundle(db, client_id)
    if not bundle:
        return None

    client, sessions, actions, meetings = (
        bundle["client"], bundle["sessions"], bundle["actions"], bundle["meetings"]
    )
    existing = await get_snapshot(db, client_id)
    reuse_ai = _snapshot_is_fresh(existing, now) and not force

    traj = trajectory(sessions, actions, now, client.get("cadence_days") or DEFAULT_CADENCE_DAYS)

    if reuse_ai and existing:
        narrative = existing.get("narrative") or {}
        read = existing.get("trajectory_read") or {}
    elif use_ai:
        narrative = await coaching_ai.running_summary(client, sessions, actions)
        read = await coaching_ai.trajectory_narrative(
            client, traj,
            [str(s.get("summary") or "") for s in sessions[:4] if s.get("summary")],
        )
    else:
        narrative = {
            "summary": fallback_running_summary(client, sessions, actions, now),
            "recurring_patterns": [], "progress_markers": [], "watch_items": [],
            "ai_generated": False,
        }
        read = {"read": " ".join(traj["signals"] + traj["risks"]), "coach_move": "", "ai_generated": False}

    upcoming = next_meeting(meetings, now)
    agenda = build_agenda(
        client=client, sessions=sessions, actions=actions, meeting=upcoming,
        now=now, running_summary=narrative.get("summary", ""),
    )
    agenda["trajectory_read"] = read

    snapshot = {
        "client_id": client_id,
        "client_name": client.get("name"),
        "generated_at": iso(now),
        "narrative": narrative,
        "trajectory": traj,
        "trajectory_read": read,
        "agenda": agenda,
        "counts": agenda["counts"],
        "themes": theme_frequency(sessions),
        "next_meeting": upcoming,
    }
    await db.coaching_snapshots.update_one(
        {"client_id": client_id}, {"$set": snapshot}, upsert=True
    )
    return snapshot


async def snapshot_or_refresh(db, client_id: str, *, use_ai: bool = True) -> dict | None:
    """Cheap read path: serve the cached snapshot when it's fresh."""
    snap = await get_snapshot(db, client_id)
    if _snapshot_is_fresh(snap, now_utc()):
        return snap
    return await refresh_snapshot(db, client_id, use_ai=use_ai)


# ------------------------------------------------------------- dashboards

async def master_rows(db, *, coach_user_id: str | None = None, use_ai: bool = False) -> list[dict]:
    """One row per active client for the coach's master dashboard.

    `use_ai=False` by default: the master view loads a dozen clients at once
    and the deterministic rollup is what the coach scans. The prose lives on
    the per-client page and in the emails, where one call per client is fine.
    """
    now = now_utc()
    clients = await list_clients(db, coach_user_id=coach_user_id)
    rows = []
    for client in clients:
        cid = client["client_id"]
        sessions = await sessions_for(db, cid, limit=60)
        actions = await actions_for(db, cid)
        meetings = await meetings_for(db, cid, upcoming_only=True, limit=5)
        snap = await get_snapshot(db, cid)

        traj = trajectory(sessions, actions, now, client.get("cadence_days") or DEFAULT_CADENCE_DAYS)
        buckets = bucket_actions(actions, now)
        upcoming = next_meeting(meetings, now)
        agenda = build_agenda(
            client=client, sessions=sessions, actions=actions, meeting=upcoming, now=now,
            running_summary=(snap or {}).get("narrative", {}).get("summary", ""),
        )

        rows.append({
            "client_id": cid,
            "name": client.get("name"),
            "email": client.get("email"),
            "company": client.get("company") or "",
            "cadence_days": client.get("cadence_days") or DEFAULT_CADENCE_DAYS,
            "portal_token": client.get("portal_token"),
            "trajectory": traj,
            "counts": buckets["counts"],
            "next_meeting": upcoming,
            "last_session_at": sessions[0]["occurred_at"] if sessions else None,
            "commitments_review": agenda["commitments_review"],
            "checklist": agenda["checklist"],
            "overdue": buckets["overdue"][:5],
            "wins": buckets["recent_wins"][:3],
            "running_summary": (snap or {}).get("narrative", {}).get("summary", ""),
        })

    # Worst trajectory first — the master dashboard is a triage list, not a
    # roster. Clients with a meeting today jump the queue regardless.
    def _rank(row):
        starts = parse_dt((row.get("next_meeting") or {}).get("starts_at"))
        imminent = bool(starts and starts <= now + timedelta(hours=36))
        return (0 if imminent else 1, row["trajectory"]["score"], row["name"] or "")

    rows.sort(key=_rank)
    return rows


# ---------------------------------------------------------------- meetings

async def meetings_starting_between(db, start: datetime, end: datetime) -> list[dict]:
    return await db.coaching_meetings.find(
        {
            "starts_at": {"$gte": iso(start), "$lte": iso(end)},
            "cancelled": {"$ne": True},
        },
        {"_id": 0},
    ).sort("starts_at", 1).to_list(200)


async def mark_prep_sent(db, meeting_id: str, when: datetime | None = None) -> None:
    await db.coaching_meetings.update_one(
        {"meeting_id": meeting_id},
        {"$set": {"prep_sent_at": iso(when or now_utc())}},
    )


async def log_email(db, *, kind: str, to_email: str, client_id: str | None = None,
                    meeting_id: str | None = None, result: dict | None = None) -> None:
    """Audit trail so a duplicate 4-hour warning is always traceable."""
    try:
        await db.coaching_email_log.insert_one({
            "log_id": new_id("clog"),
            "kind": kind,
            "to_email": to_email,
            "client_id": client_id,
            "meeting_id": meeting_id,
            "ok": not bool((result or {}).get("error")),
            "result": {k: v for k, v in (result or {}).items() if k in ("id", "error", "skipped", "blocked")},
            "created_at": iso(now_utc()),
        })
    except Exception:
        logger.exception("coaching: failed to write email log")


async def ensure_indexes(db) -> None:
    """Called from server startup alongside the rest of the app's indexes."""
    await db.coaching_clients.create_index("client_id", unique=True)
    await db.coaching_clients.create_index("portal_token", unique=True, sparse=True)
    await db.coaching_clients.create_index("coach_user_id")
    await db.coaching_sessions.create_index("session_id", unique=True)
    await db.coaching_sessions.create_index([("client_id", 1), ("occurred_at", -1)])
    await db.coaching_actions.create_index("action_id", unique=True)
    await db.coaching_actions.create_index([("client_id", 1), ("status", 1)])
    await db.coaching_actions.create_index("due_date")
    await db.coaching_meetings.create_index("meeting_id", unique=True)
    await db.coaching_meetings.create_index([("starts_at", 1)])
    await db.coaching_meetings.create_index([("client_id", 1), ("starts_at", -1)])
    await db.coaching_snapshots.create_index("client_id", unique=True)
    await db.coaching_email_log.create_index("created_at")
