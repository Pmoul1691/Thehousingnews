"""Claude-powered content moderation for member posts, essays, and replies.

Behavior: "Flag, don't block" (Mode 2).
- Every submitted post/reply is reviewed asynchronously by Claude.
- Claude returns a structured verdict: approve | flag | decline.
- If verdict is `flag` or `decline`, the content's status is set to
  `flagged_by_ai` and routed to the Admin Moderation queue.
- An admin makes the final call (override-approve or confirm decline).

ToS rules and house policy are passed in the system prompt. Reasoning is
stored per review for the audit trail.

Cost: ~$0.001–0.003 per review using Claude Sonnet 4.5.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"

Verdict = Literal["approve", "flag", "decline"]

# Tight summary of the parts of the ToS that map to moderation policy.
# We reference Section 6 (Acceptable Use), Section 7 (User Content), and
# Section 8 (Industry-specific compliance for real estate professionals).
TOS_SUMMARY = """
The Housing News is a daily news magazine for real estate professionals.
Content is editorial and must meet professional standards. The following
categories MUST be flagged or declined per the platform's Terms of Service:

PROHIBITED CONTENT (auto-decline):
  • Fair Housing violations: discriminatory language or preference based on
    race, color, religion, sex, disability, familial status, national origin,
    sexual orientation, gender identity, or source of income. Includes coded
    language like "good schools," "safe neighborhood," "family-friendly" used
    as proxies for protected class characteristics. Includes steering,
    blockbusting, or redlining.
  • Antitrust violations: discussing specific commission rates as "standard,"
    "customary," or "typical" in a way that suggests price coordination;
    proposing coordinated pricing among competing brokerages; calls for
    boycotts of specific competitors or business models.
  • Client confidentiality breaches: disclosing identities, financial
    details, motivations, offer terms, or communications of clients or
    cooperating agents without consent.
  • Unauthorized MLS / listing content reproduction.
  • RESPA violations: kickbacks for referrals.
  • Unlicensed mortgage or legal/tax advice presented as professional
    guidance.
  • Spam, unsolicited commercial messages, lead-gen schemes posing as
    editorial content.
  • Personal attacks, harassment, doxxing, or defamation of named
    individuals.
  • Misrepresentation of credentials, licensure status, designations,
    production figures, or awards.
  • Content that violates clear federal/state law.

BORDERLINE / FLAG FOR HUMAN REVIEW:
  • Strong opinions about competing brokerages that risk being read as
    antitrust signaling (even if not explicit).
  • Real-deal anecdotes that reveal enough detail to identify a client.
  • Aggressive promotion of one's own business with little editorial value.
  • Political content unrelated to the housing industry.
  • Off-topic content (entertainment, unrelated industries).
  • Unverified rumors or speculation presented as fact.

APPROVE:
  • Honest market commentary, deal notes (anonymised), industry analysis.
  • Personal reflections on practice, mentorship advice, tactical notes.
  • Strong opinions on policy, NAR, or industry direction, even if pointed.
  • Critique of named companies/individuals when grounded in published facts.
""".strip()

SYSTEM_PROMPT = f"""You are the content moderator for The Housing News, a
professional editorial platform for real estate practitioners (agents,
brokers, mortgage and title professionals).

Your job is to review one piece of user-submitted content and decide
whether it can be published.

POLICY:
{TOS_SUMMARY}

OUTPUT REQUIREMENT — you MUST respond with a single valid JSON object and
nothing else (no preamble, no markdown fence). Schema:

{{
  "verdict": "approve" | "flag" | "decline",
  "risk_score": <integer 0-100>,
  "categories": [<strings from: fair_housing, antitrust, confidentiality,
                 mls_violation, respa, unlicensed_advice, spam, harassment,
                 misrepresentation, off_topic, political, defamation,
                 unverified_rumor, borderline_promotion, none>],
  "reasoning": "<2-4 plain-English sentences explaining the verdict>",
  "quoted_excerpts": [<up to 3 short verbatim phrases that triggered the
                      flag, if any>]
}}

DECISION RULES:
  • "approve" — clean content. risk_score < 30. categories = ["none"].
  • "flag" — borderline, ambiguous, or possibly risky. risk_score 30-69.
    Flag if you would want a human to take a look.
  • "decline" — clearly violates the policy. risk_score >= 70. Reserve for
    obvious fair housing, antitrust, confidentiality, RESPA, defamation,
    or harassment violations.

Be conservative on "decline" — when in doubt, choose "flag" so a human
admin can make the final call. False decline is worse than false flag.
""".strip()


async def _get_active_prompt(db) -> str:
    """Return the live moderation prompt. Admins can override the file
    constant by saving a custom version in moderation_settings; this is
    how we tune the prompt over time without redeploying."""
    if db is None:
        return SYSTEM_PROMPT
    try:
        row = await db.moderation_settings.find_one(
            {"key": "system_prompt"}, {"_id": 0, "value": 1},
        )
        if row and (row.get("value") or "").strip():
            return row["value"]
    except Exception:
        logger.exception("failed to load custom system_prompt; using default")
    return SYSTEM_PROMPT


def _api_key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    return k


def _parse_verdict(raw: str) -> dict:
    """Pull JSON out of Claude's response, tolerating stray prose."""
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except (ValueError, AttributeError):
        pass
    # Fall back to extracting the first {...} block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object in moderation response: {raw[:200]}")
    return json.loads(m.group(0))


async def review_content(
    *,
    db=None,
    target_kind: str,          # "post" | "essay" | "reply"
    text: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> dict:
    """Ask Claude to review one piece of content. Returns the parsed verdict
    dict or raises on parse/network failure."""

    body_parts = []
    if title:
        body_parts.append(f"TITLE: {title}")
    if subtitle:
        body_parts.append(f"SUBTITLE: {subtitle}")
    body_parts.append(f"KIND: {target_kind}")
    body_parts.append(f"\nCONTENT:\n{text}")
    user_text = "\n".join(body_parts)

    session_id = f"mod_{uuid.uuid4().hex[:12]}"
    system_prompt = await _get_active_prompt(db)
    chat = LlmChat(
        api_key=_api_key(),
        session_id=session_id,
        system_message=system_prompt,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)

    response = await chat.send_message(UserMessage(text=user_text))
    parsed = _parse_verdict(response)

    # Defensive coercion
    parsed["verdict"] = parsed.get("verdict", "flag")
    if parsed["verdict"] not in ("approve", "flag", "decline"):
        parsed["verdict"] = "flag"
    try:
        parsed["risk_score"] = int(parsed.get("risk_score") or 50)
    except (ValueError, TypeError):
        parsed["risk_score"] = 50
    parsed["categories"] = parsed.get("categories") or []
    parsed["reasoning"] = parsed.get("reasoning") or ""
    parsed["quoted_excerpts"] = parsed.get("quoted_excerpts") or []
    return parsed


async def moderate_and_record(db, *, target_kind: str, target_id: str,
                              user_id: str, text: str,
                              title: Optional[str] = None,
                              subtitle: Optional[str] = None) -> dict:
    """Run Claude review, persist a moderation_review row, and (if needed)
    update the target's status to `flagged_by_ai`.

    Designed to be called from FastAPI BackgroundTasks. Errors are swallowed
    after being logged — the post should never fail to publish just because
    moderation broke.
    """
    review_id = f"mr_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        verdict = await review_content(
            db=db, target_kind=target_kind, text=text, title=title, subtitle=subtitle,
        )
    except Exception as exc:  # noqa: BLE001 - we want every error caught
        logger.exception("moderation review failed")
        await db.moderation_reviews.insert_one({
            "id": review_id,
            "target_kind": target_kind,
            "target_id": target_id,
            "user_id": user_id,
            "verdict": "error",
            "risk_score": None,
            "categories": [],
            "reasoning": f"Moderation call failed: {exc}",
            "quoted_excerpts": [],
            "model": MODEL_NAME,
            "content_excerpt": (text or "")[:500],
            "title": title,
            "reviewed_at": now_iso,
            "admin_decision": None,
            "admin_user_id": None,
            "admin_decided_at": None,
        })
        return {"verdict": "error"}

    excerpt = (text or "")[:500]
    review_doc = {
        "id": review_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "user_id": user_id,
        "verdict": verdict["verdict"],
        "risk_score": verdict["risk_score"],
        "categories": verdict["categories"],
        "reasoning": verdict["reasoning"],
        "quoted_excerpts": verdict["quoted_excerpts"],
        "model": MODEL_NAME,
        "content_excerpt": excerpt,
        "title": title,
        "reviewed_at": now_iso,
        "admin_decision": None,
        "admin_user_id": None,
        "admin_decided_at": None,
    }
    await db.moderation_reviews.insert_one(review_doc)

    # If Claude flagged or declined, gate the content.
    if verdict["verdict"] in ("flag", "decline"):
        coll = db.posts if target_kind in ("post", "essay") else db.replies
        id_field = "post_id" if target_kind in ("post", "essay") else "reply_id"
        await coll.update_one(
            {id_field: target_id},
            {"$set": {
                "status": "flagged_by_ai",
                "moderation_review_id": review_id,
                "moderation_verdict": verdict["verdict"],
                "moderation_score": verdict["risk_score"],
            }},
        )

    return verdict
