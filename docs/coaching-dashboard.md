# Coaching client dashboard — reference implementation

The production build of this system lives in the **Ultradian Partners** Replit
app, not in this repository. What is on this branch is the reference
implementation: the domain logic that specifies how the system behaves, written
and verified here before being handed to the Replit build.

Keep it if you ever want to self-host the coaching dashboard alongside The
Housing News. Otherwise it stands as the executable spec — in particular the
trajectory formula and the calendar-note merge, both of which are easy to get
subtly wrong and are pinned by tests here.

## What the system does

One dashboard per coaching client, plus a master dashboard for the coach.

- **Per client** — every past session with an AI summary, one running narrative
  of the whole engagement, and action items in three states: completed, in
  process, incomplete.
- **Trajectory** — a 0-100 score for where the engagement is heading, computed
  arithmetically so it means the same thing every week and keeps working when
  the model is unavailable. The LLM explains the score; it never sets it.
- **Master dashboard** — every client, worst trajectory first, each with last
  week's commitments (verdicted kept / working / pending / missed) and a
  generated checklist for the next call.
- **Monday 9:00 AM CT** — the whole book in one email.
- **Four hours before each session** — that call's prep sheet by email.
- **Calendar** — the agenda written into each coaching event's description.

## Module map

| Module | Responsibility |
| --- | --- |
| `services/coaching_core.py` | All domain logic. Stdlib-only, pure functions, fully unit-tested. |
| `services/coaching_ai.py` | Claude enrichment. Every call degrades to a `coaching_core` fallback. |
| `services/coaching_store.py` | Mongo reads/writes and the cached per-client snapshot. |
| `services/coaching_calendar.py` | ICS feeds, the marker-wrapped note block, webhook push. |
| `services/coaching_email.py` | The Monday report and the four-hour prep brief. |
| `routes/coaching.py` | Coach-side API (admin-gated). |
| `routes/coaching_portal.py` | Client-side API (token-authenticated). |

## Design decisions worth preserving

**The trajectory score is arithmetic, not generated.** Four components sum to
100: follow-through (40), freshness (25), momentum (20), rhythm (15). A number
that drifts because a model was in a different mood is worse than no number.

**Three states the user sees, four in the data.** `dropped` exists so a
deliberately abandoned commitment stops counting against follow-through
forever, without being silently deleted.

**The client sees less than the coach.** No trajectory score, no prep
checklist, no raw notes. A number grading the relationship should not sit in
front of the person being graded unless the coach chooses to share it.

**The portal token is the credential.** 32 bytes of `token_urlsafe`, unique per
client, rotatable. A bad token and an archived client return the identical
404 — a dead link must never confirm it was once valid.

**Everything that sends is idempotent.** The prep mail stamps `prep_sent_at`;
the weekly report stamps a per-week key; the calendar note is wrapped in
markers so re-syncing replaces the block instead of stacking a second copy.

**Nothing contacts a client automatically.** The portal-invite email is an
explicit button on the coach's side.

## Configuration

| Variable | Purpose |
| --- | --- |
| `EMERGENT_LLM_KEY` | Enables summaries, running narrative and trajectory prose. Unset degrades to deterministic fallbacks. |
| `COACHING_COACH_EMAIL` | Fallback recipient when a client carries no `coach_user_id`. |
| `COACHING_PREP_LEAD_HOURS` | Hours before a session to send the prep brief. Defaults to 4. |
| `COACHING_CALENDAR_TOKEN` | Secret guarding the coach's ICS feed. Unset closes the endpoint. |
| `COACHING_CALENDAR_WEBHOOK_URL` | Optional. Where to push the agenda so an automation writes it onto the real calendar event. |
| `COACHING_CALENDAR_WEBHOOK_SECRET` | Optional shared secret for that webhook. |

## Tests

`backend/tests/test_coaching_core.py` runs without Mongo, FastAPI or a network
connection — the core module is stdlib-only by design.
