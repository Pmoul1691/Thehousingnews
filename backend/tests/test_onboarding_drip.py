"""Tests for the Day 3 / 7 / 14 onboarding drip.

Uses the real test_database (matching the rest of the suite) and patches
`services.onboarding_drip.send_email` so nothing actually hits Brevo.

Validates:
- Sweep finds users in the right age windows and skips users outside them.
- Idempotency: a second sweep on the same day is a no-op.
- Flag dormant: with ONBOARDING_DRIP_ENABLED unset, candidates are queued
  but send_email is never called.
- Send failure is recorded on the dispatch row, not silenced.
"""
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_ = client["thn_test_drip"]  # isolated DB so we don't pollute test_database
    # Match prod index for idempotency enforcement.
    await db_.onboarding_dispatches.create_index(
        [("user_id", 1), ("kind", 1)], unique=True
    )
    yield db_
    # Clean slate for next test run
    await db_.users.delete_many({})
    await db_.onboarding_dispatches.delete_many({})


def _ts() -> int:
    return int(time.time() * 1000)


async def _seed_user(db, days_ago: int, status: str = "approved") -> str:
    uid = f"u_{days_ago}d_{_ts()}"
    created_at = (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=2)).isoformat()
    await db.users.insert_one({
        "user_id": uid,
        "email": f"{uid}@example.com",
        "name": "Test User",
        "status": status,
        "created_at": created_at,
    })
    return uid


@pytest.mark.asyncio
async def test_sweep_finds_day_3_7_14_and_skips_others(db, monkeypatch):
    monkeypatch.delenv("ONBOARDING_DRIP_ENABLED", raising=False)
    import importlib
    import services.onboarding_drip as drip
    importlib.reload(drip)

    await _seed_user(db, 3)
    await _seed_user(db, 5)   # outside every window
    await _seed_user(db, 7)
    await _seed_user(db, 14)
    await _seed_user(db, 20)  # outside

    with patch("services.onboarding_drip.send_email") as fake_send:
        summary = await drip.run_drip_sweep(db)

    assert summary["candidates"] == 3, summary
    assert not fake_send.called
    assert summary["sent"] == 0
    assert summary["skipped_flag_off"] == 3


@pytest.mark.asyncio
async def test_sweep_sends_when_flag_enabled(db, monkeypatch):
    monkeypatch.setenv("ONBOARDING_DRIP_ENABLED", "true")
    import importlib
    import services.onboarding_drip as drip
    importlib.reload(drip)

    uid = await _seed_user(db, 7)

    with patch("services.onboarding_drip.send_email", return_value={"messageId": "x"}) as fake_send:
        summary = await drip.run_drip_sweep(db)

    assert fake_send.called
    assert summary["sent"] == 1
    row = await db.onboarding_dispatches.find_one({"user_id": uid, "kind": "drip_day_7"})
    assert row is not None
    assert row["status"] == "sent"


@pytest.mark.asyncio
async def test_sweep_is_idempotent(db, monkeypatch):
    monkeypatch.setenv("ONBOARDING_DRIP_ENABLED", "true")
    import importlib
    import services.onboarding_drip as drip
    importlib.reload(drip)

    await _seed_user(db, 3)

    with patch("services.onboarding_drip.send_email", return_value={"messageId": "x"}) as fake_send:
        first = await drip.run_drip_sweep(db)
        second = await drip.run_drip_sweep(db)

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped_already_sent"] == 1
    assert fake_send.call_count == 1


@pytest.mark.asyncio
async def test_sweep_skips_non_approved_users(db, monkeypatch):
    monkeypatch.setenv("ONBOARDING_DRIP_ENABLED", "true")
    import importlib
    import services.onboarding_drip as drip
    importlib.reload(drip)

    await _seed_user(db, 3, status="pending")
    await _seed_user(db, 7, status="declined")

    with patch("services.onboarding_drip.send_email") as fake_send:
        summary = await drip.run_drip_sweep(db)

    assert summary["candidates"] == 0
    assert not fake_send.called


@pytest.mark.asyncio
async def test_send_failure_is_recorded(db, monkeypatch):
    monkeypatch.setenv("ONBOARDING_DRIP_ENABLED", "true")
    import importlib
    import services.onboarding_drip as drip
    importlib.reload(drip)

    uid = await _seed_user(db, 14)

    blocked = {"error": "blocked: preview URL in email body", "blocked": True}
    with patch("services.onboarding_drip.send_email", return_value=blocked):
        summary = await drip.run_drip_sweep(db)

    assert summary["errors"] == 1
    assert summary["sent"] == 0
    row = await db.onboarding_dispatches.find_one({"user_id": uid})
    assert row["status"] == "error"
    assert "blocked" in row["error"]
