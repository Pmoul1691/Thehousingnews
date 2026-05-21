"""Public route for the residential real estate podcast directory."""
import logging
from fastapi import APIRouter, HTTPException, Response

from services.podcasts_directory import get_directory_fast

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(prefix="/api/agg/podcasts", tags=["aggregator-podcasts"])

    @router.get("")
    async def list_podcasts(response: Response):
        """Public: returns the curated top-10 directory with live RSS data
        merged in.

        Uses the non-blocking `get_directory_fast()` so this route NEVER
        waits on external RSS feeds. The first user after a cold pod
        start gets an empty list (the page renders instantly); a
        background thread rebuilds the cache and every subsequent user
        gets full data. Stale data is also served immediately while a
        refresh is in flight. Was previously blocking up to 30 seconds
        on dead external feeds — that was the root cause of "very slow
        or won't load at all" reports on production.

        Cache-Control: public 120s so Cloudflare serves repeat visitors
        from the edge; podcast directory updates only every ~30 minutes.
        """
        response.headers["Cache-Control"] = (
            "public, max-age=120, s-maxage=120, stale-while-revalidate=120"
        )
        try:
            return get_directory_fast()
        except Exception as e:
            logger.exception("podcast directory failed")
            raise HTTPException(status_code=502, detail="Could not load directory") from e

    return router
