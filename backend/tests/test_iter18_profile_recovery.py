"""Profile-recovery path + regression coverage.

All scenarios run inside a single async test so the Motor client stays bound
to one event loop. Spinning multiple TestClient or LifespanManager contexts
across pytest tests triggers "Event loop is closed" because `server.py`
creates a module-level Motor client at import time which captures whichever
loop happened to be current at first use.
"""
import os
import time
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
os.environ.setdefault("DB_NAME", "test_database")

import sys
sys.path.insert(0, "/app/backend")

_sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _emergent_response(email: str, name: str, session_token: str):
    class _R:
        status_code = 200
        def json(self):
            return {"email": email, "name": name, "picture": "", "session_token": session_token}
    return _R()


def _cleanup(email: str):
    _sync.users.delete_many({"email": email})
    _sync.profiles.delete_many({"email": email})


@pytest.mark.asyncio
async def test_auth_session_paths_and_substack_release_window():
    """All scenarios live in one async test so the Motor client's loop stays
    valid throughout. Splitting into multiple `@pytest.mark.asyncio` tests
    triggers "Event loop is closed" on subsequent tests because server.py
    captures the loop at import time.
    """
    from server import app
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as aclient:

            # --- A: recovery from orphan profile by email ---
            email_a = f"recovery.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@example.com"
            legacy_uid = f"recovery_legacy_{uuid.uuid4().hex[:8]}"
            _cleanup(email_a)
            _sync.profiles.insert_one({
                "user_id": legacy_uid, "email": email_a, "name": "Legacy Profile",
                "market": "Chicago", "bio": "old", "objectives": ["a", "b", "c"],
                "objectives_version": 1,
            })
            try:
                token_a = "rec_" + uuid.uuid4().hex[:12]
                with patch("routes.auth.requests.get", return_value=_emergent_response(email_a, "Returning Member", token_a)):
                    r = await aclient.post("/api/auth/session", json={"session_id": "fake"})
                assert r.status_code == 200, r.text
                b = r.json()
                assert b["user_id"] == legacy_uid
                assert b["has_profile"] is True
                assert b["status"] == "approved"
                assert b["session_token"] == token_a
                u = _sync.users.find_one({"user_id": legacy_uid})
                assert u and u["source"] == "profile_recovery"
            finally:
                _cleanup(email_a)
                _sync.user_sessions.delete_many({"user_id": legacy_uid})

            # --- B: brand-new user lands on needs_application ---
            email_b = f"fresh.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@example.com"
            _cleanup(email_b)
            try:
                with patch("routes.auth.requests.get", return_value=_emergent_response(email_b, "Brand New", "fr_" + uuid.uuid4().hex[:12])):
                    r = await aclient.post("/api/auth/session", json={"session_id": "fake"})
                assert r.status_code == 200, r.text
                b = r.json()
                assert b["status"] == "needs_application"
                assert b["has_profile"] is False
            finally:
                _cleanup(email_b)

            # --- C: existing user with intact records stays put ---
            email_c = f"existing.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@example.com"
            user_id_c = f"recovery_existing_{uuid.uuid4().hex[:8]}"
            _cleanup(email_c)
            _sync.users.insert_one({
                "user_id": user_id_c, "email": email_c, "name": "Existing Member",
                "picture": "", "is_admin": False, "status": "approved", "source": "google",
            })
            _sync.profiles.insert_one({
                "user_id": user_id_c, "email": email_c, "name": "Existing Member",
                "market": "Chicago", "objectives": ["x", "y", "z"], "objectives_version": 1,
            })
            try:
                with patch("routes.auth.requests.get", return_value=_emergent_response(email_c, "Existing Member", "ex_" + uuid.uuid4().hex[:12])):
                    r = await aclient.post("/api/auth/session", json={"session_id": "fake"})
                assert r.status_code == 200, r.text
                b = r.json()
                assert b["user_id"] == user_id_c
                assert b["status"] == "approved"
                assert b["has_profile"] is True
            finally:
                _cleanup(email_c)
                _sync.user_sessions.delete_many({"user_id": user_id_c})

            # --- D: Substack import releases at the next batched window ---
            from services.substack_import import import_substack_feed
            from services.release_window import next_window
            admin_email = f"admin.import.{uuid.uuid4().hex[:6]}@example.com"
            admin_uid = f"admin_{uuid.uuid4().hex[:8]}"
            _sync.users.delete_many({"email": admin_email})
            _sync.users.insert_one({
                "user_id": admin_uid, "email": admin_email, "name": "Test Admin",
                "is_admin": True, "status": "approved", "source": "manual_test",
            })
            test_guid = f"test-guid-{uuid.uuid4().hex[:8]}"
            test_link = f"https://example.test/{uuid.uuid4().hex[:8]}"
            _sync.posts.delete_many({"source_guid": test_guid})

            class _FakeEntry:
                title = "Test essay"
                subtitle = None
                link = test_link
                id = test_guid
                published_parsed = (2026, 1, 1, 12, 0, 0)
                content = [{"value": "<p>Hello world.</p>"}]

            class _FakeParsed:
                bozo = 0
                entries = [_FakeEntry()]

            import services.substack_import as si
            original_fallback = si.ADMIN_FALLBACK_EMAILS
            si.ADMIN_FALLBACK_EMAILS = (admin_email,)
            try:
                from server import db as server_db
                with patch.object(si, "feedparser") as fp:
                    fp.parse.return_value = _FakeParsed()
                    result = await import_substack_feed(server_db, feed_url="https://fake")
                assert result["imported"] == 1, result
                post = _sync.posts.find_one({"source_guid": test_guid})
                assert post is not None
                from datetime import datetime
                release = datetime.fromisoformat(post["release_at"])
                expected = next_window()
                assert abs((release - expected).total_seconds()) < 60, (release, expected)
                assert post["source_published_at"].startswith("2026-01-01"), post["source_published_at"]
            finally:
                si.ADMIN_FALLBACK_EMAILS = original_fallback
                _sync.posts.delete_many({"source_guid": test_guid})
                _sync.users.delete_many({"email": admin_email})
