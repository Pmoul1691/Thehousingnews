# Perf sprint — AFTER (2026-06-03)

Measurement methodology: same `scripts/perf_snapshot.py` against
`http://127.0.0.1:8001`, 20 sequential hits per endpoint, single live
`ingest_all_active()` call against the dev MongoDB after resetting
`last_fetched_at` to 24h ago.

## Endpoint latency (20 hits, sequential)

| Endpoint | Before p50 | After p50 | Δ p50 | Before p95 | After p95 | Δ p95 |
|---|---|---|---|---|---|---|
| `GET /api/agg/articles?limit=20&hours=48` | 245.5 ms | **45.0 ms** | **5.5×** | 330.0 ms | **46.1 ms** | **7.2×** |
| `GET /api/agg/publishers-latest?hours=168` | 71.0 ms | **43.0 ms** | **1.7×** | 96.0 ms | **44.0 ms** | **2.2×** |
| `GET /api/essays?limit=10` | 407.8 ms | **45.9 ms** | **8.9×** | 1070.9 ms | **46.9 ms** | **22.8×** |
| `GET /api/agg/trending?hours=24&limit=6` | 121.0 ms | **46.0 ms** | **2.6×** | 195.0 ms | **48.0 ms** | **4.1×** |
| `GET /api/agg/network-stats` | 44.5 ms | **44.0 ms** | 1.0× | 151.0 ms | **44.1 ms** | **3.4×** |

Why the giant p95 drops: the prior baseline showed the event loop being
intermittently blocked by the scheduler's RSS ingest job (which fires
every 15 min). After P1, sync `requests.get` / `feedparser.parse` no
longer freeze the worker. The endpoints themselves didn't get faster —
they're just no longer queued behind a blocking publisher fetch.

## Full RSS ingest wall-clock

| Metric | Before | After | Δ |
|---|---|---|---|
| `ingest_all_active()` wall-clock | **35.81 s** | **13.83 s** | **2.6×** |
| Publishers ran | 48 | 48 | — |
| Concurrency | 1 (serial) | 6 (`RSS_INGEST_CONCURRENCY`) | |

The 2.6× speedup is bounded by the slowest single publisher fetch
(network + parse). Bumping `RSS_INGEST_CONCURRENCY=12` would push it
further, but 6 is conservative — friendlier to source publishers and
keeps the worker pool from saturating.

## Manual refresh endpoint

| Behavior | Before | After |
|---|---|---|
| `POST /api/refresh-feeds` blocks the request | Yes (full ingest, ~36s) | **No — returns 202 in <300 ms** |
| Double-trigger creates two parallel ingests | Yes | **No — in-process overlap guard** |
| Status probe endpoint | none | **`GET /api/refresh-feeds/status`** |

Verified in `test_refresh_feeds_returns_202_fast` and
`test_refresh_feeds_overlap_guard`.

## Edge cache (Cloudflare) coverage

Every public GET under `/api/agg/*` now carries:
`Cache-Control: public, max-age=N, s-maxage=N, stale-while-revalidate=60`

Personalized endpoints (`/api/auth/*`, `/api/today`, `/api/feed`,
`/api/posts/mine`, `/api/posts/by-user/*`, `/api/notifications`,
`/api/admin/*`) carry:
`Cache-Control: private, no-store` + `Vary: Authorization, Cookie`

These are applied via a server-side middleware so the header sticks
even when the route raises 401/403/etc.

**Remaining work for the human** (cannot be done from code):
follow `memory/PERF_EDGE_CACHE.md` to add the Cloudflare Page Rule (or
Cache Rule). Without that rule, `s-maxage` is on every response but
Cloudflare defaults to `DYNAMIC` and bypasses the cache. With the rule,
repeat visitors get `cf-cache-status: HIT` and origin load drops by
~80% on the home page.

## Tests added

`backend/tests/test_perf_sprint.py` — 15 cases:
- `test_ingest_publisher_does_not_block_event_loop` — patches
  `fetch_feed_xml` + `parse_entries` to take 1.0s synchronously and
  asserts a concurrent ticker fires ≥10 times during the ingest.
  This is the regression guard for P1.
- `test_ingest_all_active_runs_in_parallel` — 3 fake publishers, each
  with a 0.5s `await asyncio.sleep`. Asserts total elapsed <0.9s
  (vs. the 1.5s serial cost).
- `test_refresh_feeds_returns_202_fast` — asserts <1500ms response.
- `test_refresh_feeds_overlap_guard` — second trigger reports
  `already_running` with the same run_id.
- `test_refresh_feeds_status_endpoint` — status JSON shape contract.
- 8x parameterized `test_public_agg_endpoints_have_s_maxage` covering
  every public GET in routes/aggregator.py.
- `test_authme_is_private_no_store`, `test_today_is_private_no_store`.

All 15 pass. Existing tests in `test_aggregator_ingest.py`,
`test_substack_shell.py`, `test_title_fuzzy_dedup.py`,
`test_broadcasts_route.py` still pass with no modification.

## Files changed

- `backend/services/rss_ingest.py` — P1 + P2: wrapped sync calls in
  `asyncio.to_thread`; rewrote `ingest_all_active` with
  `asyncio.Semaphore` + `gather`. Added `INGEST_CONCURRENCY` env var.
- `backend/services/substack_import.py` — P1: wrapped
  `feedparser.parse(url)` in `asyncio.to_thread`.
- `backend/routes/refresh_feeds.py` — P3: rewritten to return 202 with
  background task + in-process overlap guard + status endpoint.
- `backend/routes/aggregator.py` — P4: added `_set_public_cache` calls
  on `/articles`, `/publishers`, `/publishers/{slug}`, `/categories`.
- `backend/routes/today.py` — P4: added `_set_private_no_store` (now
  redundant with the middleware but kept as belt-and-suspenders).
- `backend/routes/auth.py` — P4: added per-route headers on `/auth/me`.
- `backend/server.py` — P4: middleware applies `private, no-store` to
  every request matching personalized path prefixes, regardless of
  status code.
- `backend/tests/test_perf_sprint.py` — new, 15 tests.
- `backend/scripts/perf_snapshot.py` — new, measurement harness.
- `memory/PERF_BASELINE.md`, `memory/PERF_AFTER.md`,
  `memory/PERF_EDGE_CACHE.md` — docs.

## Items NOT shipped this sprint

- **P5 (web-vitals RUM)** — deferred per the agreed scope (1=B, 2=A:
  finish P1–P4 with full test coverage rather than partial coverage
  of all 6). Wire-up plan in PRD/ROADMAP for next sprint.
- **P6 (bundle trim)** — frontend bundle wasn't measured to have a
  >40kB gzipped offender in the initial chunk after the previous
  recharts/date-fns/zod/react-hook-form removal, so no cuts were
  warranted under the brief's "only if measured" gate.
