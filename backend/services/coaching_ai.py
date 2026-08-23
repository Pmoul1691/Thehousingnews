"""Claude-backed enrichment for the coaching dashboard.

Three jobs, all optional:

  summarize_session()     raw notes / transcript -> summary, themes, action items
  running_summary()       every session so far    -> one evolving narrative
  trajectory_narrative()  the deterministic score -> what it means, in prose

Every function degrades instead of failing. If EMERGENT_LLM_KEY is missing or
the model call errors, the caller still gets a usable result built by
`coaching_core` — the dashboard never shows an empty panel because an API was
down, and the numbers on it never depend on a model.
"""
import json
import logging
import os
import re
import uuid

from services.coaching_core import fallback_running_summary, normalize_owner

logger = logging.getLogger(__name__)

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"

# Transcripts run long. 60k chars is ~15k tokens — comfortably inside the
# window while keeping a single session summarisation around a cent.
_MAX_NOTES_CHARS = 60_000
_MAX_SUMMARY_CHARS = 1_400


def enabled() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY"))


def _api_key() -> str:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    return key


async def _ask(system: str, user: str, tag: str) -> str:
    """One-shot model call. Imported lazily so this module stays importable
    (and unit-testable) on a box without the emergentintegrations package."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    chat = LlmChat(
        api_key=_api_key(),
        session_id=f"coach_{tag}_{uuid.uuid4().hex[:10]}",
        system_message=system,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)
    return await chat.send_message(UserMessage(text=user[:_MAX_NOTES_CHARS]))


def _parse_json(raw: str) -> dict:
    """Pull a JSON object out of the response, tolerating code fences and
    stray prose on either side."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    return json.loads(match.group(0))


# ------------------------------------------------------- session summaries

_SESSION_SYSTEM = """You are the note-taker for a professional business coach.
You are given the raw notes or transcript of one coaching session. Return ONLY
a JSON object — no prose, no code fences — with exactly these keys:

{
  "headline": "one sentence, max 90 chars, what this session was actually about",
  "summary": "3-6 sentences. What the client is dealing with, what was decided,
              what changed since last time. Write for the coach re-reading it
              five minutes before the next call. Plain past tense, no bullet
              points, no preamble like 'In this session'.",
  "themes": ["2-5 short lowercase topic tags, e.g. 'pricing', 'hiring', 'burnout'"],
  "sentiment": "one of: energized | steady | strained | stuck",
  "direction_note": "one sentence on where the client seems to be heading and why",
  "action_items": [
    {
      "title": "imperative, specific, max 90 chars — 'Interview 3 TC candidates'",
      "detail": "one sentence of context, or empty string",
      "owner": "client or coach — who agreed to do it",
      "due_hint": "a date the notes state (YYYY-MM-DD) or a phrase like
                   'next week' / 'before the next call', or empty string"
    }
  ],
  "open_questions": ["0-3 things the coach should ask next time"]
}

Rules:
- Only extract action items someone actually committed to. Do not invent
  homework the notes do not support. An empty list is a correct answer.
- Attribute ownership honestly: if the coach agreed to send something, that is
  owner "coach".
- Quote nothing verbatim that is longer than a short phrase.
- If the notes are too thin to summarise, still return the object with your
  best short summary and empty lists."""


def _fallback_session(notes: str) -> dict:
    """No model: use the first couple of sentences as the summary and pull
    nothing out. Honest and empty beats confident and wrong."""
    clean = re.sub(r"\s+", " ", (notes or "").strip())
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    summary = " ".join(sentences[:3])[:_MAX_SUMMARY_CHARS]
    return {
        "headline": (sentences[0] if sentences else "")[:90],
        "summary": summary,
        "themes": [],
        "sentiment": "steady",
        "direction_note": "",
        "action_items": [],
        "open_questions": [],
        "ai_generated": False,
    }


async def summarize_session(notes: str, *, client_name: str = "", prior_summary: str = "") -> dict:
    """Turn raw session notes into a structured record. Always returns a dict
    with the same keys; `ai_generated` says whether the model produced it."""
    if not (notes or "").strip():
        return _fallback_session("")
    if not enabled():
        logger.info("coaching_ai: EMERGENT_LLM_KEY unset, using fallback summariser")
        return _fallback_session(notes)

    context = []
    if client_name:
        context.append(f"CLIENT: {client_name}")
    if prior_summary:
        context.append(f"WHERE THINGS STOOD BEFORE THIS SESSION:\n{prior_summary[:2000]}")
    context.append(f"SESSION NOTES:\n{notes}")

    try:
        raw = await _ask(_SESSION_SYSTEM, "\n\n".join(context), "session")
        parsed = _parse_json(raw)
    except Exception:
        logger.exception("coaching_ai: session summarisation failed; using fallback")
        return _fallback_session(notes)

    items = []
    for item in parsed.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title[:160],
            "detail": str(item.get("detail") or "").strip()[:600],
            "owner": normalize_owner(item.get("owner")),
            "due_hint": str(item.get("due_hint") or "").strip()[:60],
        })

    sentiment = str(parsed.get("sentiment") or "steady").strip().lower()
    if sentiment not in ("energized", "steady", "strained", "stuck"):
        sentiment = "steady"

    return {
        "headline": str(parsed.get("headline") or "").strip()[:120],
        "summary": str(parsed.get("summary") or "").strip()[:_MAX_SUMMARY_CHARS],
        "themes": [str(t).strip().lower()[:40] for t in (parsed.get("themes") or []) if str(t).strip()][:5],
        "sentiment": sentiment,
        "direction_note": str(parsed.get("direction_note") or "").strip()[:400],
        "action_items": items[:12],
        "open_questions": [str(q).strip()[:200] for q in (parsed.get("open_questions") or []) if str(q).strip()][:3],
        "ai_generated": True,
    }


# --------------------------------------------------------- running summary

_RUNNING_SYSTEM = """You maintain the running summary of a long-term coaching
relationship. You receive the client's stated objectives and every session
summary to date, oldest first. Return ONLY a JSON object:

{
  "summary": "4-8 sentences. The arc of the engagement: where they started,
              what has actually changed, what keeps recurring, where they are
              now. Write it as continuous prose a coach can read aloud. Name
              concrete specifics from the sessions — no generic coaching
              language, no 'the client has been on a journey'.",
  "recurring_patterns": ["2-4 patterns that show up across multiple sessions"],
  "progress_markers": ["2-4 things that demonstrably moved"],
  "watch_items": ["1-3 things that keep slipping or getting avoided"]
}

Be specific and unsentimental. If the record is thin, say so plainly rather
than padding."""


async def running_summary(client: dict, sessions: list[dict], actions: list[dict]) -> dict:
    """The evolving 'here is this whole relationship' narrative shown at the
    top of both the client's dashboard and the coach's prep sheet."""
    fallback = {
        "summary": fallback_running_summary(client, sessions, actions),
        "recurring_patterns": [],
        "progress_markers": [],
        "watch_items": [],
        "ai_generated": False,
    }
    if not enabled() or not sessions:
        return fallback

    from services.coaching_core import fmt_day, parse_dt

    ordered = sorted(
        (s for s in sessions if parse_dt(s.get("occurred_at"))),
        key=lambda s: parse_dt(s["occurred_at"]),
    )
    lines = [f"CLIENT: {client.get('name') or 'Client'}"]
    objectives = [str(o).strip() for o in (client.get("objectives") or []) if str(o).strip()]
    if objectives:
        lines.append("STATED OBJECTIVES:\n" + "\n".join(f"- {o}" for o in objectives))
    lines.append("SESSION HISTORY (oldest first):")
    for s in ordered[-24:]:  # two years of fortnightly coaching
        body = str(s.get("summary") or s.get("notes") or "").strip()
        if not body:
            continue
        lines.append(f"\n[{fmt_day(s.get('occurred_at'))}] {s.get('title') or ''}\n{body[:1500]}")

    try:
        raw = await _ask(_RUNNING_SYSTEM, "\n".join(lines), "running")
        parsed = _parse_json(raw)
    except Exception:
        logger.exception("coaching_ai: running summary failed; using fallback")
        return fallback

    summary = str(parsed.get("summary") or "").strip()
    if not summary:
        return fallback

    def _list(key: str, limit: int) -> list[str]:
        return [str(x).strip()[:200] for x in (parsed.get(key) or []) if str(x).strip()][:limit]

    return {
        "summary": summary[:2500],
        "recurring_patterns": _list("recurring_patterns", 4),
        "progress_markers": _list("progress_markers", 4),
        "watch_items": _list("watch_items", 3),
        "ai_generated": True,
    }


# ----------------------------------------------------- trajectory narrative

_TRAJECTORY_SYSTEM = """You read a coaching engagement's scorecard and say, in
plain language, which way it is heading. You receive computed metrics — you did
not compute them and you must not contradict them. Return ONLY a JSON object:

{
  "read": "2-4 sentences on the direction of this engagement and what is
           driving it. Reference the actual numbers you were given.",
  "coach_move": "one sentence: the single highest-leverage thing the coach
                 should do on the next call"
}

Do not soften a bad trend. Do not congratulate a client for a score that is
merely average."""


async def trajectory_narrative(client: dict, traj: dict, recent_summaries: list[str]) -> dict:
    """Prose on top of `coaching_core.trajectory()`. The score is authoritative;
    this only explains it."""
    fallback = {
        "read": " ".join((traj.get("signals") or []) + (traj.get("risks") or [])).strip(),
        "coach_move": "",
        "ai_generated": False,
    }
    if not enabled():
        return fallback

    payload = [
        f"CLIENT: {client.get('name') or 'Client'}",
        f"TRAJECTORY SCORE: {traj.get('score')}/100 ({traj.get('direction_label')})",
        f"COMPONENTS: {json.dumps(traj.get('components') or {})}",
        f"COMPLETION RATE: {traj.get('completion_rate')}%",
        f"DAYS SINCE LAST SESSION: {traj.get('days_since_last_session')}",
        "SIGNALS:\n" + "\n".join(f"- {s}" for s in (traj.get("signals") or [])),
        "RISKS:\n" + "\n".join(f"- {r}" for r in (traj.get("risks") or [])),
    ]
    if recent_summaries:
        payload.append(
            "RECENT SESSION SUMMARIES:\n"
            + "\n".join(f"- {s[:600]}" for s in recent_summaries[:4])
        )

    try:
        parsed = _parse_json(await _ask(_TRAJECTORY_SYSTEM, "\n\n".join(payload), "traj"))
    except Exception:
        logger.exception("coaching_ai: trajectory narrative failed; using fallback")
        return fallback

    read = str(parsed.get("read") or "").strip()
    if not read:
        return fallback
    return {
        "read": read[:900],
        "coach_move": str(parsed.get("coach_move") or "").strip()[:300],
        "ai_generated": True,
    }


__all__ = ["enabled", "summarize_session", "running_summary", "trajectory_narrative"]
