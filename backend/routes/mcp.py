"""MCP (Model Context Protocol) server for The Housing News.

Exposes member-scoped tools to MCP-compatible clients (Claude Desktop, Claude
Code, etc.) via JSON-RPC 2.0 over streamable HTTP. Authentication uses the
existing PAT system — the same `Authorization: Bearer thn_pat_*` token a
member generates in /settings.

How a member connects this in Claude Desktop:

    Edit ~/.../claude_desktop_config.json:
    {
      "mcpServers": {
        "thehousingnews": {
          "command": "npx",
          "args": ["-y", "mcp-remote", "https://thehousingnews.com/api/mcp",
                   "--header", "Authorization: Bearer thn_pat_..."]
        }
      }
    }

Tools exposed:
  • read_todays_briefing
  • search_news
  • list_my_drafts
  • save_draft
  • publish_essay
  • list_my_posts
  • read_my_replies
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from services.auth_helpers import get_current_user
from services.briefings import build_brief_payload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["mcp"])

MCP_PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "thehousingnews"
SERVER_VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Tool registry ─────────────────────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "name": "read_todays_briefing",
        "description": "Get the current daily briefing (morning or evening, picked automatically based on Chicago time). Returns the top headlines from 40 housing publishers plus the featured member essay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["auto", "morning", "evening"], "default": "auto"}
            },
        },
    },
    {
        "name": "search_news",
        "description": "Search the aggregator for housing news articles from the past N days across our 40 publishers. Returns title, snippet, source, and a link to the original article.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "days": {"type": "integer", "default": 7, "minimum": 1, "maximum": 90},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_my_drafts",
        "description": "List the authenticated member's saved drafts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_draft",
        "description": "Save or update the member's working draft. There is one draft slot per member; this replaces it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["essay", "post"], "default": "essay"},
                "title": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "publish_essay",
        "description": "Publish an essay to the network. The essay goes through automatic content moderation (Claude reviews against ToS). If Claude flags or declines it, the essay is held for human admin review. Returns the post_id and current status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["title", "text"],
        },
    },
    {
        "name": "list_my_posts",
        "description": "List the authenticated member's own published essays and posts (most recent first).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "read_my_replies",
        "description": "List recent replies on the authenticated member's posts. Useful for catching up on community engagement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
]


# ─── Tool implementations ──────────────────────────────────────────────────


async def _tool_read_todays_briefing(db, user, args: dict) -> dict:
    kind = args.get("kind", "auto")
    if kind == "auto":
        # Use the same logic as /api/today
        from datetime import datetime as _dt
        from services.release_window import now_chicago
        n = now_chicago()
        morning_start = n.replace(hour=7, minute=30, second=0, microsecond=0)
        evening_start = n.replace(hour=17, minute=30, second=0, microsecond=0)
        kind = "morning" if morning_start <= n < evening_start else "evening"
    payload = await build_brief_payload(db, kind)
    return payload


async def _tool_search_news(db, user, args: dict) -> dict:
    q = (args.get("query") or "").strip()
    if not q:
        raise ValueError("query is required")
    days = max(1, min(90, int(args.get("days", 7))))
    limit = max(1, min(50, int(args.get("limit", 10))))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = db.agg_articles.find(
        {
            "$and": [
                {"published_at": {"$gte": cutoff}},
                {"hidden": {"$ne": True}},
                {"$or": [
                    {"title": {"$regex": q, "$options": "i"}},
                    {"snippet": {"$regex": q, "$options": "i"}},
                ]},
            ]
        },
        {"_id": 0, "id": 1, "title": 1, "snippet": 1, "publisher_id": 1,
         "original_url": 1, "published_at": 1},
    ).sort("published_at", -1).limit(limit)
    rows = await cursor.to_list(limit)
    pub_ids = list({r["publisher_id"] for r in rows})
    pubs: dict = {}
    if pub_ids:
        async for p in db.agg_publishers.find(
            {"id": {"$in": pub_ids}}, {"_id": 0, "id": 1, "name": 1},
        ):
            pubs[p["id"]] = p["name"]
    items = [{
        "title": r["title"],
        "snippet": r.get("snippet") or "",
        "source": pubs.get(r["publisher_id"]) or "Unknown",
        "url": r["original_url"],
        "published_at": r.get("published_at"),
    } for r in rows]
    return {"query": q, "count": len(items), "items": items}


async def _tool_list_my_drafts(db, user, args: dict) -> dict:
    d = await db.drafts.find_one({"user_id": user["user_id"]},
                                  {"_id": 0, "kind": 1, "title": 1, "text": 1, "updated_at": 1})
    return {"draft": d}


async def _tool_save_draft(db, user, args: dict) -> dict:
    kind = args.get("kind", "essay")
    title = args.get("title") or ""
    text = args.get("text") or ""
    if not text.strip():
        raise ValueError("text cannot be empty")
    now_iso = _now_iso()
    await db.drafts.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "kind": kind,
            "title": title,
            "text": text,
            "updated_at": now_iso,
        }},
        upsert=True,
    )
    return {"ok": True, "updated_at": now_iso}


async def _tool_publish_essay(db, user, args: dict) -> dict:
    title = (args.get("title") or "").strip()
    text = (args.get("text") or "").strip()
    subtitle = (args.get("subtitle") or "").strip() or None
    if not title or not text:
        raise ValueError("title and text are required")
    if user.get("status") != "approved":
        raise ValueError("Membership not approved — cannot publish")
    if user.get("suspended"):
        raise ValueError("Account suspended — cannot publish")
    post_id = f"post_{uuid.uuid4().hex[:12]}"
    now_iso = _now_iso()
    doc = {
        "post_id": post_id,
        "user_id": user["user_id"],
        "kind": "essay",
        "title": title,
        "subtitle": subtitle,
        "text": text,
        "tags": [],
        "image_path": None,
        "media": [],
        "status": "approved",  # essays auto-publish; moderation may rewrite to flagged_by_ai
        "created_at": now_iso,
        "release_at": now_iso,
        "prompt_id": None,
        "source": "mcp",
    }
    await db.posts.insert_one(doc)

    # Trigger Claude moderation in background (best-effort, never blocks).
    try:
        from services.moderation import moderate_and_record
        import asyncio
        asyncio.create_task(moderate_and_record(
            db, target_kind="essay", target_id=post_id,
            user_id=user["user_id"], text=text, title=title, subtitle=subtitle,
        ))
    except Exception:
        logger.exception("MCP publish: failed to schedule moderation")

    return {"ok": True, "post_id": post_id, "status": "approved",
            "note": "Essay published. It will be auto-reviewed by Claude; if any policy concern is detected an admin will be notified."}


async def _tool_list_my_posts(db, user, args: dict) -> dict:
    limit = max(1, min(100, int(args.get("limit", 20))))
    rows = await db.posts.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "post_id": 1, "kind": 1, "title": 1, "status": 1,
         "created_at": 1, "release_at": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"count": len(rows), "items": rows}


async def _tool_read_my_replies(db, user, args: dict) -> dict:
    limit = max(1, min(100, int(args.get("limit", 20))))
    # Find all posts owned by the user, then replies on those posts not by user.
    my_posts = await db.posts.find(
        {"user_id": user["user_id"]}, {"_id": 0, "post_id": 1, "title": 1},
    ).to_list(500)
    post_ids = [p["post_id"] for p in my_posts]
    titles_by_id = {p["post_id"]: p.get("title") for p in my_posts}
    if not post_ids:
        return {"count": 0, "items": []}
    rows = await db.replies.find(
        {"post_id": {"$in": post_ids}, "user_id": {"$ne": user["user_id"]}},
        {"_id": 0, "reply_id": 1, "post_id": 1, "user_id": 1, "text": 1,
         "created_at": 1, "status": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    uids = list({r["user_id"] for r in rows})
    names: dict = {}
    if uids:
        async for u in db.users.find(
            {"user_id": {"$in": uids}}, {"_id": 0, "user_id": 1, "name": 1},
        ):
            names[u["user_id"]] = u.get("name") or "—"
    items = [{
        "reply_id": r["reply_id"],
        "post_id": r["post_id"],
        "post_title": titles_by_id.get(r["post_id"]),
        "reply_by": names.get(r["user_id"], "—"),
        "text": r["text"],
        "created_at": r["created_at"],
        "status": r.get("status"),
    } for r in rows]
    return {"count": len(items), "items": items}


TOOLS = {
    "read_todays_briefing": _tool_read_todays_briefing,
    "search_news": _tool_search_news,
    "list_my_drafts": _tool_list_my_drafts,
    "save_draft": _tool_save_draft,
    "publish_essay": _tool_publish_essay,
    "list_my_posts": _tool_list_my_posts,
    "read_my_replies": _tool_read_my_replies,
}


# ─── JSON-RPC handlers ─────────────────────────────────────────────────────


def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def setup(db):
    async def _user_from_header(authorization: Optional[str]) -> dict:
        # MCP clients only support header-based auth; reuse get_current_user
        # with cookie=None.
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        return await get_current_user(db, None, authorization)

    @router.get("")
    async def mcp_get():
        # MCP streamable HTTP allows GET for capability discovery.
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
            "note": "POST JSON-RPC 2.0 requests here. Auth: Bearer PAT.",
        }

    @router.post("")
    async def mcp_post(request: Request,
                       authorization: Optional[str] = Header(default=None)):
        try:
            body = await request.json()
        except Exception:
            return _rpc_error(None, -32700, "Parse error")

        # Allow `initialize` and `ping` without auth (the spec lets clients
        # introspect before the auth handshake completes).
        method = (body or {}).get("method") or ""
        req_id = (body or {}).get("id")

        if method == "initialize":
            return _rpc_result(req_id, {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": {}},
            })
        if method == "ping":
            return _rpc_result(req_id, {})
        if method == "notifications/initialized":
            # Notifications expect no response per JSON-RPC, but FastAPI must
            # return something; an empty 202-style ack is fine.
            return {"jsonrpc": "2.0"}

        # Everything else requires auth.
        try:
            user = await _user_from_header(authorization)
        except HTTPException as exc:
            return _rpc_error(req_id, -32001, exc.detail or "Unauthorized")
        except Exception as exc:
            logger.exception("mcp auth failed")
            return _rpc_error(req_id, -32001, f"Auth error: {exc}")

        if method == "tools/list":
            return _rpc_result(req_id, {"tools": TOOLS_SCHEMA})

        if method == "tools/call":
            params = body.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            fn = TOOLS.get(name)
            if not fn:
                return _rpc_error(req_id, -32601, f"Unknown tool: {name}")
            try:
                result = await fn(db, user, args)
            except ValueError as exc:
                return _rpc_error(req_id, -32602, str(exc))
            except Exception as exc:
                logger.exception(f"mcp tool {name} failed")
                return _rpc_error(req_id, -32603, f"Tool error: {exc}")
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": _format_result(result)}],
                "structuredContent": result,
            })

        return _rpc_error(req_id, -32601, f"Method not found: {method}")

    return router


def _format_result(result: Any) -> str:
    """Pretty plaintext fallback for clients that don't read structuredContent."""
    import json as _json
    try:
        return _json.dumps(result, indent=2, default=str)
    except Exception:
        return str(result)
