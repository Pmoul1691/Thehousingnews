"""Iter26 — regional feed personalization + onboarding + AI tagger.

Covers:
- GET /api/regions taxonomy shape (54 items in 5 tiers)
- GET/PUT /api/users/me/regions round-trip, taxonomy validation, 8-cap
- POST /api/posts with explicit regions => regions_source='author'
- POST /api/posts without regions => regions=[] + regions_source='pending_ai'
  (background task then populates regions+regions_source='ai')
- GET /api/posts/feed?regions=mine filters by user prefs
- GET /api/posts/feed?regions=chicago,nyc explicit override
- Backend regression: feed still returns items when no regions filter
"""
import os
import time
import asyncio
import requests
import pytest
from pathlib import Path

# Load REACT_APP_BACKEND_URL from /app/frontend/.env if not in environment
_env_url = os.environ.get("REACT_APP_BACKEND_URL")
if not _env_url:
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for line in fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _env_url = line.split("=", 1)[1].strip()
                break
assert _env_url, "REACT_APP_BACKEND_URL must be set"
BASE_URL = _env_url.rstrip("/")
ADMIN_COOKIE = {"session_token": "tok_smoke_admin_v2"}


# ── Seeded session helper: create an approved + verified test user ────
def _seed_user(suffix: str):
    """Create an approved + email_verified + profile-complete user.
    Returns (user_id, token). Uses mongo via REST signup + direct mongosh.
    """
    import subprocess, json
    ts = int(time.time() * 1000)
    user_id = f"TEST_user_regions_{suffix}_{ts}"
    token = f"TEST_tok_regions_{suffix}_{ts}"
    email = f"TEST_regions_{suffix}_{ts}@example.com"
    db = os.environ.get("DB_NAME", "test_database")
    script = f"""
use('{db}');
db.users.insertOne({{
  user_id: '{user_id}', email: '{email}', name: 'Test Regions {suffix}',
  picture: '', is_admin: false, status: 'approved', email_verified: true,
  source: 'manual_test', created_at: new Date().toISOString(),
  last_login_at: new Date().toISOString()
}});
db.user_sessions.insertOne({{
  user_id: '{user_id}', session_token: '{token}',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString()
}});
db.profiles.insertOne({{
  user_id: '{user_id}', name: 'Test Regions {suffix}', market: 'Chicago, IL',
  objectives: ['Test posting'], is_stub: false,
  created_at: new Date().toISOString()
}});
"""
    subprocess.run(["mongosh", "--quiet", "--eval", script], check=True, capture_output=True)
    return user_id, token


def _auth(token):
    return {"Cookie": f"session_token={token}"}


# ── 1. Public taxonomy ─────────────────────────────────────────────────
class TestRegionsTaxonomy:
    def test_taxonomy_shape(self):
        r = requests.get(f"{BASE_URL}/api/regions", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "grouped" in data
        # 18 city + 14 metro + 17 state + 4 region + 1 national = 54
        assert len(data["items"]) == 54
        g = data["grouped"]
        assert len(g["city"]) == 18
        assert len(g["metro"]) == 14
        assert len(g["state"]) == 17
        assert len(g["region"]) == 4
        assert len(g["national"]) == 1
        # Spot check slug + label fields
        first = data["items"][0]
        assert "slug" in first and "label" in first and "tier" in first


# ── 2. User region prefs round-trip ────────────────────────────────────
class TestUserRegions:
    def test_get_empty_default(self):
        _, token = _seed_user("get_empty")
        r = requests.get(f"{BASE_URL}/api/users/me/regions", headers=_auth(token), timeout=10)
        assert r.status_code == 200
        assert r.json() == {"regions": []}

    def test_put_then_get_persists(self):
        _, token = _seed_user("put_get")
        # PUT
        r = requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": ["chicago", "midwest"]}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json() == {"regions": ["chicago", "midwest"]}
        # GET
        r2 = requests.get(f"{BASE_URL}/api/users/me/regions", headers=_auth(token), timeout=10)
        assert r2.status_code == 200
        assert r2.json() == {"regions": ["chicago", "midwest"]}

    def test_invalid_slugs_dropped(self):
        _, token = _seed_user("invalid")
        r = requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": ["chicago", "not-a-real-region", "midwest", "fake"]},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json() == {"regions": ["chicago", "midwest"]}

    def test_caps_at_8(self):
        _, token = _seed_user("cap8")
        slugs = ["chicago", "nyc", "la", "boston", "miami", "denver", "seattle", "austin", "philadelphia", "phoenix"]
        r = requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": slugs}, timeout=10,
        )
        assert r.status_code == 200
        assert len(r.json()["regions"]) == 8

    def test_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/users/me/regions", timeout=10)
        assert r.status_code in (401, 403)
        r2 = requests.put(f"{BASE_URL}/api/users/me/regions", json={"regions": []}, timeout=10)
        assert r2.status_code in (401, 403)


# ── 3. POST /api/posts regions handling ────────────────────────────────
class TestPostRegions:
    def test_explicit_regions_author_source(self):
        _, token = _seed_user("author_post")
        r = requests.post(
            f"{BASE_URL}/api/posts",
            headers=_auth(token),
            json={"kind": "post", "text": "Hello with explicit tags about Chicago real estate.", "regions": ["chicago", "midwest"]},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        post_id = r.json()["post_id"]
        # Look up via mongo
        import subprocess
        db = os.environ.get("DB_NAME", "test_database")
        result = subprocess.run(
            ["mongosh", "--quiet", "--eval",
             f"use('{db}'); JSON.stringify(db.posts.findOne({{post_id:'{post_id}'}}, {{_id:0,regions:1,regions_source:1}}))"],
            capture_output=True, text=True, check=True,
        )
        # Output contains the JSON line
        out = result.stdout.strip()
        assert "author" in out
        assert "chicago" in out
        assert "midwest" in out

    def test_omitted_regions_pending_ai(self):
        _, token = _seed_user("ai_post")
        r = requests.post(
            f"{BASE_URL}/api/posts",
            headers=_auth(token),
            json={"kind": "post", "text": "A generic short post about industry trends nationwide."},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        post_id = r.json()["post_id"]
        # Immediately after creation, regions=[] and source=pending_ai OR
        # background task has already run and set source=ai.
        import subprocess, json as _json
        db = os.environ.get("DB_NAME", "test_database")
        result = subprocess.run(
            ["mongosh", "--quiet", "--eval",
             f"use('{db}'); JSON.stringify(db.posts.findOne({{post_id:'{post_id}'}}, {{_id:0,regions:1,regions_source:1}}))"],
            capture_output=True, text=True, check=True,
        )
        out = result.stdout.strip()
        assert ("pending_ai" in out) or ("\"ai\"" in out), out


# ── 4. Feed filtering by regions ───────────────────────────────────────
class TestFeedRegions:
    def test_feed_regions_mine(self):
        uid, token = _seed_user("feed_mine")
        # Set user's regions to chicago only
        requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": ["chicago"]}, timeout=10,
        )
        # Seed two posts directly in Mongo to bypass AI moderation flagging.
        # We're testing the feed *filter* logic, not the create flow.
        import subprocess
        ts = int(time.time() * 1000)
        p1 = f"TEST_post_chi_{ts}"
        p2 = f"TEST_post_nyc_{ts}"
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = os.environ.get("DB_NAME", "test_database")
        script = f"""
use('{db}');
db.posts.insertMany([
  {{post_id:'{p1}', user_id:'{uid}', kind:'essay', title:'Chicago Test',
    text:'Chicago industrial absorption update.', tags:[], media:[], image_path:null,
    status:'approved', created_at:'{past}', release_at:'{past}',
    regions:['chicago'], regions_source:'author'}},
  {{post_id:'{p2}', user_id:'{uid}', kind:'essay', title:'NYC Test',
    text:'Manhattan leasing update.', tags:[], media:[], image_path:null,
    status:'approved', created_at:'{past}', release_at:'{past}',
    regions:['nyc'], regions_source:'author'}}
]);
"""
        subprocess.run(["mongosh", "--quiet", "--eval", script], check=True, capture_output=True)

        # regions=mine → user has [chicago] → should include p1, exclude p2
        r = requests.get(
            f"{BASE_URL}/api/posts/feed?regions=mine", headers=_auth(token), timeout=15,
        )
        assert r.status_code == 200
        ids = {i["post_id"] for i in r.json()["items"]}
        assert p1 in ids, f"Chicago post should be in feed (user regions=[chicago])"
        assert p2 not in ids, f"NYC post should NOT be in feed (user regions=[chicago])"

        # Now set user regions to include both → both posts appear
        requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": ["chicago", "nyc"]}, timeout=10,
        )
        r = requests.get(
            f"{BASE_URL}/api/posts/feed?regions=mine", headers=_auth(token), timeout=15,
        )
        ids = {i["post_id"] for i in r.json()["items"]}
        assert p1 in ids and p2 in ids

    def test_feed_regions_explicit_override(self):
        uid, token = _seed_user("feed_explicit")
        # User has midwest only saved
        requests.put(
            f"{BASE_URL}/api/users/me/regions",
            headers=_auth(token), json={"regions": ["midwest"]}, timeout=10,
        )
        # Seed a chicago post directly to skip AI moderation
        import subprocess
        from datetime import datetime, timezone, timedelta
        ts = int(time.time() * 1000)
        p1 = f"TEST_post_chi_exp_{ts}"
        past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = os.environ.get("DB_NAME", "test_database")
        script = f"""
use('{db}');
db.posts.insertOne({{post_id:'{p1}', user_id:'{uid}', kind:'essay', title:'Chi Exp',
  text:'Chi text', tags:[], media:[], image_path:null,
  status:'approved', created_at:'{past}', release_at:'{past}',
  regions:['chicago'], regions_source:'author'}});
"""
        subprocess.run(["mongosh", "--quiet", "--eval", script], check=True, capture_output=True)
        # Explicit ?regions=chicago should return it (overrides 'midwest' pref)
        r = requests.get(
            f"{BASE_URL}/api/posts/feed?regions=chicago",
            headers=_auth(token), timeout=15,
        )
        assert r.status_code == 200
        ids = {i["post_id"] for i in r.json()["items"]}
        assert p1 in ids

    def test_feed_no_filter_returns_items(self):
        _, token = _seed_user("feed_all")
        r = requests.get(f"{BASE_URL}/api/posts/feed", headers=_auth(token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data.get("regions") == []


# ── 5. AI tagger smoke ─────────────────────────────────────────────────
class TestAITagger:
    def test_tag_post_returns_list(self):
        """Direct import test of the tagger. Calls live Claude — skip if key missing."""
        import sys
        sys.path.insert(0, "/app/backend")
        try:
            from services.region_tagger import tag_post
        except Exception as e:
            pytest.skip(f"region_tagger import failed: {e}")
        try:
            result = asyncio.run(tag_post("A new high-rise project broke ground in downtown Chicago this week."))
        except Exception as e:
            pytest.skip(f"LLM call failed: {e}")
        assert isinstance(result, list)
        # Don't assert specific tags — just that it's a valid list of strings
        for s in result:
            assert isinstance(s, str)
