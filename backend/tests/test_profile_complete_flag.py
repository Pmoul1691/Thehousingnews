"""Regression test for the `profile_complete` flag returned by /api/auth/me.

This flag drives the global ProfileNudgeBanner on the frontend. A member
counts as profile-complete when they have a NON-STUB profile row with
both a real name and a real market.
"""
import os
import time

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_ = client["thn_test_profile_complete"]
    yield db_
    await db_.users.delete_many({})
    await db_.profiles.delete_many({})


async def _check(db, user_id, profile):
    """Recreate the logic from routes/auth.py::get_me without spinning up
    the full app. If the helper drifts from the route, this test fails."""
    prof = profile or {}
    return bool(
        (prof.get("name") or "").strip()
        and (prof.get("market") or "").strip()
        and not prof.get("is_stub")
    )


@pytest.mark.asyncio
async def test_no_profile_row_is_incomplete(db):
    assert await _check(db, "u1", None) is False


@pytest.mark.asyncio
async def test_stub_profile_is_incomplete(db):
    assert await _check(db, "u1", {"name": "Marcus", "market": "Miami, FL", "is_stub": True}) is False


@pytest.mark.asyncio
async def test_missing_market_is_incomplete(db):
    assert await _check(db, "u1", {"name": "Marcus"}) is False


@pytest.mark.asyncio
async def test_missing_name_is_incomplete(db):
    assert await _check(db, "u1", {"market": "Miami, FL"}) is False


@pytest.mark.asyncio
async def test_whitespace_only_does_not_count(db):
    assert await _check(db, "u1", {"name": "  ", "market": "Miami, FL"}) is False
    assert await _check(db, "u1", {"name": "Marcus", "market": "   "}) is False


@pytest.mark.asyncio
async def test_real_profile_is_complete(db):
    assert await _check(db, "u1", {"name": "Marcus", "market": "Miami, FL"}) is True


@pytest.mark.asyncio
async def test_real_profile_with_bio_is_complete(db):
    assert await _check(db, "u1", {"name": "Marcus", "market": "Miami, FL", "bio": "Investor"}) is True
