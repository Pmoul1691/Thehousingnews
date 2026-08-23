"""Unit tests for the coaching dashboard's domain logic.

`services.coaching_core` is stdlib-only by design, so these run with no Mongo,
no FastAPI, no network and no LLM key:

    pytest backend/tests/test_coaching_core.py --noconftest

(`--noconftest` because the repo's shared conftest bootstraps a live server and
Mongo for the integration suites; nothing here needs either.)

They pin the two things most likely to be got subtly wrong: the trajectory
formula (a score that quietly changes meaning is worse than no score) and the
calendar-note merge (a block that stacks instead of replacing turns a coaching
invite into a wall of duplicated agendas).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import coaching_core as core  # noqa: E402

NOW = datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc)


def at(days: float) -> str:
    """ISO timestamp `days` from NOW (negative is the past)."""
    return core.iso(NOW + timedelta(days=days))


def action(action_id, *, status="open", owner="client", created=-9,
           due=None, completed=None, title=None):
    return {
        "action_id": action_id,
        "client_id": "cli_1",
        "session_id": "ses_1",
        "title": title or f"Item {action_id}",
        "owner": owner,
        "status": status,
        "created_at": at(created),
        "due_date": at(due) if due is not None else None,
        "completed_at": at(completed) if completed is not None else None,
    }


def session(session_id, *, days_ago, summary="", themes=()):
    return {
        "session_id": session_id,
        "client_id": "cli_1",
        "occurred_at": at(-days_ago),
        "title": "Coaching session",
        "summary": summary,
        "themes": list(themes),
    }


CLIENT = {"client_id": "cli_1", "name": "Sarah Chen", "cadence_days": 14,
          "objectives": ["Close 24 units in 2026", "Hire a transaction coordinator"]}


# ------------------------------------------------------------ status parsing

@pytest.mark.parametrize("raw,expected", [
    ("done", core.STATUS_COMPLETE),
    ("Completed", core.STATUS_COMPLETE),
    ("in progress", core.STATUS_IN_PROGRESS),
    ("in_process", core.STATUS_IN_PROGRESS),
    ("In Process", core.STATUS_IN_PROGRESS),
    ("todo", core.STATUS_OPEN),
    ("incomplete", core.STATUS_OPEN),
    ("cancelled", core.STATUS_DROPPED),
    ("", core.STATUS_OPEN),
    (None, core.STATUS_OPEN),
    ("something nobody wrote", core.STATUS_OPEN),
])
def test_status_aliases_normalise(raw, expected):
    assert core.normalize_status(raw) == expected


def test_status_labels_are_petes_vocabulary():
    assert core.status_label("open") == "Incomplete"
    assert core.status_label("in_progress") == "In process"
    assert core.status_label("done") == "Completed"


def test_owner_defaults_to_client():
    assert core.normalize_owner("coach") == core.OWNER_COACH
    assert core.normalize_owner("Pete") == core.OWNER_COACH
    assert core.normalize_owner("") == core.OWNER_CLIENT
    assert core.normalize_owner("anyone else") == core.OWNER_CLIENT


def test_parse_dt_survives_garbage():
    assert core.parse_dt("2026-08-23T15:00:00Z") == NOW
    assert core.parse_dt("2026-08-23").date().isoformat() == "2026-08-23"
    assert core.parse_dt("not a date") is None
    assert core.parse_dt(None) is None
    assert core.parse_dt("") is None


# -------------------------------------------------------------- bucketing

def test_bucket_actions_splits_into_the_three_visible_states():
    actions = [
        action("a1", status="complete", completed=-2),
        action("a2", status="in_progress"),
        action("a3", status="open"),
        action("a4", status="dropped"),
    ]
    counts = core.bucket_actions(actions, NOW)["counts"]
    assert counts["completed"] == 1
    assert counts["in_process"] == 1
    assert counts["incomplete"] == 1
    assert counts["dropped"] == 1
    # A dropped item is not "open work" and does not drag follow-through down.
    assert counts["open_total"] == 2
    assert counts["completion_rate"] == 33


def test_overdue_counts_only_live_items():
    actions = [
        action("late", status="open", due=-5),
        action("done_late", status="complete", due=-5, completed=-1),
        action("future", status="open", due=+3),
    ]
    buckets = core.bucket_actions(actions, NOW)
    assert [a["action_id"] for a in buckets["overdue"]] == ["late"]
    assert [a["action_id"] for a in buckets["due_this_week"]] == ["future"]


def test_recent_wins_window_is_seven_days():
    actions = [
        action("fresh", status="complete", completed=-3),
        action("stale_win", status="complete", completed=-20),
    ]
    wins = core.bucket_actions(actions, NOW)["recent_wins"]
    assert [a["action_id"] for a in wins] == ["fresh"]


def test_stale_items_are_open_and_over_thirty_days():
    actions = [
        action("old", status="open", created=-45),
        action("recent", status="open", created=-5),
        action("old_but_done", status="complete", created=-45, completed=-1),
    ]
    assert [a["action_id"] for a in core.bucket_actions(actions, NOW)["stale"]] == ["old"]


# ------------------------------------------------------------- commitments

def test_commitment_verdicts():
    actions = [
        action("kept", status="complete", completed=-2),
        action("missed", status="open", due=-3),
        action("working", status="in_progress", due=+2, created=-3),
        action("pending", status="open", due=+4, created=-2),
        action("ancient", status="complete", created=-90, completed=-80),
    ]
    rows = {r["action_id"]: r for r in core.commitments_from_last_week(actions, NOW)}
    assert rows["kept"]["verdict"] == "kept"
    assert rows["missed"]["verdict"] == "missed"
    assert rows["missed"]["days_overdue"] == 3
    assert rows["working"]["verdict"] == "working"
    assert rows["pending"]["verdict"] == "pending"
    # Closed out three months ago — not part of "the past week".
    assert "ancient" not in rows


def test_review_window_widens_back_to_the_last_session():
    """At a fortnightly cadence a flat seven days misses everything agreed at
    the last call — which is exactly the list the next call opens with."""
    agreed_last_session = action("from_last_call", status="in_progress", created=-12, due=+2)
    assert core.commitments_from_last_week([agreed_last_session], NOW) == []
    widened = core.commitments_from_last_week(
        [agreed_last_session], NOW, since=NOW - timedelta(days=13)
    )
    assert [r["action_id"] for r in widened] == ["from_last_call"]


def test_review_window_never_shrinks_below_a_week():
    """A session two days ago must not hide a commitment made five days ago."""
    recent = action("five_days_old", status="open", created=-5, due=+1)
    rows = core.commitments_from_last_week([recent], NOW, since=NOW - timedelta(days=2))
    assert [r["action_id"] for r in rows] == ["five_days_old"]


def test_agenda_review_covers_the_whole_gap_since_the_last_session():
    actions = [action("from_last_call", status="in_progress", created=-12, due=+2)]
    agenda = core.build_agenda(
        client=CLIENT, sessions=[session("s1", days_ago=13)], actions=actions, now=NOW,
    )
    assert [r["action_id"] for r in agenda["commitments_review"]] == ["from_last_call"]


def test_missed_commitments_sort_first():
    actions = [
        action("kept", status="complete", completed=-1),
        action("missed", status="open", due=-6),
    ]
    rows = core.commitments_from_last_week(actions, NOW)
    assert rows[0]["action_id"] == "missed"


def test_overdue_carry_survives_past_the_window():
    """An item that came due before the window opened is still owed."""
    rows = core.commitments_from_last_week([action("old_debt", status="open", due=-30)], NOW)
    assert [r["action_id"] for r in rows] == ["old_debt"]
    assert rows[0]["verdict"] == "missed"


# -------------------------------------------------------------- trajectory

def test_trajectory_components_are_capped_and_sum_to_the_score():
    sessions = [session("s1", days_ago=3)]
    actions = [action(f"a{i}", status="complete", completed=-2) for i in range(5)]
    traj = core.trajectory(sessions, actions, NOW, cadence_days=14)
    parts = traj["components"]
    assert parts["follow_through"] <= 40
    assert parts["freshness"] <= 25
    assert parts["momentum"] <= 20
    assert parts["rhythm"] <= 15
    assert traj["score"] == round(sum(parts.values()))
    assert 0 <= traj["score"] <= 100


def test_perfect_engagement_reads_as_accelerating():
    sessions = [session("s1", days_ago=2), session("s0", days_ago=16)]
    actions = [action(f"a{i}", status="complete", completed=-3) for i in range(4)]
    traj = core.trajectory(sessions, actions, NOW, cadence_days=14)
    assert traj["direction"] == "accelerating"
    assert traj["direction_label"] == "Accelerating"
    assert traj["risks"] == []


def test_abandoned_engagement_reads_as_stalled():
    sessions = [session("s1", days_ago=70)]
    actions = [action(f"a{i}", status="open", due=-40, created=-70) for i in range(4)]
    traj = core.trajectory(sessions, actions, NOW, cadence_days=14)
    assert traj["direction"] == "stalled"
    assert traj["score"] < 35
    assert any("overdue" in r for r in traj["risks"])
    assert any("quiet" in r or "days ago" in r for r in traj["risks"])


def test_trajectory_bands_are_contiguous():
    """Every score from 0 to 100 lands in exactly one band."""
    for score in range(101):
        matches = [k for floor, k, _ in core._TRAJECTORY_BANDS if score >= floor]
        assert matches, f"score {score} matched no band"


def test_trajectory_handles_a_brand_new_client():
    traj = core.trajectory([], [], NOW, cadence_days=14)
    assert 0 <= traj["score"] <= 100
    assert traj["sessions_logged"] == 0
    assert traj["days_since_last_session"] is None
    assert any("No sessions" in r for r in traj["risks"])


def test_reopening_a_completed_item_removes_it_from_momentum():
    done = [action("a1", status="complete", completed=-2)]
    reopened = [dict(done[0], status="open", completed_at=None)]
    assert core.trajectory([], done, NOW)["score"] > core.trajectory([], reopened, NOW)["score"]


# ------------------------------------------------------------------ agenda

def test_agenda_leads_with_missed_commitments():
    actions = [
        action("missed", status="open", due=-4, title="Interview 3 TC candidates"),
        action("win", status="complete", completed=-2, title="Send Q3 email"),
    ]
    agenda = core.build_agenda(
        client=CLIENT, sessions=[session("s1", days_ago=8)], actions=actions, now=NOW,
    )
    assert agenda["checklist"][0]["kind"] == "commitment"
    assert "Interview 3 TC candidates" in agenda["checklist"][0]["label"]
    kinds = [i["kind"] for i in agenda["checklist"]]
    assert "win" in kinds


def test_agenda_flags_what_the_coach_owes():
    actions = [action("mine", status="open", owner="coach", title="Send the referral script")]
    agenda = core.build_agenda(client=CLIENT, sessions=[], actions=actions, now=NOW)
    coach_items = [i for i in agenda["checklist"] if i["kind"] == "coach_task"]
    assert len(coach_items) == 1
    assert "Send the referral script" in coach_items[0]["label"]


def test_agenda_caps_untouched_objectives_at_two():
    client = dict(CLIENT, objectives=[f"Objective number {i} about widgets" for i in range(6)])
    agenda = core.build_agenda(client=client, sessions=[], actions=[], now=NOW)
    assert sum(1 for i in agenda["checklist"] if i["kind"] == "objective") <= 2


def test_checklist_ids_are_stable_across_rebuilds():
    actions = [action("a1", status="open", due=-2)]
    kwargs = dict(client=CLIENT, sessions=[session("s1", days_ago=5)], actions=actions, now=NOW)
    first = core.build_agenda(**kwargs)["checklist"]
    second = core.build_agenda(**kwargs)["checklist"]
    assert [i["id"] for i in first] == [i["id"] for i in second]
    assert len({i["id"] for i in first}) == len(first)


def test_agenda_survives_an_empty_client():
    agenda = core.build_agenda(client={"client_id": "x", "name": "New"}, sessions=[], actions=[], now=NOW)
    assert agenda["counts"]["open_total"] == 0
    assert agenda["meeting"] is None
    assert agenda["last_session"] is None
    assert core.render_agenda_text(agenda).startswith("COACHING PREP")


def test_rendered_agenda_marks_each_verdict():
    actions = [
        action("kept", status="complete", completed=-1, title="Did the thing"),
        action("missed", status="open", due=-3, title="Skipped the thing"),
    ]
    text = core.render_agenda_text(
        core.build_agenda(client=CLIENT, sessions=[], actions=actions, now=NOW)
    )
    assert "[x] Did the thing" in text
    assert "[!] Skipped the thing" in text
    assert "DISCUSS ON THIS CALL" in text


# --------------------------------------------------------------------- ICS

def test_ics_escapes_the_reserved_characters():
    assert core.ics_escape("a;b,c") == "a\\;b\\,c"
    assert core.ics_escape("back\\slash") == "back\\\\slash"
    assert core.ics_escape("line\nbreak") == "line\\nbreak"


def test_ics_folds_long_lines_without_splitting_codepoints():
    folded = core.ics_fold("DESCRIPTION:" + "é" * 200)
    for chunk in folded.split("\r\n"):
        assert len(chunk.encode("utf-8")) <= 75
    assert folded.replace("\r\n ", "") == "DESCRIPTION:" + "é" * 200


def test_build_ics_emits_a_parseable_calendar():
    ics = core.build_ics("Coaching", [{
        "uid": "m1", "starts_at": at(2), "ends_at": at(2.05),
        "title": "Coaching — Sarah", "description": "Line one\nLine two", "location": "Zoom",
    }], NOW)
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 1
    assert "UID:m1" in ics
    assert "\\n" in ics  # the description newline was escaped, not emitted raw


def test_build_ics_skips_events_with_no_start():
    ics = core.build_ics("Coaching", [{"uid": "bad", "title": "No date"}], NOW)
    assert "BEGIN:VEVENT" not in ics
