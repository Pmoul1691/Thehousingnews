"""Coaching dashboard — pure domain logic.

Everything in this module is stdlib-only and side-effect free: plain dicts in,
plain dicts out. The action bucketing, the agenda builder, the trajectory
engine and the ICS writer all live here so they can be unit-tested without
Mongo, FastAPI or an LLM key — and so the model layer in `coaching_ai.py` has
a deterministic fallback to degrade to whenever the LLM is unavailable.

Document shapes (Mongo collections; timestamps are ISO-8601 strings):

  coaching_clients   client_id, coach_user_id, name, email, cadence_days,
                     objectives[], focus_areas[], portal_token, status
  coaching_sessions  session_id, client_id, occurred_at, title, notes,
                     summary, themes[], sentiment, headline
  coaching_actions   action_id, client_id, session_id, title, detail, owner,
                     status, due_date, created_at, completed_at, updated_at
  coaching_meetings  meeting_id, client_id, starts_at, ends_at, title,
                     location, calendar_event_id, agenda, prep_sent_at
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    CHICAGO = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - zoneinfo ships with 3.9+
    CHICAGO = timezone.utc


# ---------------------------------------------------------------- constants

# Canonical action states. Pete's vocabulary is "completed / in process /
# incomplete"; `dropped` exists so an abandoned commitment can leave the
# active list without being counted as a miss forever.
STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_DROPPED = "dropped"

ACTION_STATUSES = (STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_COMPLETE, STATUS_DROPPED)

# Every spelling we accept on the way in, normalised to the canonical set.
_STATUS_ALIASES = {
    "open": STATUS_OPEN,
    "not_started": STATUS_OPEN,
    "notstarted": STATUS_OPEN,
    "todo": STATUS_OPEN,
    "incomplete": STATUS_OPEN,
    "pending": STATUS_OPEN,
    "in_progress": STATUS_IN_PROGRESS,
    "inprogress": STATUS_IN_PROGRESS,
    "in_process": STATUS_IN_PROGRESS,
    "started": STATUS_IN_PROGRESS,
    "working": STATUS_IN_PROGRESS,
    "doing": STATUS_IN_PROGRESS,
    "complete": STATUS_COMPLETE,
    "completed": STATUS_COMPLETE,
    "done": STATUS_COMPLETE,
    "finished": STATUS_COMPLETE,
    "dropped": STATUS_DROPPED,
    "cancelled": STATUS_DROPPED,
    "canceled": STATUS_DROPPED,
    "abandoned": STATUS_DROPPED,
    "wont_do": STATUS_DROPPED,
}

# Human labels — used in the UI, the emails and the calendar note so the
# three surfaces never drift apart.
STATUS_LABELS = {
    STATUS_OPEN: "Incomplete",
    STATUS_IN_PROGRESS: "In process",
    STATUS_COMPLETE: "Completed",
    STATUS_DROPPED: "Dropped",
}

OWNER_CLIENT = "client"
OWNER_COACH = "coach"
ACTION_OWNERS = (OWNER_CLIENT, OWNER_COACH)

DEFAULT_CADENCE_DAYS = 14

# Trajectory bands, high to low. (floor, key, label)
_TRAJECTORY_BANDS = (
    (75, "accelerating", "Accelerating"),
    (55, "steady", "Steady"),
    (35, "drifting", "Drifting"),
    (0, "stalled", "Stalled"),
)


# ------------------------------------------------------------ time helpers

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value) -> datetime | None:
    """Parse an ISO-8601 string (or pass a datetime through) to an aware UTC
    datetime. Returns None for anything unparseable rather than raising —
    a single malformed note must never take down the whole dashboard."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            # Bare date, e.g. "2026-03-04"
            try:
                dt = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def local(dt: datetime | None) -> datetime | None:
    """Render an instant in the coach's working timezone (America/Chicago)."""
    return dt.astimezone(CHICAGO) if dt else None


def fmt_day(value) -> str:
    """'Mon Mar 4' — used in checklists and email bodies."""
    dt = parse_dt(value)
    return local(dt).strftime("%a %b %-d") if dt else "no date"


def fmt_when(value) -> str:
    """'Mon Mar 4, 9:00 AM CT' — used for meeting times."""
    dt = parse_dt(value)
    if not dt:
        return "unscheduled"
    return local(dt).strftime("%a %b %-d, %-I:%M %p") + " CT"


def days_between(later: datetime, earlier: datetime) -> int:
    """Whole days from `earlier` to `later`, negative if earlier is in the future."""
    return int((later - earlier).total_seconds() // 86400)


def week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 America/Chicago of the week containing `now`, as UTC."""
    ref = local(now or now_utc())
    monday = ref - timedelta(days=ref.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def review_window(now: datetime | None = None, days: int = 7) -> tuple[datetime, datetime]:
    """The 'past week' Pete wants to hold clients to: a rolling `days` window
    ending now. Rolling rather than calendar-aligned because coaching calls
    land on every weekday, not just Mondays."""
    end = now or now_utc()
    return end - timedelta(days=days), end


# ------------------------------------------------------------ normalisation

def normalize_status(value) -> str:
    """Accept whatever a human or a model typed. Spaces and hyphens both
    collapse to underscores first, so "In Progress", "in-progress" and
    "in_process" all land on the same state."""
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _STATUS_ALIASES.get(key, STATUS_OPEN)


def normalize_owner(value) -> str:
    key = str(value or "").strip().lower()
    return OWNER_COACH if key in (OWNER_COACH, "me", "pete", "self") else OWNER_CLIENT


def status_label(value) -> str:
    return STATUS_LABELS[normalize_status(value)]


def is_open(action: dict) -> bool:
    """Still live — not finished, not abandoned."""
    return normalize_status(action.get("status")) in (STATUS_OPEN, STATUS_IN_PROGRESS)


def action_age_days(action: dict, now: datetime) -> int:
    created = parse_dt(action.get("created_at"))
    return days_between(now, created) if created else 0


def days_overdue(action: dict, now: datetime) -> int:
    """Positive when the due date has passed and the item is still live."""
    if not is_open(action):
        return 0
    due = parse_dt(action.get("due_date"))
    if not due:
        return 0
    return max(0, days_between(now, due))


def _sort_key(action: dict, now: datetime):
    """Most urgent first: overdue by how much, then soonest due, then oldest."""
    due = parse_dt(action.get("due_date"))
    return (
        -days_overdue(action, now),
        due.timestamp() if due else float("inf"),
        -action_age_days(action, now),
        str(action.get("title") or ""),
    )


# --------------------------------------------------------- action bucketing

def bucket_actions(actions: list[dict], now: datetime | None = None) -> dict:
    """Split a client's action items into the three states Pete asked for —
    completed, in process, incomplete — plus the derived cuts the dashboard
    and the agenda need (overdue, due this week, recent wins, stale)."""
    now = now or now_utc()
    since, _ = review_window(now)

    completed, in_process, incomplete, dropped = [], [], [], []
    for a in actions or []:
        st = normalize_status(a.get("status"))
        if st == STATUS_COMPLETE:
            completed.append(a)
        elif st == STATUS_IN_PROGRESS:
            in_process.append(a)
        elif st == STATUS_DROPPED:
            dropped.append(a)
        else:
            incomplete.append(a)

    live = in_process + incomplete
    overdue = sorted((a for a in live if days_overdue(a, now) > 0), key=lambda a: _sort_key(a, now))

    week_end = now + timedelta(days=7)
    due_this_week = sorted(
        (
            a for a in live
            if (d := parse_dt(a.get("due_date"))) is not None
            and now <= d <= week_end
        ),
        key=lambda a: _sort_key(a, now),
    )

    recent_wins = sorted(
        (
            a for a in completed
            if (c := parse_dt(a.get("completed_at") or a.get("updated_at"))) is not None
            and c >= since
        ),
        key=lambda a: parse_dt(a.get("completed_at") or a.get("updated_at")) or now,
        reverse=True,
    )

    # Open for more than two cadences with no movement — the quiet killers.
    stale = sorted(
        (a for a in live if action_age_days(a, now) >= 30),
        key=lambda a: -action_age_days(a, now),
    )

    closed_total = len(completed) + len(dropped)
    resolved_or_live = len(completed) + len(live)
    completion_rate = round(100 * len(completed) / resolved_or_live) if resolved_or_live else 0

    return {
        "completed": sorted(
            completed,
            key=lambda a: parse_dt(a.get("completed_at") or a.get("updated_at")) or now,
            reverse=True,
        ),
        "in_process": sorted(in_process, key=lambda a: _sort_key(a, now)),
        "incomplete": sorted(incomplete, key=lambda a: _sort_key(a, now)),
        "dropped": dropped,
        "overdue": overdue,
        "due_this_week": due_this_week,
        "recent_wins": recent_wins,
        "stale": stale,
        "counts": {
            "completed": len(completed),
            "in_process": len(in_process),
            "incomplete": len(incomplete),
            "dropped": len(dropped),
            "open_total": len(live),
            "overdue": len(overdue),
            "closed_total": closed_total,
            "completion_rate": completion_rate,
        },
    }


def commitments_from_last_week(
    actions: list[dict],
    now: datetime | None = None,
    days: int = 7,
    since: datetime | None = None,
) -> list[dict]:
    """What the client actually signed up for in the past week — the list Pete
    opens the next call with.

    An action counts as a past-week commitment if it was created in the window,
    came due in the window, or was closed out in the window. Each row carries
    the verdict (`kept` / `working` / `missed`) so the coach doesn't have to
    re-derive it mid-call.

    The window defaults to the trailing `days`, which is what the Monday report
    wants. Pass `since` to widen it back to the previous session: at a
    fortnightly cadence a flat seven days would miss every commitment made at
    the last call, which is precisely the list the next call opens with. The
    window only ever grows — an unusually recent session never shortens it.
    """
    now = now or now_utc()
    default_since, _ = review_window(now, days)
    since = min(since, default_since) if since else default_since
    rows = []

    for a in actions or []:
        created = parse_dt(a.get("created_at"))
        due = parse_dt(a.get("due_date"))
        closed = parse_dt(a.get("completed_at"))
        in_window = any(
            d is not None and since <= d <= now for d in (created, due, closed)
        )
        # A live item that came due before the window opened is still owed.
        overdue_carry = is_open(a) and due is not None and due < since
        if not (in_window or overdue_carry):
            continue

        st = normalize_status(a.get("status"))
        if st == STATUS_COMPLETE:
            verdict = "kept"
        elif st == STATUS_DROPPED:
            verdict = "dropped"
        elif st == STATUS_IN_PROGRESS:
            verdict = "working"
        elif due is not None and due < now:
            verdict = "missed"
        else:
            verdict = "pending"

        rows.append({
            "action_id": a.get("action_id"),
            "title": a.get("title") or "(untitled commitment)",
            "detail": a.get("detail") or "",
            "owner": normalize_owner(a.get("owner")),
            "status": st,
            "status_label": STATUS_LABELS[st],
            "verdict": verdict,
            "due_date": a.get("due_date"),
            "due_label": fmt_day(a.get("due_date")) if a.get("due_date") else "",
            "days_overdue": days_overdue(a, now),
            "session_id": a.get("session_id"),
        })

    order = {"missed": 0, "working": 1, "pending": 2, "kept": 3, "dropped": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -r["days_overdue"], r["title"]))
    return rows


# ------------------------------------------------------------- trajectory

def trajectory(
    sessions: list[dict],
    actions: list[dict],
    now: datetime | None = None,
    cadence_days: int = DEFAULT_CADENCE_DAYS,
) -> dict:
    """Where the engagement is heading, scored 0-100 from four observable
    signals. Deterministic on purpose: the number has to mean the same thing
    every week, and it has to keep working when the LLM is unreachable.

      follow-through (0-40)  completion rate on assigned commitments
      freshness      (0-25)  is anything overdue, and by how long
      momentum       (0-20)  completions in the last 14d vs the 14d before
      rhythm         (0-15)  are sessions happening on the agreed cadence

    `coaching_ai.trajectory_narrative()` layers prose on top of this; the
    score itself never depends on the model.
    """
    now = now or now_utc()
    cadence = max(1, int(cadence_days or DEFAULT_CADENCE_DAYS))
    buckets = bucket_actions(actions, now)
    counts = buckets["counts"]
    signals: list[str] = []
    risks: list[str] = []

    # --- follow-through -------------------------------------------------
    assigned = counts["completed"] + counts["open_total"]
    if assigned:
        rate = counts["completed"] / assigned
        follow_through = 40 * rate
        pct = round(rate * 100)
        if pct >= 70:
            signals.append(f"Closing {pct}% of commitments — follow-through is strong.")
        elif pct >= 40:
            signals.append(f"Closing {pct}% of commitments.")
        else:
            risks.append(f"Only {pct}% of commitments are getting closed.")
    else:
        # No commitments on the board at all is its own problem.
        follow_through = 20.0
        risks.append("No open commitments on record — nothing is being tracked between calls.")

    # --- freshness ------------------------------------------------------
    overdue = buckets["overdue"]
    if not overdue:
        freshness = 25.0
        if counts["open_total"]:
            signals.append("Nothing overdue.")
    else:
        worst = max(days_overdue(a, now) for a in overdue)
        # Full credit at 0 days late, zero credit once ~3 weeks late.
        freshness = max(0.0, 25.0 * (1 - min(worst, 21) / 21))
        risks.append(
            f"{len(overdue)} item{'s' if len(overdue) != 1 else ''} overdue, "
            f"the oldest by {worst} day{'s' if worst != 1 else ''}."
        )

    # --- momentum -------------------------------------------------------
    def _closed_between(start: datetime, end: datetime) -> int:
        n = 0
        for a in actions or []:
            if normalize_status(a.get("status")) != STATUS_COMPLETE:
                continue
            c = parse_dt(a.get("completed_at") or a.get("updated_at"))
            if c and start <= c < end:
                n += 1
        return n

    recent = _closed_between(now - timedelta(days=14), now)
    prior = _closed_between(now - timedelta(days=28), now - timedelta(days=14))
    if recent > prior:
        momentum = 20.0
        signals.append(f"Momentum building — {recent} closed in the last two weeks vs {prior} before.")
    elif recent == prior and recent > 0:
        momentum = 14.0
        signals.append(f"Holding a steady {recent} closed per fortnight.")
    elif recent == prior == 0:
        momentum = 6.0
        risks.append("Nothing has been closed out in four weeks.")
    else:
        momentum = 6.0
        risks.append(f"Output slipping — {recent} closed in the last two weeks vs {prior} before.")

    # --- rhythm ---------------------------------------------------------
    dated = sorted(
        (d for s in sessions or [] if (d := parse_dt(s.get("occurred_at")))),
        reverse=True,
    )
    if dated:
        gap = days_between(now, dated[0])
        if gap <= cadence:
            rhythm = 15.0
        elif gap <= cadence * 2:
            rhythm = 8.0
            risks.append(f"Last session was {gap} days ago — past the {cadence}-day cadence.")
        else:
            rhythm = 2.0
            risks.append(f"Last session was {gap} days ago. The engagement has gone quiet.")
    else:
        gap = None
        rhythm = 7.0
        risks.append("No sessions logged yet.")

    score = round(follow_through + freshness + momentum + rhythm)
    score = max(0, min(100, score))
    direction, label = next((k, lb) for floor, k, lb in _TRAJECTORY_BANDS if score >= floor)

    return {
        "score": score,
        "direction": direction,
        "direction_label": label,
        "components": {
            "follow_through": round(follow_through, 1),
            "freshness": round(freshness, 1),
            "momentum": round(momentum, 1),
            "rhythm": round(rhythm, 1),
        },
        "signals": signals,
        "risks": risks,
        "sessions_logged": len(dated),
        "days_since_last_session": gap,
        "completion_rate": counts["completion_rate"],
        "computed_at": iso(now),
    }


# ------------------------------------------------------- running narrative

def theme_frequency(sessions: list[dict], limit: int = 8) -> list[dict]:
    """Which subjects keep coming back. Counts the tags the AI (or the coach)
    attached to each session, most recent sessions weighted first."""
    tally: dict[str, dict] = {}
    for s in sessions or []:
        when = parse_dt(s.get("occurred_at"))
        for raw in s.get("themes") or []:
            theme = str(raw).strip()
            if not theme:
                continue
            key = theme.lower()
            row = tally.setdefault(key, {"theme": theme, "count": 0, "last_seen": None})
            row["count"] += 1
            if when and (row["last_seen"] is None or when > row["last_seen"]):
                row["last_seen"] = when
    rows = sorted(
        tally.values(),
        key=lambda r: (-r["count"], -(r["last_seen"].timestamp() if r["last_seen"] else 0)),
    )
    for r in rows:
        r["last_seen"] = iso(r["last_seen"]) if r["last_seen"] else None
    return rows[:limit]


def fallback_running_summary(
    client: dict,
    sessions: list[dict],
    actions: list[dict],
    now: datetime | None = None,
) -> str:
    """A readable running summary assembled without the model. This is what
    the client sees if the LLM key is missing or the call fails — thinner than
    the generated version, never blank, never wrong."""
    now = now or now_utc()
    name = client.get("name") or "This client"
    dated = sorted(
        (s for s in sessions or [] if parse_dt(s.get("occurred_at"))),
        key=lambda s: parse_dt(s.get("occurred_at")),
        reverse=True,
    )
    counts = bucket_actions(actions, now)["counts"]
    parts = []

    if dated:
        first = parse_dt(dated[-1]["occurred_at"])
        parts.append(
            f"{name} has had {len(dated)} coaching session"
            f"{'s' if len(dated) != 1 else ''} since {fmt_day(first)}, "
            f"most recently on {fmt_day(dated[0]['occurred_at'])}."
        )
    else:
        parts.append(f"{name} has no coaching sessions logged yet.")

    themes = theme_frequency(dated, limit=4)
    if themes:
        parts.append(
            "Recurring subjects: " + ", ".join(t["theme"] for t in themes) + "."
        )

    objectives = [o for o in (client.get("objectives") or []) if str(o).strip()]
    if objectives:
        parts.append("Stated objectives: " + "; ".join(str(o) for o in objectives) + ".")

    parts.append(
        f"{counts['completed']} commitment{'s' if counts['completed'] != 1 else ''} completed, "
        f"{counts['in_process']} in process, {counts['incomplete']} still incomplete"
        + (f", {counts['overdue']} overdue." if counts["overdue"] else ".")
    )

    latest_summary = next(
        (s.get("summary") for s in dated if str(s.get("summary") or "").strip()), ""
    )
    if latest_summary:
        parts.append("Last session: " + str(latest_summary).strip())

    return " ".join(parts)


# --------------------------------------------------------------- meetings

def next_meeting(meetings: list[dict], now: datetime | None = None) -> dict | None:
    now = now or now_utc()
    upcoming = [
        m for m in meetings or []
        if (d := parse_dt(m.get("starts_at"))) is not None
        and d >= now
        and not m.get("cancelled")
    ]
    return min(upcoming, key=lambda m: parse_dt(m["starts_at"])) if upcoming else None


def last_session(sessions: list[dict], now: datetime | None = None) -> dict | None:
    now = now or now_utc()
    past = [
        s for s in sessions or []
        if (d := parse_dt(s.get("occurred_at"))) is not None and d <= now
    ]
    return max(past, key=lambda s: parse_dt(s["occurred_at"])) if past else None


# ------------------------------------------------------------ agenda build

def _checklist_item(kind: str, label: str, detail: str = "", ref: str = "") -> dict:
    """Stable id so the UI can remember which boxes the coach already ticked
    across a page refresh."""
    seed = f"{kind}:{ref or label}".encode("utf-8")
    return {
        "id": hashlib.sha1(seed).hexdigest()[:12],
        "kind": kind,
        "label": label,
        "detail": detail,
        "ref": ref,
    }


def build_agenda(
    *,
    client: dict,
    sessions: list[dict],
    actions: list[dict],
    meeting: dict | None = None,
    now: datetime | None = None,
    running_summary: str = "",
) -> dict:
    """The prep sheet for one upcoming call: what they committed to last week,
    what's still open, what to celebrate, and the checklist to run the call
    from. Fully deterministic — `coaching_ai` may add prose, never structure.
    """
    now = now or now_utc()
    buckets = bucket_actions(actions, now)
    traj = trajectory(sessions, actions, now, client.get("cadence_days") or DEFAULT_CADENCE_DAYS)
    prev = last_session(sessions, now)

    # Review everything since the last conversation, never less than a week and
    # never more than 60 days — beyond that it stops being a review and starts
    # being an audit.
    prev_at = parse_dt((prev or {}).get("occurred_at"))
    floor = now - timedelta(days=60)
    commitments = commitments_from_last_week(
        actions, now, since=max(prev_at, floor) if prev_at else None
    )
    meeting = meeting or next_meeting([], now)

    checklist: list[dict] = []

    # 1. Hold them to last week's word. This is the top of every call.
    owed = [c for c in commitments if c["verdict"] in ("missed", "working", "pending")
            and c["owner"] == OWNER_CLIENT]
    for c in owed[:8]:
        if c["verdict"] == "missed":
            label = f"Missed: {c['title']}"
            detail = (
                f"Due {c['due_label']} — {c['days_overdue']} day"
                f"{'s' if c['days_overdue'] != 1 else ''} past. Ask what got in the way."
            )
        elif c["verdict"] == "working":
            label = f"In process: {c['title']}"
            detail = "Ask for the specific next step and a date."
        else:
            label = f"Committed: {c['title']}"
            detail = f"Due {c['due_label']}." if c["due_label"] else "No date set — set one."
        checklist.append(_checklist_item("commitment", label, detail, c["action_id"] or c["title"]))

    # 2. Open with a win — a completed item is the cheapest momentum there is.
    for w in buckets["recent_wins"][:3]:
        checklist.append(_checklist_item(
            "win",
            f"Acknowledge: {w.get('title')}",
            "Completed since the last call.",
            w.get("action_id") or str(w.get("title")),
        ))

    # 3. Anything the coach owes the client — credibility runs both ways.
    coach_owes = [a for a in buckets["in_process"] + buckets["incomplete"]
                  if normalize_owner(a.get("owner")) == OWNER_COACH]
    for a in coach_owes[:4]:
        checklist.append(_checklist_item(
            "coach_task",
            f"You owe them: {a.get('title')}",
            f"Due {fmt_day(a.get('due_date'))}." if a.get("due_date") else "No date set.",
            a.get("action_id") or str(a.get("title")),
        ))

    # 4. Items rotting on the board.
    for a in buckets["stale"][:3]:
        age = action_age_days(a, now)
        checklist.append(_checklist_item(
            "stale",
            f"Still open after {age} days: {a.get('title')}",
            "Re-commit with a date, hand it to someone else, or drop it.",
            a.get("action_id") or str(a.get("title")),
        ))

    # 5. Objectives that haven't surfaced in recent conversation.
    recent_text = " ".join(
        str(s.get("summary") or "") + " " + " ".join(str(t) for t in (s.get("themes") or []))
        for s in sorted(
            (s for s in sessions or [] if parse_dt(s.get("occurred_at"))),
            key=lambda s: parse_dt(s["occurred_at"]),
            reverse=True,
        )[:3]
    ).lower()
    untouched = 0
    for obj in (client.get("objectives") or []):
        if untouched >= 2:  # two is a prompt; five is a lecture
            break
        text = str(obj).strip()
        if not text:
            continue
        keywords = [w for w in re.findall(r"[a-z]{5,}", text.lower())][:4]
        if keywords and not any(k in recent_text for k in keywords):
            untouched += 1
            checklist.append(_checklist_item(
                "objective",
                f"Untouched objective: {text}",
                "Hasn't come up in the last three sessions.",
                text,
            ))

    # 6. Trajectory flags worth naming out loud.
    for risk in traj["risks"][:3]:
        checklist.append(_checklist_item("risk", risk, "", risk))

    return {
        "client_id": client.get("client_id"),
        "client_name": client.get("name"),
        "generated_at": iso(now),
        "meeting": {
            "meeting_id": (meeting or {}).get("meeting_id"),
            "title": (meeting or {}).get("title") or f"Coaching — {client.get('name')}",
            "starts_at": (meeting or {}).get("starts_at"),
            "when_label": fmt_when((meeting or {}).get("starts_at")) if meeting else "unscheduled",
            "location": (meeting or {}).get("location") or "",
        } if meeting else None,
        "last_session": {
            "session_id": prev.get("session_id"),
            "occurred_at": prev.get("occurred_at"),
            "when_label": fmt_day(prev.get("occurred_at")),
            "title": prev.get("title") or "",
            "summary": prev.get("summary") or "",
            "themes": prev.get("themes") or [],
        } if prev else None,
        "running_summary": running_summary or "",
        "commitments_review": commitments,
        "open_items": buckets["in_process"] + buckets["incomplete"],
        "wins": buckets["recent_wins"],
        "overdue": buckets["overdue"],
        "due_this_week": buckets["due_this_week"],
        "counts": buckets["counts"],
        "trajectory": traj,
        "themes": theme_frequency(sessions),
        "checklist": checklist,
    }


# --------------------------------------------------------------- rendering

def render_agenda_text(agenda: dict) -> str:
    """Plain-text agenda. This is the exact block that gets written into the
    calendar event description, so it has to read well in Google Calendar's
    tiny monospace box — no markdown, no HTML, hard-wrapped by the reader."""
    lines: list[str] = []
    name = agenda.get("client_name") or "Client"
    meeting = agenda.get("meeting") or {}
    traj = agenda.get("trajectory") or {}
    counts = agenda.get("counts") or {}

    lines.append(f"COACHING PREP — {name}")
    if meeting.get("when_label"):
        lines.append(meeting["when_label"])
    lines.append(
        f"Trajectory: {traj.get('direction_label', 'Unknown')} ({traj.get('score', 0)}/100) · "
        f"{counts.get('completed', 0)} completed / {counts.get('in_process', 0)} in process / "
        f"{counts.get('incomplete', 0)} incomplete"
    )
    lines.append("")

    if agenda.get("running_summary"):
        lines.append("WHERE THINGS STAND")
        lines.append(str(agenda["running_summary"]).strip())
        lines.append("")

    review = agenda.get("commitments_review") or []
    if review:
        lines.append("LAST WEEK'S COMMITMENTS")
        marks = {"kept": "[x]", "missed": "[!]", "working": "[~]", "pending": "[ ]", "dropped": "[-]"}
        for c in review:
            suffix = ""
            if c["verdict"] == "missed" and c["days_overdue"]:
                suffix = f" ({c['days_overdue']}d late)"
            elif c.get("due_label"):
                suffix = f" (due {c['due_label']})"
            who = "" if c["owner"] == OWNER_CLIENT else " [yours]"
            lines.append(f"  {marks.get(c['verdict'], '[ ]')} {c['title']}{suffix}{who}")
        lines.append("")

    checklist = agenda.get("checklist") or []
    if checklist:
        lines.append("DISCUSS ON THIS CALL")
        for i, item in enumerate(checklist, 1):
            lines.append(f"  {i}. {item['label']}")
            if item.get("detail"):
                lines.append(f"     {item['detail']}")
        lines.append("")

    open_items = agenda.get("open_items") or []
    if open_items:
        lines.append("OPEN ITEMS")
        for a in open_items[:12]:
            due = f" — due {fmt_day(a.get('due_date'))}" if a.get("due_date") else ""
            lines.append(f"  · [{status_label(a.get('status'))}] {a.get('title')}{due}")
        lines.append("")

    last = agenda.get("last_session")
    if last and last.get("summary"):
        lines.append(f"LAST SESSION ({last.get('when_label')})")
        lines.append(str(last["summary"]).strip())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# -------------------------------------------------------------------- ICS

_ICS_ESCAPES = (("\\", "\\\\"), (";", "\\;"), (",", "\\,"))


def ics_escape(text: str) -> str:
    out = str(text or "")
    for raw, esc in _ICS_ESCAPES:
        out = out.replace(raw, esc)
    return out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def ics_fold(line: str) -> str:
    """RFC 5545 §3.1: content lines wrap at 75 octets, continuations start
    with a single space. Folded on byte boundaries so multi-byte characters
    survive the split."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, start = [], 0
    limit = 75
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Back off so we never cut mid-codepoint.
        while end > start and end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines carry a leading space
    return "\r\n ".join(chunks)


def _ics_stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(calendar_name: str, events: list[dict], now: datetime | None = None) -> str:
    """Serialise coaching meetings as a subscribable calendar.

    Each event dict: uid, starts_at, ends_at, title, description, location.
    Google Calendar refreshes external ICS subscriptions on its own slow
    schedule (often several hours) — for same-day agenda edits the webhook
    push in `coaching_calendar.py` is the surface that updates in real time.
    """
    now = now or now_utc()
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//The Housing News//Coaching Dashboard//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        "X-PUBLISHED-TTL:PT1H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    ]
    for ev in events or []:
        start = parse_dt(ev.get("starts_at"))
        if not start:
            continue
        end = parse_dt(ev.get("ends_at")) or (start + timedelta(hours=1))
        out += [
            "BEGIN:VEVENT",
            f"UID:{ics_escape(ev.get('uid') or _ics_stamp(start))}",
            f"DTSTAMP:{_ics_stamp(now)}",
            f"DTSTART:{_ics_stamp(start)}",
            f"DTEND:{_ics_stamp(end)}",
            f"SUMMARY:{ics_escape(ev.get('title') or 'Coaching session')}",
        ]
        if ev.get("description"):
            out.append(f"DESCRIPTION:{ics_escape(ev['description'])}")
        if ev.get("location"):
            out.append(f"LOCATION:{ics_escape(ev['location'])}")
        out.append("STATUS:CONFIRMED")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(line) for line in out) + "\r\n"
