"""Public route for the residential real estate podcast directory."""
import logging
from fastapi import APIRouter, HTTPException

from services.podcasts_directory import get_directory

logger = logging.getLogger(__name__)


def setup(db):
    router = APIRouter(prefix="/api/agg/podcasts", tags=["aggregator-podcasts"])

    @router.get("")
    async def list_podcasts():
        """Public: returns the curated top-10 directory with live RSS data
        merged in. Server-side RSS parsing avoids browser CORS issues; results
        are cached in-process for 1 hour."""
        try:
            return get_directory()
        except Exception as e:
            logger.exception("podcast directory failed")
            raise HTTPException(status_code=502, detail="Could not load directory") from e

    return router
