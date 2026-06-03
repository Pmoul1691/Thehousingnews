"""Token-protected endpoint to refresh every active RSS feed on demand.

Designed to be called by an external cron / scheduler service. The platform
ALSO runs an in-process APScheduler job every 15 minutes (see
services/scheduler.py), so this endpoint is the redundant "if APScheduler dies
or you want a manual kick" trigger.

Token comes from RSS_REFRESH_TOKEN in backend/.env. Caller passes it as either
`?token=` or the `X-Refresh-Token` header.

The actual ingest is kicked off as a background task so the HTTP request
returns in <300ms — a long-running ingest used to pin a uvicorn worker for
30-60 seconds, stalling every other request behind it. An in-process flag
prevents two concurrent triggers from double-fetching every feed.
"""
import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from services.rss_ingest import ingest_all_active

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(tags=["aggregator-public"])

    # In-process overlap guard. We don't need cross-pod coordination here:
    # the public endpoint is meant to be hit by a single external cron, and
    # the in-process APScheduler job calls ingest_all_active directly (not
    # through this endpoint), so the only conflict is "operator clicks
    # refresh twice in quick succession".
    state = {
        "running": False,
        "started_at": None,
        "last_run_at": None,
        "last_run_id": None,
        "last_summary": None,
    }

    async def _run_ingest(run_id: str) -> None:
        state["running"] = True
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        state["last_run_id"] = run_id
        t0 = time.perf_counter()
        try:
            summary = await ingest_all_active(db)
            state["last_summary"] = {
                **summary,
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
        except Exception:
            logger.exception("background refresh-feeds crashed")
            state["last_summary"] = {"error": "crash"}
        finally:
            state["running"] = False
            state["last_run_at"] = datetime.now(timezone.utc).isoformat()

    @router.post("/api/refresh-feeds")
    async def refresh_feeds(
        background_tasks: BackgroundTasks,
        token: str | None = Query(default=None),
        x_refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
    ):
        expected = os.environ.get("RSS_REFRESH_TOKEN")
        if not expected:
            raise HTTPException(status_code=503, detail="Refresh token not configured")
        supplied = token or x_refresh_token
        if not supplied or supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        if state["running"]:
            # Already in flight — return 202 with the existing run reference
            # so a duplicate trigger doesn't kick off a second ingest.
            return {
                "accepted": True,
                "already_running": True,
                "run_id": state["last_run_id"],
                "started_at": state["started_at"],
            }

        run_id = uuid.uuid4().hex[:12]
        background_tasks.add_task(_run_ingest, run_id)
        return {
            "accepted": True,
            "already_running": False,
            "run_id": run_id,
        }

    @router.get("/api/refresh-feeds/status")
    async def refresh_feeds_status(
        token: str | None = Query(default=None),
        x_refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
    ):
        """Status probe — useful for the external cron to confirm the last
        run actually completed. Same auth as the trigger."""
        expected = os.environ.get("RSS_REFRESH_TOKEN")
        if not expected:
            raise HTTPException(status_code=503, detail="Refresh token not configured")
        supplied = token or x_refresh_token
        if not supplied or supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        return {
            "running": state["running"],
            "started_at": state["started_at"],
            "last_run_at": state["last_run_at"],
            "last_run_id": state["last_run_id"],
            "last_summary": state["last_summary"],
        }

    # Expose state for tests.
    router._refresh_state = state  # type: ignore[attr-defined]
    return router
