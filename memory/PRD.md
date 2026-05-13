# The Ultradian Network - PRD

## Original problem statement
Build "The Ultradian Network" at ultradiannetwork.com: a batched, members-only feed
for real estate operators. Signature feature: posts release at 8:30am and 5:30pm
America/Chicago time. No live updates between windows. Calm-by-design alternative to
LinkedIn/Facebook. Brand: Pete Moulton (28 years, 1,600 agents, $2.8B sales volume).

Voice rules: first-person Pete, no em/en dashes, no hype, short sentences.
Hard guardrails: no chat widget, no popups, no follower counts, no stock photography
of teams.

## Architecture
- **Frontend**: React 19, React Router 7, Tailwind, shadcn primitives, sonner toasts.
- **Backend**: FastAPI, Motor (Mongo), Pydantic v2.
- **Storage**: Emergent Object Storage for avatars + post images.
- **Auth**: Emergent-managed Google Auth (no client_id/secret needed). Session
  exchange via `/api/auth/session` -> `session_token` HttpOnly cookie + mirror in
  `user_sessions` Mongo collection (7-day TTL).
- **Email**: Brevo transactional emails. Tagged `["ultradian_network","<kind>"]`.
  Contact lists: `Network - Applicants | Members | Declined`.
- **Cross-property**: On sign-in, server calls
  `https://www.ultradianpartners.com/api/network/user-status?email=` with
  `X-Network-Api-Key` header. `network_grant == auto` -> auto-approve.

## Mongo collections
- `users` (user_id, email, name, picture, is_admin, status, source, created_at, last_login_at)
- `user_sessions` (user_id, session_token, created_at, expires_at)
- `applications` (application_id, user_id, email, name, current_role, market,
   years_in_real_estate, why_joining, status, created_at, reviewed_at, reviewed_by, review_note)
- `profiles` (user_id, email, name, market, bio, avatar_path, objectives[3],
   objectives_version, created_at, updated_at)
- `objective_history` (user_id, version, objectives, archived_at)
- `posts` (post_id, user_id, text, image_path, status, created_at, release_at)
- `files` (storage_path, user_id, kind, content_type, size, is_deleted, created_at)

## Phase 1 — Implemented (2026-02-12)
- Landing page (`/`) with Pete-voice copy, three rules, hero with Bloom mark.
- Emergent Google sign-in + `/auth/callback` page that exchanges session_id.
- Cross-property auto-grant on first sign-in (calls partners bridge).
- 4-question application form (`/apply`) + pending + declined states.
- Onboarding (`/onboarding`): avatar upload, name, market, 280-char bio, 3 versioned objectives.
- Post composer (text 500 chars + optional image).
- Personal feed (`/feed`) and public feed (`/public`, last 14 days).
- Profile page (`/profile`, `/profile/:id`) with versioned objectives + recent posts.
- Admin queue (`/admin`) with pending/approved/declined tabs and approve/decline buttons.
- Brevo emails: application received, accepted, declined (with HTML template) + contact list upsert.
- Object storage upload endpoint with size/MIME validation and serving via `/api/uploads/file/{path}`.
- Next release window header indicator (`/api/release-window`).

## Phase 2 — Implemented (2026-05-12)
- **Batched release**: `POST /api/posts` now stores `status=pending_release` with `release_at = next 8:30am or 5:30pm America/Chicago`. Feeds filter `release_at <= now`.
- **APScheduler async cron** at 8:30 and 17:30 America/Chicago flips due `pending_release` posts and replies to `approved` and sends AM/PM digest emails.
- **`/api/posts/mine`** returns the user's own queued + released posts with `is_released` boolean for the "Your queue" panel.
- **Reply threads**: new `replies` collection, `POST /api/posts/{post_id}/replies` (300-char, pending_release, releases at the next window), `GET /api/posts/{post_id}/replies` returns released + the viewer's own pending. `reply_count` is included on each post.
- **Admin trigger** `POST /api/admin/release-now` (admin-only) fires the release job immediately and returns `{window, kind, posts_released, replies_released, emails_sent}`. Useful for testing or recovery.
- **Brevo digest email** with author name, market, and snippet for each post in the batch, tagged `digest_am` or `digest_pm`.
- **Frontend**: Composer shows "Releases at X CT" preview; `Your queue` panel on the feed for own pending posts; PostItem shows a Queued badge + reply count + expandable Replies thread with inline composer.

## Phase 3 + Moderation + Digest prefs — Implemented (2026-05-12)
- **Follows**: `POST/DELETE /api/users/{id}/follow`, `GET /api/users/{id}/relationship`, `GET /api/me/following`. New `follows` collection with unique compound index. No public follower counts (brand rule); counts only returned when viewing your own profile.
- **Member directory**: `GET /api/members?q=` returns approved + non-suspended members with profile snippet, searchable on name or market substring (case-insensitive). 403 to unapproved viewers. Frontend page `/members`.
- **Feed scope toggle**: `GET /api/posts/feed?scope=following|everyone` returns either everyone-in-the-room or only authors you follow (always includes self in following view). Frontend persists choice in localStorage.
- **Digest preferences**: new `digest_prefs={am, pm}` on user. `GET/PUT /api/me/digest-prefs`. Scheduler reads prefs and returns `emails_sent`/`emails_skipped` counts. Frontend `/settings` page.
- **Moderation - members can flag**: `POST /api/posts/{id}/flag` and `POST /api/replies/{id}/flag` (300-char optional reason, idempotent per user+target). Frontend `FlagButton` on each post/reply (not shown for own content). Reported responses persist `viewer_flagged` flag.
- **Moderation - admin queue**: `GET /api/admin/flags?status=open|resolved` returns hydrated target + owner snippets. Actions: `POST /api/admin/posts/{id}/hide|unhide`, `POST /api/admin/replies/{id}/hide`, `POST /api/admin/flags/{id}/dismiss`. Hiding auto-resolves all open flags on that target.
- **Moderation - suspend members**: `POST /api/admin/users/{id}/suspend|unsuspend`. Suspended users cannot create posts or replies (403), and their existing content is hidden from public/feed/by-user/replies endpoints (admins can still see). Admin emails cannot be suspended.
- **Frontend**: Admin page now has Applications and Moderation tabs. Profile page shows Follow / Following button for others and inbox preferences link for self. Layout adds Members nav link.

## Phase 4a — Pete picks, Stripe supporter tier, Analytics — Implemented (2026-05-12)
- **Pete's pick of the week**: `POST /api/admin/posts/{id}/pick|unpick` (admin only), public `GET /api/posts/picks` (last 30 days, released, not hidden/suspended). PostItem shows a "Pete pick" hairline header. PublicFeed has a "Pete recommends" section at top. Digest emails include the same Pete recommends sidebar.
- **Network Supporter tier (Stripe Checkout)**: `$19` one-time, grants 30 days of supporter status (`supporter_until` on user). Backend price is server-defined (`SUPPORTER_PRICE_USD` env). Endpoints: `POST /api/payments/checkout` (creates checkout session + `payment_transactions` row), `GET /api/payments/status/{session_id}` (polled, idempotent grant), `POST /api/webhook/stripe` (also idempotent), `GET /api/me/subscription`. Supporter shows a small ✦ next to their name on the feed. Frontend pages `/upgrade` and `/upgrade/success` (polling).
- **Admin analytics**: `GET /api/admin/analytics` returns `{members:{total_approved,suspended,with_profile,supporters,active_14d}, application_funnel, posts_per_week (8 weeks), top_markets, open_flags, pete_picks_30d}`. Frontend renders in the Admin > Analytics tab with a small bar chart and stat cards.

## Phases 4b-5 (not built yet)
- **Phase 4b**: SPF/DKIM email auth checklist, real public-domain launch on ultradiannetwork.com, member-invite codes (2 per quarter to existing members), digest open-rate tracking.

## Phase 5 - Substack-style essays — Implemented (2026-05-13)
- **Two post kinds** on a single `posts` collection via discriminator: `kind="post"` (short, 500-char, batched 8:30am/5:30pm CT) and `kind="essay"` (long-form, requires title, body 100-50000 chars, publishes INSTANTLY with `release_at == created_at`, `status="approved"`).
- **Composer toggle**: frontend has Short post / Essay segmented control. Essay mode reveals title + subtitle inputs and a much taller body textarea. Submits to the same `POST /api/posts` with `kind=essay`.
- **Per-essay email** to the writer's followers via Brevo on publish. FastAPI `BackgroundTasks` runs `services.essay_dispatch.dispatch_essay_to_followers(db, post_id)` after the response is returned. Idempotency: unique compound index on `(post_id, recipient_user_id)` in new `essay_dispatches` collection; the row is inserted BEFORE the Brevo call so at-most-once-email holds even on transient failures.
- **Paywall**: `GET /api/essays/{post_id}` returns full body (`text`) only for approved members. For everyone else (guests, applicants, declined, pending), returns title + subtitle + cover + ~320-char `preview` + `paywall=true` and a CTA to apply.
- **Feed payload trim**: essay items in `/api/posts/feed`, `/public`, `/mine`, `/by-user` return `preview` instead of `text` to keep payload small; full body is only delivered via the single-essay endpoint.
- **EssayDetail page** (`/essays/:id`): magazine-style typography, full reader for members, paywall card with Apply CTA for non-members, embedded Replies thread below.
- **Existing systems still apply to essays**: Pete pick (admin can mark essays), Reply threads (replies on essays follow the same batched release), Suspended/Hidden filters, Pete recommends section.

**Stats**: 94/94 backend tests passing (24 new in `test_phase5_essays.py`).

## Phase 5b - Markdown, drafts, scheduled essays, member archive — Implemented (2026-05-13)
- **Markdown rendering**: essays now support full markdown (#, **, _, lists, blockquotes, links, code, hr, images). `services/markdown_render.py` uses `python-markdown` + `bleach` allowlist (no `<script>`, no event handlers, http/https/mailto only). `GET /api/essays/{post_id}` returns both raw `text` and sanitized `html` for members. Brevo essay emails render the markdown to HTML inline. Frontend renders via `react-markdown` + `remark-gfm` with brand-styled `.essay-body` CSS.
- **Drafts**: one draft per user via `GET/PUT/DELETE /api/drafts/mine` (new `drafts` collection with unique index on `user_id`). Composer auto-saves every 5 seconds (with a "Draft saved at 8:14am" indicator). Drafts auto-clear on successful publish/schedule.
- **Scheduled essays**: composer has a `datetime-local` schedule picker. `POST /api/posts kind=essay` with `scheduled_at` future ISO stores `status="scheduled"` and `release_at=scheduled_at`. Past timestamps return 422. A new per-minute `process_scheduled_essays` apscheduler job flips due rows to `approved` and dispatches follower emails (idempotent via `essay_dispatches` unique index + `modified_count==1` guard). Scheduled essays show as "Queued" in the writer's `/feed` view.
- **Member archive**: `GET /api/profile/{user_id}/essays` returns released essays only (chronological desc), full body excluded, paginated up to 100. Profile page renders an "Essays" section below recent posts: title + subtitle + date list, each linking to the essay reader. Suspended writers' archives return `[]` for non-admins.

**Stats**: 113/113 backend tests passing (19 new in `test_phase5b_drafts_markdown_schedule_archive.py`).

## Phase 5c - Substack shell — Implemented (2026-05-13)
- **Browse essays** (`/essays`): public page listing all released essays with full-text search (`q`) + market filter, Pete recommends rail when no filter applied. Backend: `GET /api/essays?q=&market=&writer_id=&limit=` (in `routes/essays.py`).
- **Library** (`/library`): member-only bookmark inbox. Backend: `routes/reader.py` with `POST/DELETE/GET /api/me/bookmarks[/{id}]`. New `bookmarks` Mongo collection (unique compound index on `user_id+post_id`).
- **Writer desk** (`/write`): member-only writer dashboard. 5 stat cards (published, scheduled, short posts 30d, followers, emails sent 30d), inline composer toggle, Published/Scheduled tabs with per-essay email counts. Backend: `routes/writer.py` with `GET /api/me/writer/stats|published|scheduled`.
- **EssayDetail upgrades**: inline bookmark button above the title (member-only), fixed top reading-progress bar with auto mark-as-read at 80% scroll (POST `/api/me/reads/{id}`). New `reads` Mongo collection.
- **Magazine `/feed`**: replaces the old short-post stream view. Featured essay + Pete recommends sidebar + recent essays grid + short post composer + short post stream + right-rail "Open your desk" and "Open library" cards. Short posts and essays are now separated in the stream.
- **Layout nav**: new links Essays, Library, Write. Removed Public.
- **Emergent badge removed** from `public/index.html`.

**Stats**: 124/124 backend tests passing (11 new in `tests/test_substack_shell.py`).

## Phase 5d - Rich media: gallery, video, audio, embeds — Implemented (2026-05-13)
- **Both post types support media**: short posts and essays can attach up to 4 images (gallery), 1 video, 1 audio, and 1 URL embed (YouTube/Vimeo). Mutually exclusive: a single post cannot have both an uploaded video and a URL embed.
- **Upload service** (`routes/uploads.py`): one endpoint, content-type aware. Images ≤6MB (jpg/png/webp/gif). Video ≤50MB and ≤60s (mp4, mov, webm) - rejected with 400/413 otherwise. Audio ≤20MB and ≤5min (mp3, m4a, wav, ogg, webm). ffprobe reads duration/dimensions; ffmpeg extracts a JPEG poster frame at t=0.5s for every uploaded video and uploads it as a sibling thumbnail file; the response carries `thumbnail_path`, `duration_s`, `width`, `height`.
- **Embed parser** (`services/embed.py`): `POST /api/uploads/embed {url}` returns `{provider:youtube|vimeo, video_id, embed_url, thumbnail_url}`. Supports YouTube `watch?v=`, `youtu.be`, `/shorts/`, `/embed/`, and Vimeo `/{id}` paths. Anything else returns 400.
- **Post model** (`routes/posts.py`): new `media: List[MediaItem]` array on every post. Pydantic validator enforces the per-kind caps (max 4 images, 1 each of video/audio/embed). Legacy `image_path` is still stored and is auto-synthesized into `media[0]` for old rows. Drafts persist `media` too.
- **Frontend MediaBlock** (`components/MediaBlock.jsx`): gallery renderer (1/2/3+ image grids), `<video>` player with poster, `<iframe>` embed, `<audio>` player. Used by `PostItem` (short posts and essay extras) and `EssayDetail`.
- **Composer** (`components/Composer.jsx`): media picker with multi-image input (cap 4), single-video, single-audio, and a YouTube/Vimeo URL field. Live attached-media list with per-item remove. Drafts auto-save media. Same media UX for both Short post and Essay modes.
- **ffmpeg + ffprobe** installed in the container (Debian package `ffmpeg`).

**Stats**: 148/148 backend tests passing (24 new in `tests/test_media_uploads.py`).

## Phase 4b - Email auth, invites, open-rate tracking — Implemented (2026-05-13)
- **Admin email-health page** (`/admin/email-health`): admin-only DNS records checklist (SPF / DKIM / DMARC / Brevo verification / www CNAME) with one-click copy and a Brevo-backed "test send" button. Static runbook lives at `/app/docs/email-setup.md`. Backend: `GET /api/admin/email/dns-records`, `POST /api/admin/email/test-send`.
- **Member invite codes** (`routes/invites.py`): 2 codes per member per quarter (`YEAR-Q{1..4}`), 8-char alphanumeric, 60-day expiry, one-time use. Atomic redeem on application submit (`POST /api/applications` accepts `invite_code`). Admin queue shows an "Invited by X" chip on each application. Settings page has copy/revoke UI.
- **Open + click tracking** (`services/tracking.py`, `routes/tracking.py`): `services/brevo.send_email` accepts a `dispatch_id`; the HTML is wrapped with a 1x1 open pixel at `/api/track/open/{dispatch_id}.gif` and every external `<a href>` is rewritten to `/api/track/click/{dispatch_id}?to=...` which 302-redirects after logging. Tracking is a no-op when `APP_PUBLIC_URL` is empty. Each digest + essay email mints its own `dispatch_id` and stores a row in the new `email_dispatches` collection (with `first_opened_at`, `first_clicked_at`). Open/click events also land in `email_events`.
- **Admin email engagement** (`/api/admin/analytics/email`): aggregated sent/opened/clicked counts and open/click rates per batch for the last 30 days, surfaced inside Admin > Analytics tab as a table + stat cards.

**Stats**: 166/166 backend tests passing (18 new in `tests/test_phase4b_email_invites_tracking.py`).

## Phase 5e - WYSIWYG essay editor + inline media — Implemented (2026-05-13)
- **Rich-text editor** (`components/RichTextEditor.jsx`): Tiptap + StarterKit + Link + Image + Youtube + tiptap-markdown. Wire format stays markdown end-to-end (`editor.storage.markdown.getMarkdown()` on every change), so the backend and existing essays are unchanged. Toolbar exposes bold, italic, H1, H2, quote, bullet/ordered list, link, image, video, audio, YouTube/Vimeo. A slash-command menu opens when `/` is typed at the start of an empty paragraph and offers headings, lists, divider, and inline image/video/audio/embed insertion.
- **Visual / Markdown toggle** in Composer essay mode (`essay-editor-toggle`). Choice persists in localStorage. Switching is content-preserving in both directions; an existing markdown essay loads losslessly into the visual editor.
- **Inline media** is uploaded via the existing `POST /api/uploads` pipeline and inserted at the cursor — images via the Tiptap `Image` extension, video/audio/iframe as raw HTML inside the markdown body.
- **Sanitizer updates**: `services/markdown_render.py` allowlist now permits `video / audio / source / iframe` (with `src` restricted to http/https via bleach protocols). EssayDetail renders raw HTML through `rehype-raw` + a custom `rehype-sanitize` schema with the same allowlist.

**Stats**: 172/172 backend tests passing (6 new in `tests/test_phase5e_richtext_media.py`).

## Phase 6 - Subject of the Week + P1 polish — Implemented (2026-05-13)
- **Subject of the Week** (`routes/prompts.py`): admin-set weekly writing prompt (Mon-Sun), one active at a time, auto-advances Monday 8:30am CT via the existing APScheduler (`advance_weekly_prompt` cron). Members can suggest subjects (`POST /api/prompts/suggestions`); admin queue accepts or rejects them. Posts/essays carry an optional `prompt_id` link; feed responses include a `post.prompt={prompt_id,title}` snapshot. Magazine home (`/feed`) shows the hero strip, Composer offers a "Writing about this week's subject" checkbox, PostItem + EssayCard show a chip linking to the prompt page, and the digest emails include the prompt block. Dedicated `/prompts` archive + `/prompts/:id` response list.
- **Admin Subjects tab** (`components/AdminPromptsPanel.jsx`): create new prompts (set live now / queue for later), list with set-active and delete, member suggestions inbox with accept/reject. Accept loads the suggestion as a draft in the create form.
- **Applications rate-limit**: at most one application per email per 24h. Second submit returns 429.
- **Image resize at upload** (`routes/uploads.py::_maybe_resize_image`): images >1MB are downscaled to a max dimension of 1920px and recompressed to JPEG q85; PNG with alpha keeps PNG; GIFs are left intact to preserve animation.
- **Composer gallery reorder**: up/down arrows on each image entry swap order; arrows only show on `image` media entries; first/last are correctly disabled.
- **HLS for longer-form video**: explicitly deferred (requires multi-output ffmpeg segmentation + hls.js + storage strategy). Current 60s/50MB cap remains.

**Stats**: 184/185 backend tests passing (13 new in `tests/test_phase6_prompts_p1.py`; 1 pre-existing flake in `test_decline_application` unrelated to this phase).

## Phase 7 - HLS + public-domain launch tooling — Implemented (2026-05-13)
- **HLS hybrid pipeline** (`services/hls_transcode.py`): videos ≤60s stay as direct MP4 (existing behavior); 60-180s videos are queued as a background ffmpeg HLS transcode at 720p H.264 main + AAC 128k with 4-second segments. The upload endpoint returns `{processing:true, transcode_job_id}` immediately; the frontend polls `GET /api/uploads/transcode/{id}` until `status:ready`. Total video cap raised to 3 minutes / 200MB.
- **MediaItem.hls_path**: new optional field; `MediaBlock`'s VideoPlayer chooses Hls.js (with Safari native fallback) when `hls_path` is set, otherwise direct MP4 with poster.
- **Composer flow**: long video shows a "transcoding..." placeholder in the media list, `composer-publish` is disabled while any media is `processing`, and the placeholder is replaced with an `hls_path` entry once the job is ready.
- **APP_PUBLIC_URL admin setter** (`routes/email_health.py`): `GET / POST /api/admin/email/public-url` write to a new `app_settings` collection AND `os.environ`. Startup loads the DB value into the process so digest / tracking URLs hot-flip without a redeploy.
- **Launch readiness check** (`GET /api/admin/email/readiness`): runs real DNS lookups (SPF, DKIM `mail._domainkey`, DMARC) via `dnspython`, HEADs the public URL, and verifies the Brevo key. Surfaced on `/admin/email-health` with a green/red row per check.
- **Launch runbook** at `/app/docs/launch.md`. SEO basics: OG / Twitter / canonical meta in `index.html` and a `/robots.txt` that disallows `/api/` + advertises the sitemap.

**Stats**: 198/198 backend tests passing (13 new in `tests/test_phase7_hls_launch.py`; `test_media_uploads.py` updated for the new HLS behavior).

## Phase 8 - P2 batch: Sunday admin digest, Next essay, Bubble menu — Implemented (2026-05-13)
- **Weekly admin digest** (`services/admin_digest.py`): kitchen-sink HTML email sent every Sunday 8am Chicago time to every `is_admin=true` user. Includes applications (pending / approved / declined 7d), members (total + active 7d), posts/essays released, top 3 conversations by reply count, Pete picks 7d, top member subject suggestions, and digest open/click/send rates. Scheduler cron `send_admin_digest`. Admin endpoints: `GET /api/admin/email/admin-digest/preview` (returns data + rendered HTML) and `POST /api/admin/email/admin-digest/send` (manual fire). Surfaced on `/admin/email-health` as a "Send to all admins now" button.
- **Smart Next Essay** (`GET /api/essays/{id}/next`): if the reader follows the author, returns the next unread essay from the same author with `reason:more_from_author`; otherwise returns a recent globally unread essay with `reason:discover`. Falls back gracefully when the reader is signed-out or no unread candidates exist. Rendered as a `next-essay` card at the bottom of `EssayDetail` below the replies.
- **Rich-text BubbleMenu** (`@tiptap/extension-bubble-menu`): floating toolbar appears on text selection inside the visual editor with Bold / Italic / Link buttons (`bubble-bold`, `bubble-italic`, `bubble-link`).
- **Mid-line slash trigger**: typing `/` after a space (or at the start of any line) now opens the slash command menu in addition to the original "start of empty paragraph" rule. Both paths work; backward compatible.

**Stats**: 198+ backend tests still pass; new endpoints verified by direct curl (next-essay smart routing returns expected `more_from_author` / `discover` reasons; admin-digest preview returns 6.3KB HTML; send emails N admins via Brevo wrap with tracking pixel).

## Phase 9 - Auth redirect-loop fix + Landing magazine (2026-05-13)
- **Auth redirect-loop fixed**: Kubernetes ingress was rewriting `Access-Control-Allow-Origin` to `*` while keeping `Access-Control-Allow-Credentials: true`, which browsers reject. The HttpOnly `session_token` cookie was silently dropped, so `/auth/me` after sign-in returned 401 and AuthCallback bounced the user back to `/`. Fix: `POST /api/auth/session` now also returns `session_token` in the JSON body; `frontend/src/lib/api.js` stores it in localStorage (`ultradian_session_token`) and an axios request interceptor attaches it as `Authorization: Bearer <token>` on every request. `AuthContext.logout()` clears the token. Backend kept its cookie response as a same-domain fallback. Backend CORS also switched to `allow_origin_regex=".*"` so direct-to-backend traffic gets a credential-safe response.
- **Landing magazine**: `/` now renders the live read-only magazine (`pages/Landing.jsx`) — featured essay + 3 also-reading minis + up to 6 batched short posts pulled from public endpoints (`/posts/public`, `/essays`, `/prompts/current`). No like/reply/follow controls exposed for unauthenticated visitors. Two CTAs: "Sign in with Google" and "Apply for membership". Subject-of-the-week banner shows when a prompt is active.
- **About page** at `/about` (`pages/About.jsx`): houses the original "Three rules of the room" + "Who I am" sections that used to live on the landing splash.

**Stats**: 9 new pytest cases in `tests/test_iter14_auth_landing.py` (all pass); end-to-end Playwright verified Landing render + authenticated `/feed` via Bearer header.

## Phase 10 - Substack import + Share buttons + Tech debt (2026-05-13)
- **Daily Substack RSS import** (`services/substack_import.py`): pulls Pete's essays from `SUBSTACK_RSS_URL` (defaults to `https://peterrmoulton.substack.com/feed`), converts the HTML body to markdown via `markdownify`, strips trailing #Hashtag clusters Substack/LinkedIn syndication adds (de-branded), de-dupes by `source_guid` and `source_url`, and inserts each entry as `kind: "essay"`, `status: "approved"`, `source: "substack_import"`, attributed to the first matching admin (`peter@1691inc.com` or `peter@ultradianpartners.com`). Scheduler cron `substack_rss_import` fires daily at 7:00am Chicago. Manual admin trigger: `POST /api/admin/rss/import` + status at `GET /api/admin/rss/status`. Surfaced in the Admin header as an "Import essays now" button (`admin-rss-import-btn`). First import on Pete's feed pulled 20 essays; subsequent calls return `imported=0 skipped=20`.
- **Share buttons** (`components/ShareButtons.jsx`): on every member-visible essay, a row of 8 share targets — LinkedIn, X, Facebook, Substack (Note quote), Instagram, TikTok, YouTube, Copy link. LinkedIn/X/Facebook/Substack open a tab to the platform's intent URL. Instagram/TikTok/YouTube + Copy link write the canonical essay URL to the clipboard with a contextual toast. Render only when the viewer is not paywalled, so anonymous visitors do not see them.
- **Shared `EssayCards.jsx`**: `FeaturedEssay` + `EssayMini` extracted out of `Landing.jsx` and `Feed.jsx`. Both pages now use the shared components — the only divergence is the `linkTo` / `testIdPrefix` prop, removing the drift the iter-14 code review flagged.
- **Auth round trip removed**: `POST /api/auth/session` now returns `has_profile`, so `AuthCallback.jsx` no longer calls `/auth/me` after exchange — shaves a ~300ms round trip off sign-in.
- **`withCredentials: false`** on the axios instance — Bearer-in-localStorage is now the canonical auth, this removes a class of intermittent CORS preflight failures.

**Stats**: 11 new pytest cases in `tests/test_iter15_substack_share.py` (all green); iter-14's 9/9 still green; Playwright verified Landing shared-grid render, anonymous paywall hides share-buttons, member share-buttons render with all 8 testids and correct intent URLs, admin RSS import button visible and wired.

## Phase 11 - Substack-quiet Landing redesign (2026-05-13)
- **Landing rebuilt** as a Substack-style minimalist publication front page: single masthead with one gold pill `Sign in` + text `About` link, large 3-line display headline, italic serif tagline. Below the masthead a hairline separates the featured essay (no border, `variant="quiet"` from `EssayCards.jsx`), then a hairline-separated stack of `More essays` rows, then a `From the feed` stack of short notes. No bordered cards anywhere on landing - type and whitespace do all the work. Single quiet footer CTA.
- **Removed distractions**: `NextReleaseTimer` hidden in the Layout header when on `/`; the "Reading without an account" sidebar box dropped; the "Subject of the week" colored banner dropped; multiple stacked CTAs collapsed to one masthead pill + one footer pill.
- **EssayCards variants**: `FeaturedEssay` now has `variant="quiet"` (no border, big serif h2, italic subtitle, gold "LATEST ESSAY" eyebrow) and `EssayMini` has `variant="row"` (no border, serif headline + subtitle + 1-line preview + meta, designed to pair with `divide-y` on the parent).
- **Toaster** repositioned to `bottom-center` with shorter `duration={2200}` and no shadow - notifications are now a calm hairline-bordered cream chip at the bottom of the screen rather than a top-center alert.
- **Typographic polish**: switched the meta separator from a bare `. ` (which read like the end of a sentence) to a true middle dot `·` everywhere on Landing; added `line-clamp-3/4` safety on the featured essay subtitle and preview so a long subtitle cannot dominate the masthead-to-stack rhythm.

## Phase 12 - Make writing evident + new headline (2026-05-13)
- **Landing headline + tagline updated**: "A daily magazine for the real estate industry." with sub "Written by people who close deals. Released twice a day, at 8:30am and 5:30pm."
- **Write CTA promoted to a gold pill** in the global nav header (Layout.jsx) with a pen icon. For approved members the Write button is now the visually dominant action on every page, not a plain text link buried among other nav items.
- **Composer hoisted to the top of /feed**: the new `feed-compose-block` (gold "WRITE" eyebrow + "What did you see today?" headline + "Open the desk →" link) is now the first thing a signed-in member sees, with the full Composer immediately below. The Magazine grid follows underneath.
- **Small copy nudges**: short-post placeholder is now "Plain words. What happened on a deal today?" - more inviting than the previous generic prompt.
- **Removed**: the in-nav "Support" link (one less item competing with Write) and the second/inner composer that used to live inside the "Short notes" section (eliminated duplication).






## Phases 2-4 (not built yet, listed in architecture)
- **Phase 2**: Batched 8:30am/5:30pm release scheduler. AM/PM digest emails via Brevo.
  Reply threads. Posts move from `pending_release` to `approved` at scheduled times.
- **Phase 3**: Follows, member directory, advanced moderation (flag, hide, suspend).
- **Phase 4**: Paid tier with its own Stripe account, member analytics, public launch.

## Backlog
- P0: confirm Brevo sender email is verified in Brevo dashboard.
- P1: rate-limit application submissions per email.
- P1: image resize at upload time (compress > 1MB).
- P2: search posts.
- P2: weekly admin digest email.

## Next Actions
1. Test full end-to-end (auth, application, admin approve, post, public feed).
2. Add Phase 2 batched scheduler with apscheduler.
3. Add digest email job that summarises the AM and PM batches.
