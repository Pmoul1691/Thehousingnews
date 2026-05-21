# Day 1 — Performance Baseline & Top 10 Wins

_Generated 2026-02-21. All measurements from production (https://thehousingnews.com)._

## TL;DR — The site is already fast. Most wins are now image- and bundle-related.

| Metric | Desktop | Mobile (iPhone 14 viewport) | Industry benchmark |
|---|---|---|---|
| First Contentful Paint (FCP) | **152 ms** | **264 ms** | <1.8s = "good" |
| DOM content loaded | 58 ms | 164 ms | — |
| Load event | 225 ms | 539 ms | — |
| Time to first byte | ~0 ms (Cloudflare cached) | — | <800ms = "good" |
| Slowest API call | 136 ms (`trending-tags`) | 204 ms (pageview tracker) | — |

**Verdict**: post the Feb 20 async + caching fixes, backend is no longer the bottleneck. Every signed-out API call is ≤140ms. The remaining wins are about **bytes shipped to the browser** (JS bundle + images), not server speed.

---

## Top 10 ranked wins, biggest impact first

### 🥇 1. Code-split routes — single biggest win available
- **Now**: 1 JS bundle, **711 kB gzipped / 2.5 MB uncompressed**. All 38 pages ship to every visitor, even the landing-page tire-kicker.
- **Why it matters**: a first-time mobile visitor on slow 4G pays the full 2.5 MB before they see anything that depends on JS.
- **Fix**: `React.lazy()` + `<Suspense>` for `/admin/*`, `/write`, `/today`, `/podcasts`, `/library`, `/prompts`, `/email-health`, `/onboarding`, `/settings`, the entire `Agg*` admin set.
- **Est. savings**: ~300–400 kB gzipped off the first-load chunk.
- **Risk**: low. Skeletons already exist for fallbacks.
- **Day**: Day 2.

### 🥈 2. Replace the 186 kB PNG logo
- **Now**: `https://thehousingnews.com/brand/logo-full.png` weighs **186 kB**. That's a logo.
- **Fix**: ship the same wordmark as a 4–10 kB inline SVG or WebP.
- **Est. savings**: ~175 kB on every page load.
- **Risk**: cosmetic verification only.
- **Day**: Day 3.

### 🥉 3. Convert publisher/hero images to WebP + `srcset`
- **Now**: the landing-page hero images are 50–242 kB JPGs. Top single image: a 242 kB JPG (member commentary thumbnail). Total image weight on mobile: **710 kB**.
- **Fix**: re-encode user-uploaded thumbnails to WebP at upload time + serve a `?w=480` mobile-sized variant via `srcset`.
- **Est. savings**: 250–400 kB on mobile landing.
- **Risk**: needs object-storage tweak to re-process existing images (background backfill job).
- **Day**: Day 3.

### 4. Lazy-load below-the-fold images
- **Now**: no `loading="lazy"` attribute anywhere — every card image fires at page load even if it's 8 cards down.
- **Fix**: add `loading="lazy"` + explicit `width`/`height` to `DailyCard`, `MemberCommentaryCard`, podcast cards.
- **Est. savings**: defer ~400 kB until scroll; +CLS improvement (no layout shift).
- **Risk**: very low.
- **Day**: Day 3.

### 5. Dynamic-import TipTap (the rich text editor)
- **Now**: TipTap (`@tiptap/react` + 4 extensions + ProseMirror) ships on every page. It's only used in `/write`.
- **Fix**: `await import('@tiptap/react')` inside `RichTextEditor` so the chunk is fetched only when a user opens the composer.
- **Est. savings**: ~120 kB gzipped off first-load JS.
- **Risk**: low.
- **Day**: Day 2 (rolled into the code-split pass).

### 6. Add long-cache headers to static JS/CSS/img assets
- **Now**: Cloudflare is already in front (TTFB ≈ 0), but I haven't verified `Cache-Control: max-age=31536000, immutable` is set on hashed asset filenames.
- **Fix**: confirm hashed assets get a 1-year immutable cache header. Already true if Emergent's CDN respects CRA's default.
- **Est. savings**: repeat visits become instant (0 bytes downloaded for unchanged JS/CSS).
- **Risk**: zero; this is a verification.
- **Day**: Day 4 audit.

### 7. Reduce eager Radix UI imports in shared components
- **Now**: 28 Radix UI primitives in `package.json`. Some are only used in admin/settings pages.
- **Fix**: confirm tree-shaking is hauling out the unused ones. If not, hoist Radix imports up to their consuming pages so they ride along in those routes' chunks.
- **Est. savings**: 20–60 kB gzipped (modest).
- **Risk**: low.
- **Day**: Day 4.

### 8. Aggregator card images: explicit `width`/`height`
- **Now**: cards render images without dimensions → CLS jank when each card loads its thumbnail.
- **Fix**: hard-code aspect ratio via `aspect-[16/9]` or `width="640" height="360"`.
- **Est. savings**: CLS metric improvement (no layout shift). Score, not bytes.
- **Risk**: very low.
- **Day**: Day 3.

### 9. Aggregator API: HTTP cache headers
- **Now**: my in-process 60–90s caches save the server, but every browser still does a full round-trip every time.
- **Fix**: add `Cache-Control: public, max-age=60` to `/api/agg/podcasts`, `/api/agg/publishers-latest`, `/api/agg/trending-tags`, `/api/agg/recent-members`, `/api/agg/new-members`, `/api/agg/articles/top-clicked`, `/api/essays?limit=12`. Cloudflare will then edge-cache them.
- **Est. savings**: 100% of repeat-visit API calls go to edge (≈10 ms instead of ≈130 ms).
- **Risk**: very low — these are public and already cached server-side.
- **Day**: Day 4.

### 10. Prefetch the obvious next click on landing
- **Now**: clicking "Read today's brief" on `/news` makes you wait for `/today`'s JS chunk + the daily-brief API.
- **Fix**: `<link rel="prefetch">` for the top 3 next-routes (`/today`, `/feed`, `/news`) once the landing page is idle.
- **Est. savings**: perceived-instant transitions between top routes.
- **Risk**: low — only fetches a few kB on idle.
- **Day**: Day 5.

---

## Non-issues I confirmed (so we don't waste days on them)

- ❌ Backend slowness — every endpoint is now 100–260 ms. The Feb 20 fixes cleared this.
- ❌ No moment.js / lodash / react-quill / recharts bloat. Bundle is clean of usual suspects.
- ❌ No render-blocking external scripts beyond Cloudflare RUM + Google Analytics (both deferred).
- ❌ DB indexes — fine on the core collections. (Will spot-check on Day 4.)

---

## What I didn't measure today (but should before declaring victory on Day 7)

- LCP value: the LCP didn't trigger in my Playwright run because the landing has no single dominant image. Should re-run after image fixes land.
- INP (Interaction-to-Next-Paint): would need a real-user-monitoring window or a longer Playwright session.
- TBT (Total Blocking Time): worth measuring after Day 2 ships, since the eager JS bundle is the biggest contributor.
- Signed-in pages (Feed, Write, Today): no admin token used in Playwright — Day 4 or 5 sweep should cover.
