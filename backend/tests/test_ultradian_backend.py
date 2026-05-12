"""Backend API tests for The Ultradian Network."""
import json
import re
import time
import requests
import pytest


# ---- Helpers ----

def _no_underscore_id(obj):
    """Recursively check no '_id' key in JSON."""
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Found _id in response: {obj}"
        for v in obj.values():
            _no_underscore_id(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_underscore_id(v)


# ---- Module: Health & release window ----

class TestHealth:
    def test_root(self, http, base_url):
        r = http.get(f"{base_url}/api/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "name" in data

    def test_release_window(self, http, base_url):
        r = http.get(f"{base_url}/api/release-window")
        assert r.status_code == 200
        data = r.json()
        assert "next_release_iso" in data
        assert data["timezone"] == "America/Chicago"
        # iso parseable
        from datetime import datetime
        datetime.fromisoformat(data["next_release_iso"])
        # label should contain am/pm
        assert re.search(r"(am|pm)", data["next_release_label"]) is not None


# ---- Module: Auth /api/auth/me ----

class TestAuthMe:
    def test_me_without_token(self, http, base_url):
        r = http.get(f"{base_url}/api/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, http, base_url, approved_user, bearer):
        r = http.get(f"{base_url}/api/auth/me", headers=bearer(approved_user["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == approved_user["user_id"]
        assert data["email"] == approved_user["email"]
        assert data["status"] == "approved"
        _no_underscore_id(data)

    def test_logout_clears_session(self, http, base_url, approved_user, bearer):
        # logout
        r = http.post(f"{base_url}/api/auth/logout", headers=bearer(approved_user["token"]))
        assert r.status_code == 200
        # subsequent /me must 401
        r2 = http.get(f"{base_url}/api/auth/me", headers=bearer(approved_user["token"]))
        assert r2.status_code == 401


# ---- Module: Applications ----

class TestApplications:
    def test_submit_application_flow(self, http, base_url, needs_app_user, admin_user, bearer):
        payload = {
            "why_joining": "I want to network with other operators in Chicago real estate.",
            "current_role": "Broker",
            "market": "Chicago, IL",
            "years_in_real_estate": "8",
        }
        r = http.post(f"{base_url}/api/applications", json=payload,
                      headers=bearer(needs_app_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "pending"
        assert "application_id" in data
        app_id = data["application_id"]
        _no_underscore_id(data)

        # /api/auth/me should now show status pending
        me = http.get(f"{base_url}/api/auth/me", headers=bearer(needs_app_user["token"]))
        assert me.json()["status"] == "pending"

        # /applications/mine returns the submitted doc
        mine = http.get(f"{base_url}/api/applications/mine", headers=bearer(needs_app_user["token"]))
        assert mine.status_code == 200
        mdata = mine.json()
        assert mdata.get("application_id") == app_id
        assert mdata.get("status") == "pending"
        _no_underscore_id(mdata)

        # Admin can list pending
        lst = http.get(f"{base_url}/api/applications?status=pending",
                       headers=bearer(admin_user["token"]))
        assert lst.status_code == 200
        ids = [it["application_id"] for it in lst.json()["items"]]
        assert app_id in ids
        _no_underscore_id(lst.json())

        # Non-admin cannot list
        forb = http.get(f"{base_url}/api/applications",
                        headers=bearer(needs_app_user["token"]))
        assert forb.status_code == 403

        # Approve flips status
        appr = http.post(f"{base_url}/api/applications/{app_id}/approve",
                         json={"note": "ok"}, headers=bearer(admin_user["token"]))
        assert appr.status_code == 200
        # user should now be approved
        me2 = http.get(f"{base_url}/api/auth/me", headers=bearer(needs_app_user["token"]))
        assert me2.json()["status"] == "approved"

    def test_decline_application(self, http, base_url, needs_app_user, admin_user, bearer):
        payload = {
            "why_joining": "Just want to see the network and decide later about joining.",
            "current_role": "Investor",
            "market": "Austin, TX",
            "years_in_real_estate": "3",
        }
        r = http.post(f"{base_url}/api/applications", json=payload,
                      headers=bearer(needs_app_user["token"]))
        assert r.status_code == 200
        app_id = r.json()["application_id"]

        d = http.post(f"{base_url}/api/applications/{app_id}/decline",
                      json={"note": "not a fit"}, headers=bearer(admin_user["token"]))
        assert d.status_code == 200
        me = http.get(f"{base_url}/api/auth/me", headers=bearer(needs_app_user["token"]))
        assert me.json()["status"] == "declined"


# ---- Module: Profiles ----

class TestProfiles:
    def test_unapproved_put_403(self, http, base_url, needs_app_user, bearer):
        payload = {
            "name": "X", "market": "Chicago", "bio": "Hi",
            "objectives": ["a a a", "b b b", "c c c"],
        }
        r = http.put(f"{base_url}/api/profile", json=payload,
                     headers=bearer(needs_app_user["token"]))
        assert r.status_code == 403

    def test_put_requires_exactly_3_objectives(self, http, base_url, approved_user, bearer):
        bad = {
            "name": "Test", "market": "Chicago", "bio": "Bio",
            "objectives": ["only one", "only two"],
        }
        r = http.put(f"{base_url}/api/profile", json=bad,
                     headers=bearer(approved_user["token"]))
        assert r.status_code == 422

    def test_put_bio_max_280(self, http, base_url, approved_user, bearer):
        bad = {
            "name": "Test", "market": "Chicago", "bio": "x" * 281,
            "objectives": ["o1", "o2", "o3"],
        }
        r = http.put(f"{base_url}/api/profile", json=bad,
                     headers=bearer(approved_user["token"]))
        assert r.status_code == 422

    def test_put_and_versioning(self, http, base_url, approved_user, bearer):
        payload = {
            "name": "Approved Member",
            "market": "Chicago, IL",
            "bio": "Selling homes.",
            "objectives": ["List 12", "Build team", "Write daily"],
        }
        r = http.put(f"{base_url}/api/profile", json=payload,
                     headers=bearer(approved_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["objectives_version"] == 1
        assert data["objectives"] == payload["objectives"]
        _no_underscore_id(data)

        # PUT again with SAME objectives: version unchanged
        r2 = http.put(f"{base_url}/api/profile", json=payload,
                      headers=bearer(approved_user["token"]))
        assert r2.status_code == 200
        assert r2.json()["objectives_version"] == 1

        # PUT with new objectives: version bumped
        payload2 = dict(payload, objectives=["New 1", "New 2", "New 3"])
        r3 = http.put(f"{base_url}/api/profile", json=payload2,
                      headers=bearer(approved_user["token"]))
        assert r3.status_code == 200
        assert r3.json()["objectives_version"] == 2

    def test_get_profile_by_user_id(self, http, base_url, approved_user, bearer):
        # 404 first
        r = http.get(f"{base_url}/api/profile/user_doesnotexist_xyz",
                     headers=bearer(approved_user["token"]))
        assert r.status_code == 404

        # Create profile then get
        payload = {
            "name": "Approved Member", "market": "Chicago",
            "bio": "Bio", "objectives": ["a a", "b b", "c c"],
        }
        http.put(f"{base_url}/api/profile", json=payload,
                 headers=bearer(approved_user["token"]))
        r2 = http.get(f"{base_url}/api/profile/{approved_user['user_id']}",
                      headers=bearer(approved_user["token"]))
        assert r2.status_code == 200
        _no_underscore_id(r2.json())


# ---- Module: Posts ----

class TestPosts:
    def test_unapproved_cannot_post(self, http, base_url, needs_app_user, bearer):
        r = http.post(f"{base_url}/api/posts",
                      json={"text": "Hi"},
                      headers=bearer(needs_app_user["token"]))
        assert r.status_code == 403

    def test_post_text_max_500(self, http, base_url, approved_user, bearer):
        r = http.post(f"{base_url}/api/posts",
                      json={"text": "x" * 501},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 422

    def test_create_post_and_public_feed(self, http, base_url, approved_user, bearer):
        unique = f"TEST_POST_{int(time.time()*1000)} Wabansia 4-flat insight."
        r = http.post(f"{base_url}/api/posts",
                      json={"text": unique},
                      headers=bearer(approved_user["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["post_id"].startswith("post_")
        _no_underscore_id(data)

        # Public feed (no auth)
        pub = requests.get(f"{base_url}/api/posts/public")
        assert pub.status_code == 200
        items = pub.json()["items"]
        texts = [it["text"] for it in items]
        assert unique in texts
        _no_underscore_id(pub.json())
        # Each item has author and post_id, no _id
        for it in items:
            assert "post_id" in it
            assert "author" in it
            assert "_id" not in it

    def test_feed_only_approved(self, http, base_url, needs_app_user, approved_user, bearer):
        # needs_application user gets empty list
        r = http.get(f"{base_url}/api/posts/feed",
                     headers=bearer(needs_app_user["token"]))
        assert r.status_code == 200
        assert r.json()["items"] == []

        # approved gets posts
        r2 = http.get(f"{base_url}/api/posts/feed",
                      headers=bearer(approved_user["token"]))
        assert r2.status_code == 200
        assert isinstance(r2.json()["items"], list)
        _no_underscore_id(r2.json())
