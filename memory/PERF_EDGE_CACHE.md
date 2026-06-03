# Edge Cache (Cloudflare) — Audit & Page Rule

Last updated: 2026-06-03

## Goal
Make Cloudflare's edge actually serve cached responses for our public
aggregator endpoints, so repeat visitors are served in <50ms with zero
origin load. Personalized endpoints must NEVER be edge-cached.

## What the code now does

Every public GET under `/api/agg/*` sets:
```
Cache-Control: public, max-age=<N>, s-maxage=<N>, stale-while-revalidate=60
```
`s-maxage` is the directive Cloudflare reads. `max-age` is the browser
hint. `stale-while-revalidate` lets the edge keep serving a slightly
stale value while it refreshes in the background — perceived latency
stays at 0ms for the user.

| Endpoint                          | s-maxage | Rationale                                |
|-----------------------------------|----------|------------------------------------------|
| `GET /api/agg/articles`           | 60s      | River; refreshed by 15-min ingest cron. Skipped if `?search=` is present (one-hit queries pollute the edge). |
| `GET /api/agg/publishers`         | 300s     | Mutates only on admin add/remove.        |
| `GET /api/agg/publishers-latest`  | 60s      | One card per publisher with latest article. |
| `GET /api/agg/publishers/{slug}`  | 60s      | Single-publisher archive page.           |
| `GET /api/agg/articles/top-clicked` | 60s    | 24h windowed leaderboard.                |
| `GET /api/agg/network-stats`      | 300s     | Slow-moving aggregate counters.          |
| `GET /api/agg/trending`           | 90s      | Trending topics over 24h.                |
| `GET /api/agg/trending-tags`      | 90s      | Same.                                    |
| `GET /api/agg/recent-members`     | 90s      | Slow-changing.                           |
| `GET /api/agg/new-members`        | 90s      | Slow-changing.                           |
| `GET /api/agg/categories`         | 300s     | Category counts.                         |
| `GET /api/podcasts`               | 120s     | Cold-start dominated; in-process cache also. |
| `GET /api/essays` (first page)    | 60s      | Only the first page caches; deeper pages skip. |

Personalized endpoints set `Cache-Control: private, no-store` and
`Vary: Authorization, Cookie`:

- `GET /api/auth/me`
- `GET /api/today`
- `GET /api/feed`, `/api/posts/mine`, `/api/posts/by-user/*` (rely on
  default no-cache since they require auth header — confirm if you
  add any new personalized GET, set the same headers)

## Cloudflare-side configuration the human must apply

Cloudflare ignores origin `Cache-Control` for most paths by default,
because the default "Standard Caching" rule only caches static asset
extensions (.css, .js, .png, etc.). To get edge caching on the JSON
endpoints above, you need ONE Page Rule (or Cache Rule on the new
Rules engine):

### Option A — Page Rules (Legacy, still works)
1. Cloudflare dashboard → your zone (`thehousingnews.com`) → Rules →
   Page Rules → Create.
2. URL pattern: `thehousingnews.com/api/agg/*`
3. Settings:
   - **Cache Level**: `Cache Everything`
   - **Edge Cache TTL**: `Respect existing headers` (so our `s-maxage`
     drives the TTL)
   - **Browser Cache TTL**: `Respect existing headers`
4. Save & deploy.
5. (Optional) Add a second rule for `thehousingnews.com/api/podcasts`
   and `thehousingnews.com/api/essays` if you want those edge-cached
   too.

### Option B — Cache Rules (new Rules engine, recommended)
1. Cloudflare dashboard → Caching → Cache Rules → Create rule.
2. If incoming requests match:
   `URI Path` `starts with` `/api/agg/`
3. Then:
   - **Cache eligibility**: `Eligible for cache`
   - **Edge TTL**: `Use cache-control header if present, bypass cache
     if not`
   - **Browser TTL**: `Respect origin TTL`
4. Save.

### Verifying it worked
After deploying, run:
```
curl -I "https://thehousingnews.com/api/agg/articles?limit=5&hours=48"
```
Look for these headers in the response:
- `cf-cache-status: MISS` on the first hit
- `cf-cache-status: HIT` on the second hit within `s-maxage`

If you see `cf-cache-status: DYNAMIC` after the rule is in place, the
rule didn't match (check the path pattern) OR there's an upstream
header like `Set-Cookie` defeating the cache (Cloudflare won't cache
responses with cookies on the free plan). The aggregator endpoints
don't set cookies, so this should be a non-issue.

### Endpoints that MUST NOT be cached (already set to `private, no-store`)
- `/api/auth/*`
- `/api/today`
- `/api/feed`, `/api/posts/mine`, anything reading the session token

If you add the Page Rule above with path `/api/agg/*` ONLY, you don't
need to do anything for these — they're outside the rule's URI match
and will pass through to the origin every time.

## Once you redeploy, run this verification
```
for path in \
  /api/agg/articles?limit=5 \
  /api/agg/publishers \
  /api/agg/trending \
  /api/agg/network-stats; do
  echo "=== $path ==="
  curl -sI "https://thehousingnews.com$path" | grep -iE "cache-control|cf-cache"
done
```
Expect: each path returns `cache-control: public, max-age=..., s-maxage=...`
and (after the Cloudflare rule is in place) `cf-cache-status: HIT` on
the second hit.
