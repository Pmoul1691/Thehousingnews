"""User-region preferences + taxonomy endpoint.

`GET  /api/regions`            → full taxonomy (public, used by Settings + composer)
`GET  /api/users/me/regions`   → current user's region picks
`PUT  /api/users/me/regions`   → update picks
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Cookie, Header
from pydantic import BaseModel, Field

from services.auth_helpers import get_current_user
from services.regions import REGIONS, normalise, grouped


class RegionPrefs(BaseModel):
    regions: list[str] = Field(default_factory=list)


def setup(db):
    router = APIRouter(prefix="/api", tags=["regions"])

    @router.get("/regions")
    async def list_regions():
        """Public taxonomy — labels + tier grouping for the UI picker."""
        return {"items": REGIONS, "grouped": grouped()}

    @router.get("/users/me/regions")
    async def get_my_regions(
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        return {"regions": list(user.get("regions") or [])}

    @router.put("/users/me/regions")
    async def set_my_regions(
        body: RegionPrefs,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await get_current_user(db, session_token, authorization)
        clean = normalise(body.regions)
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"regions": clean}},
        )
        return {"regions": clean}

    return router
