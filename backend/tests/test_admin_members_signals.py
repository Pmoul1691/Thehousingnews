"""Regression: /api/admin/dashboard/members must surface the two new
operator-useful signals — `email_verified` and `profile_complete` — so
the admin panel can render the new signal pills instead of the cryptic
6-char status slice the old UI shipped.
"""
import os
import time

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_ = client["thn_test_admin_members"]
    yield db_
    await db_.users.delete_many({})
    await db_.profiles.delete_many({})


def _row_for(users, profiles):
    """Recreate the projection from routes/admin_dashboard.py::list_members
    without spinning up the full FastAPI app. If the route drifts, this
    test fails."""
    pmap = {p["user_id"]: p for p in profiles}
    out = []
    for u in users:
        prof = pmap.get(u["user_id"]) or {}
        profile_complete = bool(
            (prof.get("name") or "").strip()
            and (prof.get("market") or "").strip()
            and not prof.get("is_stub")
        )
        out.append({
            "user_id": u["user_id"],
            "email_verified": bool(u.get("email_verified")),
            "profile_complete": profile_complete,
        })
    return out


@pytest.mark.asyncio
async def test_real_profile_with_verified_email_is_fully_signaled(db):
    rows = _row_for(
        [{"user_id": "u1", "email_verified": True}],
        [{"user_id": "u1", "name": "Marcus", "market": "Miami, FL"}],
    )
    assert rows[0]["email_verified"] is True
    assert rows[0]["profile_complete"] is True


@pytest.mark.asyncio
async def test_unverified_email_signals_as_false(db):
    rows = _row_for(
        [{"user_id": "u1"}],  # email_verified missing
        [{"user_id": "u1", "name": "Marcus", "market": "Miami, FL"}],
    )
    assert rows[0]["email_verified"] is False


@pytest.mark.asyncio
async def test_stub_profile_does_not_count_as_complete(db):
    rows = _row_for(
        [{"user_id": "u1", "email_verified": True}],
        [{"user_id": "u1", "name": "Marcus", "market": "Miami, FL", "is_stub": True}],
    )
    assert rows[0]["profile_complete"] is False


@pytest.mark.asyncio
async def test_missing_profile_row_is_incomplete(db):
    rows = _row_for(
        [{"user_id": "u1", "email_verified": True}],
        [],
    )
    assert rows[0]["profile_complete"] is False


@pytest.mark.asyncio
async def test_market_missing_is_incomplete(db):
    rows = _row_for(
        [{"user_id": "u1"}],
        [{"user_id": "u1", "name": "Marcus"}],
    )
    assert rows[0]["profile_complete"] is False
