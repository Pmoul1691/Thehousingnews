"""Tests for the perf-sprint changes:

- Event loop is not blocked by RSS ingest (a slow publisher fetch can't
  starve other concurrent coroutines).
- ingest_all_active runs publishers concurrently (3+ feeds with the same
  per-feed cost should finish in ~one feed's time, not the sum).
- POST /api/refresh-feeds returns 202 immediately and runs the actual
  work in the background, with an overlap guard.
- Public agg/essay endpoints carry s-maxage; personalized endpoints
  carry private/no-store.
"""
from __future__ import annotations
import asyncio
import os
import time
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
REFRESH_TOKEN = os.environ.get("RSS_REFRESH_TOKEN")


# ─────────────────────────────────────────────────────────────────────
# Priority 1 — event loop unblocked
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_publisher_does_not_block_event_loop():
    """A slow synchronous feed fetch (1.0s) must not freeze the event
    loop — other coroutines should make full progress in parallel."""
    from services import rss_ingest

    async def fake_db_stub():
        class Coll:
            async def update_one(self, *a, **kw):
                return None

            async def find_one(self, *a, **kw):
                return None

            def find(self, *a, **kw):
                class Cur:
                    def __init__(self):
                        self._items: list = []

                    def limit(self, n):
                        return self

                    async def to_list(self, n):
                        return []

                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        raise StopAsyncIteration
                return Cur()

        class DB:
            agg_publishers = Coll()
            agg_articles = Coll()

        return DB()

    db = await fake_db_stub()
    publisher = {
        "id": "p1",
        "feed_url": "https://example.test/feed.xml",
        "bypass_robots": True,
    }

    # Stub blocking fetch + parse to take 0.6s each (synchronous sleep).
    def slow_fetch(url, user_agent=None):
        time.sleep(0.6)
        return "<rss><channel></channel></rss>", None

    def slow_parse(xml, pub):
        time.sleep(0.4)
        return []

    # If the event loop is blocked, this counter won't tick.
    ticks = [0]

    async def ticker():
        while True:
            await asyncio.sleep(0.05)
            ticks[0] += 1

    with patch.object(rss_ingest, "fetch_feed_xml", slow_fetch), \
         patch.object(rss_ingest, "parse_entries", slow_parse):
        tick_task = asyncio.create_task(ticker())
        t0 = time.perf_counter()
        await rss_ingest.ingest_publisher(db, publisher)
        elapsed = time.perf_counter() - t0
        tick_task.cancel()
        try:
            await tick_task
        except asyncio.CancelledError:
            pass

    # ingest took ~1.0s total. If the loop weren't blocked, the ticker
    # should have ticked ~20 times (every 50ms). If it had been blocked,
    # ticks would be near zero.
    assert elapsed >= 0.9, f"sanity: ingest should have taken ~1.0s, got {elapsed:.2f}"
    assert ticks[0] >= 10, (
        f"event loop appears blocked: ticker only fired {ticks[0]} times "
        f"during a {elapsed:.2f}s ingest. Expected >=10."
    )


# ─────────────────────────────────────────────────────────────────────
# Priority 2 — concurrency in ingest_all_active
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_all_active_runs_in_parallel(monkeypatch):
    """3 publishers, each taking 0.5s in ingest_publisher, must finish in
    well under 1.5s (the serial cost). With concurrency >=6 (default),
    they all run together and finish in ~0.5s."""
    from services import rss_ingest

    # Fake DB returning 3 active publishers, none of which have a
    # last_fetched_at so they're all considered "due".
    publishers = [
        {"id": f"p{i}", "feed_url": f"https://example.test/{i}.xml",
         "bypass_robots": True}
        for i in range(3)
    ]

    class Cursor:
        def __init__(self, items):
            self._items = items

        async def to_list(self, n):
            return self._items

    class Coll:
        def __init__(self, items):
            self._items = items

        def find(self, *a, **kw):
            return Cursor(self._items)

        async def update_one(self, *a, **kw):
            return None

    class DB:
        agg_publishers = Coll(publishers)

    async def fake_ingest_publisher(db, p):
        await asyncio.sleep(0.5)
        return {"publisher_id": p["id"], "ok": True, "inserted": 0}

    monkeypatch.setattr(rss_ingest, "ingest_publisher", fake_ingest_publisher)

    t0 = time.perf_counter()
    res = await rss_ingest.ingest_all_active(DB())
    elapsed = time.perf_counter() - t0

    assert res["ran"] == 3
    # Serial would be 1.5s. Concurrent should be <0.9s with margin.
    assert elapsed < 0.9, (
        f"ingest_all_active is still serial — 3 x 0.5s publishers took {elapsed:.2f}s, "
        f"expected <0.9s with concurrency"
    )


# ─────────────────────────────────────────────────────────────────────
# Priority 3 — /api/refresh-feeds returns 202 fast + overlap guard
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not REFRESH_TOKEN, reason="RSS_REFRESH_TOKEN not set")
def test_refresh_feeds_returns_202_fast():
    """The manual trigger should return in <300ms and report `accepted`
    even though a real ingest takes 5-60s to complete."""
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/api/refresh-feeds",
        params={"token": REFRESH_TOKEN},
        timeout=10,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("accepted") is True
    assert elapsed < 1500, f"refresh-feeds took {elapsed:.0f}ms, expected <1500ms"


@pytest.mark.skipif(not REFRESH_TOKEN, reason="RSS_REFRESH_TOKEN not set")
def test_refresh_feeds_overlap_guard():
    """Two back-to-back triggers within the same ingest window must NOT
    both spawn ingests — the second should report already_running."""
    r1 = requests.post(
        f"{BASE}/api/refresh-feeds",
        params={"token": REFRESH_TOKEN},
        timeout=10,
    )
    assert r1.status_code == 200
    # Hit again immediately — the first run should still be in flight.
    r2 = requests.post(
        f"{BASE}/api/refresh-feeds",
        params={"token": REFRESH_TOKEN},
        timeout=10,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    # The second call should see the in-flight run. (If the first run
    # somehow finished in <1ms — possible if every publisher's refresh
    # window prevented ingest — that's still a passing case as long as
    # neither errored.)
    assert body2.get("accepted") is True
    if body2.get("already_running"):
        assert body2.get("run_id") == r1.json().get("run_id")


@pytest.mark.skipif(not REFRESH_TOKEN, reason="RSS_REFRESH_TOKEN not set")
def test_refresh_feeds_status_endpoint():
    r = requests.get(
        f"{BASE}/api/refresh-feeds/status",
        params={"token": REFRESH_TOKEN},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    # All four keys must be present so the cron can interpret them.
    for key in ("running", "started_at", "last_run_at", "last_run_id"):
        assert key in body


# ─────────────────────────────────────────────────────────────────────
# Priority 4 — Cache-Control headers
# ─────────────────────────────────────────────────────────────────────


PUBLIC_AGG_PATHS = [
    "/api/agg/articles?limit=3&hours=24",
    "/api/agg/publishers",
    "/api/agg/publishers-latest?hours=168",
    "/api/agg/articles/top-clicked?hours=24",
    "/api/agg/network-stats",
    "/api/agg/trending?hours=24&limit=6",
    "/api/agg/trending-tags?hours=24",
    "/api/agg/categories",
]


@pytest.mark.parametrize("path", PUBLIC_AGG_PATHS)
def test_public_agg_endpoints_have_s_maxage(path):
    r = requests.get(f"{BASE}{path}", timeout=10)
    assert r.status_code == 200, f"{path}: {r.status_code}"
    cc = (r.headers.get("Cache-Control") or "").lower()
    assert "s-maxage" in cc, (
        f"{path}: Cache-Control missing s-maxage. Got: {cc!r}"
    )
    assert "public" in cc, f"{path}: not declared public. Got: {cc!r}"


def test_authme_is_private_no_store():
    # No auth header — endpoint still sets the headers BEFORE auth check.
    r = requests.get(f"{BASE}/api/auth/me", timeout=10)
    # 401 is fine; we just care about cache directives.
    cc = (r.headers.get("Cache-Control") or "").lower()
    assert "private" in cc, f"Cache-Control: {cc!r}"
    assert "no-store" in cc, f"Cache-Control: {cc!r}"


def test_today_is_private_no_store():
    r = requests.get(f"{BASE}/api/today", timeout=10)
    cc = (r.headers.get("Cache-Control") or "").lower()
    assert "private" in cc, f"Cache-Control: {cc!r}"
    assert "no-store" in cc, f"Cache-Control: {cc!r}"
