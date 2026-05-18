"""AI-powered region tagger.

Given a post's text, asks Claude Haiku to return a JSON array of region
slugs drawn from `services.regions.REGIONS`. Returns `[]` if the post isn't
geographically specific.

Runs as a FastAPI BackgroundTask so it never blocks `POST /api/posts`.
"""
import os
import json
import re
import uuid
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

from services.regions import all_slugs, normalise

logger = logging.getLogger(__name__)

_MODEL_PROVIDER = "anthropic"
_MODEL_NAME = "claude-haiku-4-5-20251001"  # fast + cheap; falls through if unavailable
_MAX_INPUT_CHARS = 6000


def _api_key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    return k


def _system_prompt() -> str:
    slugs = all_slugs()
    return (
        "You classify short pieces of real-estate writing by the US region(s) "
        "they discuss. You receive the post text. You MUST respond with ONLY a "
        "JSON array of slugs drawn from this exact allowed list — no prose, no "
        "code fences, no keys:\n\n"
        f"ALLOWED_SLUGS = {json.dumps(slugs)}\n\n"
        "Rules:\n"
        "1. Return 0 to 5 slugs, ranked most-specific first (city > metro > "
        "state > region > national).\n"
        "2. If the post is about a city, include city + metro + state + region "
        "as well (so a Chicago post returns [\"chicago\",\"chicago-metro\",\"il\","
        "\"midwest\"]).\n"
        "3. If the post is generic US news, return [\"national\"].\n"
        "4. If the post has no geographic specificity at all (industry trends, "
        "philosophical takes, advice), return [].\n"
        "5. NEVER invent a slug not in ALLOWED_SLUGS.\n"
        "6. Respond with ONLY the JSON array. Example responses:\n"
        '   ["chicago","chicago-metro","il","midwest"]\n'
        '   ["national"]\n'
        '   []'
    )


def _parse(raw: str) -> list[str]:
    """Pull a JSON array out of Claude's response, tolerating stray prose."""
    if not raw:
        return []
    # Direct parse
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
    except (ValueError, TypeError):
        pass
    # Fallback: regex-extract the first [...] block
    m = re.search(r"\[[^\]]*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
    except (ValueError, TypeError):
        pass
    return []


async def tag_post(text: str) -> list[str]:
    """Classify `text` into region slugs. Returns [] on any error path.

    Safe to call without try/except at the call-site; failures are logged
    and swallowed so a tagging hiccup never breaks the post create path.
    """
    if not text:
        return []
    snippet = text.strip()
    if len(snippet) > _MAX_INPUT_CHARS:
        snippet = snippet[:_MAX_INPUT_CHARS]
    try:
        chat = LlmChat(
            api_key=_api_key(),
            session_id=f"region_{uuid.uuid4().hex[:12]}",
            system_message=_system_prompt(),
        ).with_model(_MODEL_PROVIDER, _MODEL_NAME)
        response = await chat.send_message(UserMessage(text=snippet))
    except Exception:
        logger.exception("region_tagger: LLM call failed")
        return []
    return normalise(_parse(response))
