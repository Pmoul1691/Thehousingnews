"""Iteration 20: P2 features test suite.

Coverage:
  A) GET /api/agg/trending - trending topics
  B) GET /api/members - admin entitlement filter
  C) GET /api/admin/preview-db/preview + POST .../reset
  D) GET /api/applications/tos-version + POST /api/applications tos validation
  G) Hashtag verification (regression smoke)

Reset tests run last because they wipe non-admin data on the shared DB.
"""
import os
import time
import re
import requests
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://housing-news-preview.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# --------------------------- Shared seed fixtures ---------------------------

@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def seed_users(mongo):
    """Seed admin / approved member / applicant. Cleaned up at session end."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    exp_iso = (now + timedelta(days=7)).isoformat()
    ts = int(time.time() * 1000)

    admin_token = f"tok_admin_iter20_{ts}"
    member_id = f"user_member_iter20_{ts}"
    member_token = f"tok_member_iter20_{ts}"
    applicant_id = f"user_app_iter20_{ts}"
    applicant_token = f"tok_app_iter20_{ts}"
    comped_id = f"user_comped_iter20_{ts}"
    supporter_id = f"user_supporter_iter20_{ts}"

    # Re-use existing admin (peter@1691inc.com) row if present; else create.
    existing_admin = mongo.users.find_one({"email": "peter@1691inc.com"})
    if existing_admin:
        admin_id = existing_admin["user_id"]
        mongo.users.update_one({"user_id": admin_id},
                                {"$set": {"is_admin": True, "status": "approved"}})
    else:
        admin_id = f"user_admin_iter20_{ts}"
        mongo.users.insert_one({"user_id": admin_id, "email": "peter@1691inc.com",
                                "name": "Iter20 Admin", "picture": "", "is_admin": True,
                                "status": "approved", "source": "manual_test",
                                "created_at": now_iso, "last_login_at": now_iso})

    mongo.users.insert_many([
        {"user_id": member_id, "email": f"member.iter20.{ts}@example.com", "name": "Iter20 Member",
         "picture": "", "is_admin": False, "status": "approved", "source": "manual_test",
         "created_at": now_iso, "last_login_at": now_iso},
        {"user_id": applicant_id, "email": f"applicant.iter20.{ts}@example.com", "name": "Iter20 Applicant",
         "picture": "", "is_admin": False, "status": "needs_application", "source": "manual_test",
         "created_at": now_iso, "last_login_at": now_iso},
        {"user_id": comped_id, "email": f"comped.iter20.{ts}@example.com", "name": "Iter20 Comped",
         "picture": "", "is_admin": False, "status": "approved", "source": "partners_auto_grant",
         "partner_tier": "gold",
         "created_at": now_iso, "last_login_at": now_iso},
        {"user_id": supporter_id, "email": f"supporter.iter20.{ts}@example.com", "name": "Iter20 Supporter",
         "picture": "", "is_admin": False, "status": "approved", "source": "manual_test",
         "supporter_until": exp_iso,
         "created_at": now_iso, "last_login_at": now_iso},
    ])
    mongo.profiles.insert_many([
        {"user_id": member_id, "name": "Iter20 Member", "market": "NYC", "bio": "test"},
        {"user_id": comped_id, "name": "Iter20 Comped", "market": "LA", "bio": "test"},
        {"user_id": supporter_id, "name": "Iter20 Supporter", "market": "SF", "bio": "test"},
    ])
    mongo.user_sessions.insert_many([
        {"user_id": admin_id, "session_token": admin_token, "created_at": now_iso, "expires_at": exp_iso},
        {"user_id": member_id, "session_token": member_token, "created_at": now_iso, "expires_at": exp_iso},
        {"user_id": applicant_id, "session_token": applicant_token, "created_at": now_iso, "expires_at": exp_iso},
    ])

    data = {
        "admin_id": admin_id, "admin_token": admin_token,
        "member_id": member_id, "member_token": member_token,
        "applicant_id": applicant_id, "applicant_token": applicant_token,
        "comped_id": comped_id, "supporter_id": supporter_id,
        "ts": ts,
    }
    yield data
    # Cleanup (don't delete pre-existing admin user, just the session token we added)
    mongo.users.delete_many({"user_id": {"$in": [member_id, applicant_id, comped_id, supporter_id]}})
    mongo.profiles.delete_many({"user_id": {"$in": [member_id, comped_id, supporter_id]}})
    mongo.user_sessions.delete_many({"session_token": {"$in": [admin_token, member_token, applicant_token]}})
    mongo.applications.delete_many({"user_id": applicant_id})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ============================== A. Trending ==============================

class TestTrending:
    def test_trending_defaults(self):
        r = requests.get(f"{BASE_URL}/api/agg/trending", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "hours" in data
        assert data["hours"] == 24
        # Each item should have the required fields
        for it in data["items"]:
            assert "topic" in it and isinstance(it["topic"], str)
            assert "count" in it and it["count"] >= 2  # threshold
            assert "kind" in it and it["kind"] in ("bigram", "trigram")
            assert "article_indices" in it and isinstance(it["article_indices"], list)

    def test_trending_custom_window(self):
        r = requests.get(f"{BASE_URL}/api/agg/trending?hours=168&limit=5", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["hours"] == 168
        assert len(data["items"]) <= 5

    def test_trending_public_no_auth(self):
        # No auth header, should still return 200
        r = requests.get(f"{BASE_URL}/api/agg/trending?hours=24&limit=8", timeout=15)
        assert r.status_code == 200

    def test_trending_bounds(self):
        # hours must be <= 168
        r = requests.get(f"{BASE_URL}/api/agg/trending?hours=999", timeout=15)
        assert r.status_code == 422


# ============================== B. Members filter ==============================

class TestMembersFilter:
    def test_members_non_admin_no_entitlement(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members",
                         headers=_auth(seed_users["member_token"]), timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1
        for row in items:
            # entitlement should be absent (effectively null) for non-admin
            assert row.get("entitlement") is None

    def test_members_non_admin_filter_rejected(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members?filter=comped",
                         headers=_auth(seed_users["member_token"]), timeout=15)
        assert r.status_code == 403

    def test_members_admin_all_have_entitlement(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 3
        for row in items:
            ent = row.get("entitlement")
            assert ent is not None
            assert "tier" in ent and ent["tier"] in ("comped", "supporter", "free")
            assert "partner_tier" in ent
            assert "is_supporter" in ent
            assert "supporter_until" in ent
            assert "source" in ent
            assert "email" in ent

    def test_members_admin_filter_comped(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members?filter=comped",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        # Our seeded comped user must appear; all rows must be comped tier.
        ids = [row["user_id"] for row in items]
        assert seed_users["comped_id"] in ids
        assert seed_users["supporter_id"] not in ids
        for row in items:
            assert row["entitlement"]["tier"] == "comped"

    def test_members_admin_filter_supporter(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members?filter=supporter",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        ids = [row["user_id"] for row in items]
        assert seed_users["supporter_id"] in ids
        assert seed_users["comped_id"] not in ids
        for row in items:
            assert row["entitlement"]["tier"] == "supporter"

    def test_members_admin_filter_free(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/members?filter=free",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        ids = [row["user_id"] for row in items]
        assert seed_users["member_id"] in ids
        assert seed_users["comped_id"] not in ids
        assert seed_users["supporter_id"] not in ids
        for row in items:
            assert row["entitlement"]["tier"] == "free"


# ============================== D. ToS ==============================

class TestToS:
    def test_tos_version_public(self):
        r = requests.get(f"{BASE_URL}/api/applications/tos-version", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "version_hash" in data
        assert "document_url" in data
        assert data["document_url"] == "/legal/terms-of-service.pdf"
        # 64-char hex sha256
        assert re.match(r"^[0-9a-f]{64}$", data["version_hash"]), f"hash={data['version_hash']}"

    def test_apply_without_tos_rejected(self, seed_users, mongo):
        # Clear any pre-existing applications for this applicant
        mongo.applications.delete_many({"user_id": seed_users["applicant_id"]})
        payload = {
            "why_joining": "I want to learn from peers " + ("x" * 20),
            "current_role": "Broker",
            "market": "NYC",
            "years_in_real_estate": "5",
            "tos_accepted": False,
        }
        r = requests.post(f"{BASE_URL}/api/applications", json=payload,
                          headers=_auth(seed_users["applicant_token"]), timeout=15)
        assert r.status_code == 400, r.text
        assert "Terms of Service" in r.json().get("detail", "")

    def test_apply_with_tos_stamps_doc(self, seed_users, mongo):
        # Ensure no prior application for applicant (rate-limit guard from iter19)
        mongo.applications.delete_many({"email": {"$regex": f"applicant.iter20.{seed_users['ts']}@"}})
        # Reset user status if needed
        mongo.users.update_one({"user_id": seed_users["applicant_id"]},
                                {"$set": {"status": "needs_application"}})

        payload = {
            "why_joining": "I want to learn from peers and contribute to the network actively",
            "current_role": "Broker",
            "market": "NYC",
            "years_in_real_estate": "5",
            "tos_accepted": True,
        }
        r = requests.post(f"{BASE_URL}/api/applications", json=payload,
                          headers=_auth(seed_users["applicant_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "pending"
        app_id = data["application_id"]

        # Verify application document stamps
        app_doc = mongo.applications.find_one({"application_id": app_id})
        assert app_doc is not None
        assert app_doc.get("tos_accepted") is True
        assert app_doc.get("tos_accepted_at")
        assert re.match(r"^[0-9a-f]{64}$", app_doc.get("tos_version_hash") or "")
        assert app_doc.get("tos_document_url") == "/legal/terms-of-service.pdf"

        # Verify user document stamps
        u = mongo.users.find_one({"user_id": seed_users["applicant_id"]})
        assert u.get("tos_accepted_at")
        assert re.match(r"^[0-9a-f]{64}$", u.get("tos_version_hash") or "")


# ============================== G. Hashtag regression ==============================

class TestHashtag:
    def test_posts_popular_tags(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/posts/tags/popular",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Should have either "items" or "tags" - check both
        assert isinstance(data, dict)

    def test_posts_by_tag_unknown(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/posts/by-tag/nonexistenttag_iter20",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        # Should return 200 with empty items or 404 - tolerate both shapes
        assert r.status_code in (200, 404)


# ============================== C. Reset DB (LAST) ==============================

class TestResetDB:
    """Run last because /reset deletes non-admin data."""

    def test_preview_non_admin_forbidden(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/admin/preview-db/preview",
                         headers=_auth(seed_users["member_token"]), timeout=15)
        assert r.status_code == 403

    def test_reset_non_admin_forbidden(self, seed_users):
        r = requests.post(f"{BASE_URL}/api/admin/preview-db/reset",
                          headers=_auth(seed_users["member_token"]),
                          json={"confirm": "RESET"}, timeout=15)
        assert r.status_code == 403

    def test_preview_admin_ok(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/admin/preview-db/preview",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "enabled" in data
        assert "preserves" in data
        assert "will_delete" in data
        assert "admin_users" in data["preserves"]
        assert isinstance(data["preserves"]["aggregator_publishers"], int)
        assert isinstance(data["preserves"]["aggregator_articles"], int)

    def test_reset_bad_token(self, seed_users):
        r = requests.post(f"{BASE_URL}/api/admin/preview-db/reset",
                          headers=_auth(seed_users["admin_token"]),
                          json={"confirm": "yes"}, timeout=15)
        assert r.status_code == 400

    def test_reset_succeeds_and_preserves(self, seed_users, mongo):
        # Snapshot aggregator + substack imports before
        pub_count_before = mongo.agg_publishers.count_documents({})
        art_count_before = mongo.agg_articles.count_documents({})
        substack_count_before = mongo.posts.count_documents({"source": "substack_import"})

        # Confirm admin session and applicant session exist before
        assert mongo.user_sessions.find_one({"session_token": seed_users["admin_token"]}) is not None

        r = requests.post(f"{BASE_URL}/api/admin/preview-db/reset",
                          headers=_auth(seed_users["admin_token"]),
                          json={"confirm": "RESET"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "deleted" in data
        assert "preserved" in data

        # Aggregator data must remain
        assert mongo.agg_publishers.count_documents({}) == pub_count_before
        assert mongo.agg_articles.count_documents({}) == art_count_before
        # Substack imports preserved
        assert mongo.posts.count_documents({"source": "substack_import"}) == substack_count_before
        # Admin session preserved
        assert mongo.user_sessions.find_one({"session_token": seed_users["admin_token"]}) is not None
        # Non-admin applications wiped
        assert mongo.applications.count_documents({}) == 0
        # Non-admin users wiped
        assert mongo.users.count_documents({"user_id": seed_users["member_id"]}) == 0
        assert mongo.users.count_documents({"user_id": seed_users["applicant_id"]}) == 0
        # Admin user preserved
        assert mongo.users.count_documents({"user_id": seed_users["admin_id"]}) == 1

    def test_admin_token_still_works_after_reset(self, seed_users):
        r = requests.get(f"{BASE_URL}/api/admin/preview-db/preview",
                         headers=_auth(seed_users["admin_token"]), timeout=15)
        assert r.status_code == 200
