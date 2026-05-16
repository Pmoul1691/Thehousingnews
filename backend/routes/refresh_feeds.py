"""Token-protected endpoint to refresh every active RSS feed on demand.

Designed to be called by an external cron / scheduler service. The platform
ALSO runs an in-process APScheduler job every 15 minutes (see
services/scheduler.py), so this endpoint is the redundant "if APScheduler dies
or you want a manual kick" trigger.

Token comes from RSS_REFRESH_TOKEN in backend/.env. Caller passes it as either
`?token=` or the `X-Refresh-Token` header. Returns a per-publisher summary so
operators can spot dead feeds without going to the admin UI.
"""
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Query

from services.rss_ingest import ingest_all_active

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(tags=["aggregator-public"])

    @router.post("/api/refresh-feeds")
    async def refresh_feeds(
        token: str | None = Query(default=None),
        x_refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
    ):
        expected = os.environ.get("RSS_REFRESH_TOKEN")
        if not expected:
            raise HTTPException(status_code=503, detail="Refresh token not configured")
        supplied = token or x_refresh_token
        if not supplied or supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        # ingest_all_active runs the same loop the cron uses. One bad feed
        # never affects the others; each publisher's error_count is bumped
        # individually and the worst-case is recorded in last_fetch_status.
        try:
            summary = await ingest_all_active(db)
        except Exception as e:
            logger.exception("manual refresh-feeds crashed")
            raise HTTPException(status_code=500, detail=f"refresh crashed: {type(e).__name__}")
        return summary

    return router
