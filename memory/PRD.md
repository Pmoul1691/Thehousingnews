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

## Phase 14 - Facebook + Substack intuitive Feed (2026-05-13)
- **New `/feed` layout**: single-column main + sticky right rail. Drops the previous magazine grid clutter (featured + Pete picks block + recent essays grid) entirely. Top-to-bottom: greeting ("Good day, {firstName}."), Substack-style collapsed compose row, Subject of the week hairline link (if active), pending-queue tiny stack, Everyone/Following scope tabs, mixed essay+short-post stream sorted by `release_at` desc.
- **`FeedCompose.jsx` (new)**: Facebook-style collapsed compose card. Shows avatar + italic "Write something, {firstName}..." pseudo-input + Photo/Video/Essay quick-action chips. Click anywhere on the row OR a chip to expand the full Composer in place. Expanded view has a small X-icon `Close` button (testid `feed-compose-collapse`) to collapse back. `scrollIntoView` uses `block: 'nearest'` so the close button does not jitter mid-animation.
- **Right rail**: NEXT RELEASE timer, Pete picks (3 most recent, hairline-stacked), Shortcuts (Browse all essays, See members, Your library, Past subjects). No bordered cards. Picks now fall back to `text.slice(0,90)` when a Pete pick is a short post without a title.
- **`NextReleaseTimer` dedup**: hidden in the Layout header on `/feed` as well as `/` so the timer only appears once (in the right rail).
- **Following empty state fixed**: dropped the now-redundant `/api/essays?limit=8` call and feed the stream from the scope-aware `/api/posts/feed` endpoint (which already returns mixed essays + shorts).

## Phase 15 - Profile-recovery on sign-in (2026-05-14)
- **Bug**: members reported being routed back to `/onboarding` every sign-in. Root cause was orphaned `profiles` rows: a previous dev/test cleanup deleted some `users` rows but left their `profiles` behind. On next sign-in `/auth/session` did `db.users.find_one({email})`, found nothing, generated a new `user_id`, and ignored the existing profile - so `has_profile` stayed false forever and the SPA kept routing the member to onboarding.
- **Fix (`routes/auth.py` POST `/auth/session`)**: when no user row matches the email, fall back to `db.profiles.find_one({email})`. If a profile exists, reuse its `user_id` when minting the new user row and force `status=approved` (profile rows only exist for approved members). Stamp `source="profile_recovery"` so the recovery path is auditable in the user collection.
- **Defensive index**: added a sparse non-unique index on `profiles.email` to keep the recovery lookup fast. The unique index on `users.email` was already in place; no new dup risk.
- **One-time data sweep**: deleted 6 legacy orphan profiles + 20 orphan sessions left from earlier dev runs so Pete's identity is unambiguous (`user_pete_demo` is now the single canonical record for `peter@1691inc.com`).

**Stats**: 1 new pytest case in `tests/test_iter18_profile_recovery.py` asserts the orphan-profile-by-email path: a legacy profile is reattached to its original `user_id`, `has_profile` returns true, status is `approved`, and a `profile_recovery` user row is created. Two related regression paths (fresh user + existing user) were verified via live `curl` against the running backend instead of additional TestClient instances because spinning multiple TestClients per pytest session triggers an "Event loop is closed" error from the module-level Motor client in `server.py`.

## Phase 16 - Tech debt sweep + audio waveform previews (2026-05-14)
- **Partial unique index on `posts.source_guid`** scoped to `source: "substack_import"` (server.py). Prevents the daily RSS cron from inserting a duplicate essay even under concurrent races. Other post kinds are excluded by the `partialFilterExpression` so manual essays and short posts still don't need a `source_guid`.
- **Substack imports gated to the next batched release window** (`services/substack_import.py`): newly imported essays get `release_at` set to `services.release_window.next_window()` so they join the 8:30am/5:30pm CT batched rhythm instead of going live immediately at the Substack publish time. The original publish date is preserved separately as `source_published_at` and powers the "Originally published on Substack, {date}" footnote. One-time backfill applied to the existing 20 imports so their footnotes still show the original Substack dates.
- **TestClient + Motor "Event loop is closed" resolved** in `tests/test_iter18_profile_recovery.py` by switching to `httpx.AsyncClient` + `asgi_lifespan.LifespanManager` and consolidating the three auth scenarios + the Substack release-window scenario into a single async test so the Motor client lives in one event loop for the whole run. All 4 scenarios now run inline in pytest with no curl side-channel needed (4 asserts in 1 test, 100% green). Added `asgi-lifespan` and `pytest-asyncio` to `requirements.txt`.
- **Audio waveform previews** (P2):
  - Backend `services/media.py` adds `extract_audio_peaks(data, buckets=200)` that pipes the upload through ffmpeg (`-ac 1 -filter:a aresample=8000 -c:a pcm_s16le -f s16le`), reads the raw int16 PCM, buckets it, takes peak abs per bucket, normalizes to 0..1 and rounds to 3 decimals. Returns `[]` on failure.
  - `routes/uploads.py` runs `extract_audio_peaks` on audio uploads and stores the 200-bucket array as `peaks` on the media record.
  - Frontend `components/MediaBlock.jsx` renders the peaks as a clickable bar-chart waveform with a gold play/pause pill on the left and the duration on the right. The portion already played fills gold; the remainder is the lighter `#E8D4A0`. Clicking the waveform seeks to that position. Empty `peaks` array falls back to the previous "Audio" eyebrow.
- **OS dep**: installed `ffmpeg` (was missing from this fork environment despite the handoff note - peaks extraction would have silently failed without it). Verified ramping amplitude renders correctly across 200 buckets (linear 0.1 -> 1.0).



- **New `/feed` layout**: single-column main + sticky right rail. Drops the previous magazine grid clutter (featured + Pete picks block + recent essays grid) entirely. Top-to-bottom: greeting ("Good day, {firstName}."), Substack-style collapsed compose row, Subject of the week hairline link (if active), pending-queue tiny stack, Everyone/Following scope tabs, mixed essay+short-post stream sorted by `release_at` desc.
- **`FeedCompose.jsx` (new)**: Facebook-style collapsed compose card. Shows avatar + italic "Write something, {firstName}..." pseudo-input + Photo/Video/Essay quick-action chips. Click anywhere on the row OR a chip to expand the full Composer in place. Expanded view has a small X-icon `Close` button (testid `feed-compose-collapse`) to collapse back. `scrollIntoView` uses `block: 'nearest'` so the close button does not jitter mid-animation.
- **Right rail**: NEXT RELEASE timer, Pete picks (3 most recent, hairline-stacked), Shortcuts (Browse all essays, See members, Your library, Past subjects). No bordered cards. Picks now fall back to `text.slice(0,90)` when a Pete pick is a short post without a title.
- **`NextReleaseTimer` dedup**: hidden in the Layout header on `/feed` as well as `/` so the timer only appears once (in the right rail).
- **Following empty state fixed**: dropped the now-redundant `/api/essays?limit=8` call and feed the stream from the scope-aware `/api/posts/feed` endpoint (which already returns mixed essays + shorts). Previously essays were unconditionally merged into the stream regardless of scope, which made `feed-empty` unreachable on the Following tab. Now empty state shows: "No released posts from people you follow yet. Switch to Everyone to see the full room."

**Stats**: iter-17 ran on the previous version and reported 95% green with one real product bug (empty state); the bug is now fixed and self-verified via Playwright (`feed-empty` resolves on a fresh non-admin account with `scope=following`).

## Phase 13 - "Originally published on Substack" footnote (2026-05-13)
- **Backend** (`routes/essays.py` GET `/api/essays/{id}`): for members only (post-paywall), the response now includes `source` and `source_published_at` when the essay was pulled from a Substack import. Anonymous viewers still see the preview + paywall and do not get these fields.
- **Frontend** (`pages/EssayDetail.jsx`): when `essay.source === "substack_import"`, the reader page renders a quiet italic serif footnote at the bottom of the body: *"Originally published on Substack, {Month D, YYYY}."* with a hairline separator above. No logo, no link - text-only trust signal that does not break the de-brand rule.
- New testid `essay-source-note` for testability.
- **Data cleanup**: re-attributed the 20 orphaned Substack imports (from a mid-session admin user delete) back to Peter Moulton's user_id, and swept 122 pytest fixture posts that had been sorting above his real content on the public Landing.







## Phase 25 — P2 sweep: trending strip, members filter, preview-DB reset, ToS stamping (2026-02-15)
- **Trending topics strip** (`services/trending.py`, `GET /api/agg/trending`): n-gram extraction from aggregator headline titles, returns bigrams and trigrams with count >= 2 in the last `hours` window (default 24h, max 168h). Trigrams ranked first, then bigrams that aren't already contained in a chosen trigram. Stopword + generic real-estate filler list applied. Frontend `AggTrendingStrip.jsx` renders the chips above the river on `/`; clicking a chip drops the `?topic=` URL param which widens the river fetch to a 168-hour / 100-item window so the chip count and the in-memory filter agree. Active filter shows a clear "Filtering · {topic} ✕ · N of M items" banner.
- **Admin members directory filter** (`routes/users.py::list_members`): new optional `?filter=comped|supporter|free` query param (admin-only, returns 403 otherwise). Each row now carries an `entitlement` object for admin viewers (`{tier, partner_tier, is_supporter, supporter_until, source, email}`). Filter logic: comped → `partner_tier` truthy or `source=partners_auto_grant`; supporter → `supporter_until > now` and not comped; free → neither. Frontend `/members` page shows the 4-chip filter strip only when `user.is_admin`, and renders an `EntitlementChip` next to each member's name.
- **Reset preview DB** (`routes/admin_reset.py`): admin-only `GET /api/admin/preview-db/preview` (dry-run, returns will-delete / will-preserve counts) and `POST /api/admin/preview-db/reset` (destructive, requires `confirm:"RESET"` body token AND `AGG_ALLOW_DB_RESET=true` env flag). Preserves admin users, admin-authored posts, Substack imports (`source=substack_import`), aggregator publishers + articles. Wipes member-generated content (applications, profiles, posts, replies, follows, flags, drafts, bookmarks, reads, payment_transactions, essay_dispatches, invite_codes, prompt_suggestions, email events, agg_newsletter_signups, agg_suggestions) and all non-admin sessions/users. Frontend `AdminResetDbPanel.jsx` is rendered at the bottom of the Admin > Orphans tab as a clearly-marked "Danger zone" with a typed-confirmation modal.
- **ToS acceptance stamping** (`services/tos.py`, `routes/applications.py`): the Terms of Service PDF at `/legal/terms-of-service.pdf` is hashed (SHA-256, mtime-cached) at request time and the hash is stamped on every application submission alongside an ISO timestamp. `ApplicationCreate` now requires `tos_accepted: true` or returns 400. Application docs persist `{tos_accepted, tos_accepted_at, tos_version_hash, tos_document_url}`; the same hash + timestamp is also mirrored onto the user document. New public `GET /api/applications/tos-version` returns the live hash + document URL so the apply form can display the version the user is consenting to.

**Hashtag regression** (Phase 24 feature): re-verified by curl + Playwright through the iter-20 test pass. `/api/posts/by-tag/{tag}` and `/api/posts/tags/popular` continue to behave as expected. Composer hint + Tag page popular strip render correctly.

**Stats**: iter-20 testing — 21/21 backend pytest cases pass; all targeted frontend selectors render correctly. Code-review feedback addressed: `AGG_ALLOW_DB_RESET` now defaults to `false` (must be explicitly opted in via env); trending chip + river filter window are reconciled so the chip count matches the visible filtered list.


- **Phase 2**: Batched 8:30am/5:30pm release scheduler. AM/PM digest emails via Brevo.
  Reply threads. Posts move from `pending_release` to `approved` at scheduled times.
- **Phase 3**: Follows, member directory, advanced moderation (flag, hide, suspend).
- **Phase 4**: Paid tier with its own Stripe account, member analytics, public launch.

## Phase 21 — Hamburger nav + "We"/Staff picks voice (2026-02-14)
- **Header collapsed**: Authenticated nav now shows only Logo, Feed link, gold Write pill,
  and a hamburger trigger (`data-testid="nav-menu-trigger"`) that opens a right-side Sheet.
  Sheet contains: Essays, Subjects, Library, Members, Profile, Settings, Admin (if admin),
  About, Sign out. Mobile-friendly.
- **Voice swap**: replaced all user-facing first-person/single-person "Pete" framing with
  plural "We" / "The Editors" / "the editors" across UI and transactional emails.
  - `About.jsx` masthead rewritten in "we" voice (no more "Pete Moulton" single founder framing).
  - `PendingReview.jsx`: "We will read it shortly." / sign-off "The Editors".
  - `FlagButton.jsx`: "Tell us what is off" / "The editors will take a look".
  - `Prompts.jsx`: "Suggestion sent to the editors".
  - `Settings.jsx` invites: "We still review every application..."
  - Brevo email templates (`services/brevo.py`, `services/admin_digest.py`,
    `routes/email_health.py`): every "Pete" sign-off swapped to "The Editors".
- **"Staff picks"** replaces "Editor picks" / "Pete recommends" across:
  - Feed sidebar, Essays page, PetePicksSection component, AdminAnalyticsPanel,
    Brevo digest emails, Sunday admin brief.
- Component file `PetePicksSection.jsx` kept (internal name only); user-facing label
  is now "Staff picks".

## Phase 22 — Floating Write pill + admin orphan reconnect + "producers" voice (2026-02-14)
- **Floating Write pill** (`components/FloatingWriteButton.jsx`): persistent
  bottom-right gold pill rendered by `Layout` for every approved member on every
  page except `/write` itself. Polls `GET /api/drafts/mine` on mount/route change.
  When the response contains text/title/subtitle/media content, a small deep-red
  dot (`data-testid="floating-write-draft-dot"`) appears on the icon as a quiet
  unfinished-draft indicator.
- **Admin "Orphans" tab** in `/admin`: new section that lists every profile whose
  `user_id` no longer maps to a live user. For each orphan, the candidate live
  user (matched by email) is shown alongside post-count attached to the orphan
  user_id. A gold "Reconnect to live user" button re-stitches the profile and
  reassigns all posts + replies to the live user_id in a single request.
  Disabled with a hint ("Waiting for the member to sign in again.") when no
  candidate user exists.
  - Backend: new `routes/admin_orphans.py` mounted at `/api/admin/orphan-profiles`
    with `GET ""` and `POST /reconnect` (admin-only).
- **"Operators" -> "producers" / "the real estate industry"** across all
  user-facing copy: `About.jsx`, `EssayDetail.jsx`, `Essays.jsx`, `Upgrade.jsx`.

## Phase 23 — Search posts + digest polish + tighter image compression (2026-02-14)
- **Posts search** (`GET /api/posts/search?q=...&kind=...&market=...`): full-text
  search across released posts using a new Mongo text index on
  `(text, title, subtitle)` with weights `title:10, subtitle:4, text:1`. Members
  only; suspended authors excluded. Sort: text score, then release_at desc.
- **New `/search` page** (`pages/Search.jsx`) with URL-synced query params, kind
  tabs (Everything / Essays / Short posts), and an optional market filter.
  Linked from the hamburger menu and from the Feed right-rail Shortcuts.
- **Image compression**: bumped longest-edge from 1920 -> 2000px,
  `RESIZE_JPEG_QUALITY` 85 -> 82, EXIF strip already in place. Trigger threshold
  unchanged at 1MB.
- **Application rate-limit**: pre-existing `applications.py` check (one
  submission per email per 24h) was confirmed and tested at 429.
- **Weekly admin digest polish** (`services/admin_digest.py`):
  - Date-stamped subject line, e.g. `Sunday brief - Feb 14 - 3 applications pending`.
  - New "Top essays this week" section (sorted by reply count, then recency, top 3).
  - New "Biggest mover" callout: member whose released-post count grew most vs
    the prior 7-day window. Quiet pull-quote style block.
- **"Staff picks"** label propagated to every previously-missed surface
  (`PostItem`, `EssayCards`, `EssayDetail`, `Essays`, `Write` page).

## Phase 24 — Public RSS aggregator backend (Phase 1 of 3) (2026-02-14)

Major product pivot: in addition to the members-only batched social network,
`thehousingnews.com` now hosts a public RSS aggregator modeled on Techmeme /
Memeorandum. Members product stays in the codebase (will move under `/members`
in Phase 2 frontend work).

- **Collections** (Mongo, prefixed `agg_*`): `agg_publishers`, `agg_articles`,
  `agg_newsletter_signups`. Compound unique index `(publisher_id, guid)`
  guarantees dedupe.
- **Seed**: 28 residential real estate publishers (Inman, The Real Deal,
  HousingWire, RISMedia, Realtor.com, 6 TRD regional editions, Brownstoner,
  Curbed, 8 industry blogs, 5 data/research, 2 mortgage). Idempotent at boot.
- **Ingest service** (`services/rss_ingest.py`): pulls feeds with the
  declared User-Agent `thehousingnews-aggregator/1.0 (+...)`, honors
  robots.txt, strips HTML server-side, caps snippet at 280 chars OR 2 sentences,
  extracts thumbnails only as publisher-hosted URLs (never rehosts).
- **Cron** (APScheduler): every **15 minutes** ingest all active publishers
  whose `refresh_minutes` window has elapsed. Daily `03:15 UTC` prune: hide
  items >90d, hard-delete >120d.
- **Public read endpoints** (`/api/agg/*`):
  - `GET /articles?category=&publisher_slug=&hours=&offset=&limit=` (river)
  - `GET /publishers`, `GET /publishers/{slug}`, `GET /categories`
  - `POST /newsletter/signup` (local capture; Beehiiv/ConvertKit push deferred to follow-up)
- **Admin endpoints** (`/api/agg/admin/*`, admin-only via existing allowlist):
  - List / create / update / soft-delete publishers
  - `POST /test-feed` returns first 3 parsed items (preview before activation)
  - `POST /publishers/{id}/refresh` for manual one-off pull
  - Search / hide / hard-delete articles
- **Tests**: 9 unit tests covering snippet cap, dedupe behaviour, headline-only
  mode, thumbnail extraction, malformed RSS handling. All passing.
- **Smoke test**: ran manual ingest — **27/28 feeds OK, 533 articles inserted**.
  Only Inman returned HTTP 403 (Cloudflare-style bot block); admin can disable
  or fall back to an alternate URL through the admin UI.
- **Compliance rules baked in**:
  - Snippet truncation is server-side (not CSS).
  - `original_url` on every article points to the publisher's domain.
  - No `read more` internal route. No full-article view. No paywall on aggregator.
  - 90/120-day expiry enforced by `prune_expired` cron.

## Phase 7 — Editorial copy cleanup + new hero (2026-02-16)
- **Landing hero**: replaced "Morning/Evening Brief" mockups with two product
  previews styled as actual screenshots of `/news` (The Daily) and `/feed` (the
  member Composer). New `BrowserChrome`, `TheDailyPreview`, `ComposerPreview`
  components in `Landing.jsx`.
- **45-day free trial for invitees**: hero CTA, pricing note, and final CTA
  reflect $12.50/mo or $100/yr after the 45-day Brevo-invite trial. Claim page
  also greets invitees with "45 days, free".
- **Corporate-speak removed across the site** (Landing + AggHome):
  - "Signal over noise" → "A magazine, not a feed."
  - "Housing Intelligence Network" → "The Network" / "Housing News Network"
  - "intelligence layer" → "What the housing industry is reading today."
  - "The value is not more information…" → "Read once in the morning. Read once
    at night. The rest of the day belongs to your clients."
  - "Built for substance" / "elevate the industry" → "Members write. Members
    read."
  - "Stop searching. Start understanding." → "One place. Twice a day. Done."
  - "Local Signal" badge → "Local"
  - Removed: "performative theater", "vanity metrics", "fragmented information",
    "signals that matter", "spend less time searching".

## Phase 8 — Morning + Evening Daily Briefs (2026-02-16)
- **New service** `services/briefings.py`:
  - `build_brief_payload(db, kind)` — pulls top 8 articles (deduped by
    publisher) from last 14h (morning) or 8h (evening, widens to 14h if thin),
    plus one podcast pick (morning), trending topics (evening), and the most
    recent approved member essay.
  - `send_brief(db, kind)` / `send_morning_brief` / `send_evening_brief` —
    iterates `status in [approved, invited]` users with `brief_optout != true`,
    inserts a `brief_dispatches` tracking row per recipient, sends via Brevo.
- **New Brevo template** `send_brief_email` in `services/brevo.py` — premium
  cream/gold/ink HTML shell with article rows, podcast pick, trending list,
  member essay block, "Open The Daily" CTA, and a manage-prefs footer.
  Sender override: `briefs@thehousingnews.com` / "The Housing News".
- **APScheduler cron jobs** added in `services/scheduler.py`:
  - `brief_morning` — daily 7:30 AM America/Chicago
  - `brief_evening` — daily 5:30 PM America/Chicago
- **Admin endpoints** in `routes/admin_briefings.py`:
  - `GET  /api/admin/briefings/preview?kind=morning|evening` — dry-run dump
  - `POST /api/admin/briefings/send?kind=morning|evening` — fire immediately
  - `POST /api/admin/briefings/send-test?kind=...&email=...` — send a single
    `[TEST]`-prefixed brief to one inbox, no tracking row recorded.
- **Verified**: end-to-end test against the live Brevo API returned a real
  `messageId` for a Morning Brief test send. Both previews return 8 deduped
  articles with publisher attribution + a member essay; evening preview also
  surfaces 24h trending topics.
- **Mongo collection added**: `brief_dispatches` (dispatch_id, kind,
  recipient_user_id, recipient_email, articles_count, first_opened_at,
  first_clicked_at, created_at).
- **Env**: `BRIEF_SENDER_EMAIL` (default `briefs@thehousingnews.com`),
  `BRIEF_SENDER_NAME` (default `The Housing News`).

## Phase 9 — "The Feed" syndicated-sources strip on Landing (2026-02-16)
- New `TheFeedSection` on `/`: 3 rows of 38 source logos — 28 publisher
  favicons (via Google's favicon service when `logo_url` is null) + 10 podcast
  cover arts. Each logo links to its archive (`/news/source/:slug`) or to
  `/news/podcasts`. Replaces the older text-only `TrustSection`.
- Title: "The Feed" / "What gets syndicated, every day." with a dynamic count
  ("28 publishers and 10 podcasts feed into The Daily.") and an "Open The
  Daily →" CTA.

## Phase 10 — "The Feed" categorized layout (2026-02-16)
- Replaced the round-robin 3-row layout with **6 category-labeled rows**:
  National News, Regional, Mortgage, Data & Research, Blogs, Podcasts. Each
  row shows the category label + count, followed by the favicons/cover art.
- Smarter dedupe: when two publishers share a hostname, the entry with the
  higher-priority category wins (national_trade > mortgage > data > regional
  > blog), so "The Real Deal" properly anchors National News instead of being
  collapsed into a regional TRD desk.
- Confirmed: 32 distinct sources rendered across 6 categories. Keeping
  Current Matters appears in **Blogs** (already ingesting at
  `www.keepingcurrentmatters.com/feed`, 8 articles in DB).

## Phase 11 — Real member photos on Landing (2026-02-16)
- **New public endpoint** `GET /api/agg/recent-members?limit=8` — returns
  approved (non-stub, non-suspended) members who have published an approved
  post in the last 30 days. Returns: `user_id`, `name`, `market`,
  `avatar_path`, `last_post_at`, `last_kind`, `last_post_id`, `snippet`.
  No emails. Sorted by most-recent activity.
- **New `MemberAvatar` atom** in `Landing.jsx` — `<img>` loaded from
  `${API}/uploads/file/<avatar_path>` with graceful `onError` fallback to a
  cream-soft initial circle. Reused across all new landing avatar surfaces.
- **New `MembersOnTheFeedSection`** — six member cards (avatar + name +
  market + relative time + 3-line post snippet) right before the essay grid.
  Hidden gracefully when fewer than 3 active members exist.
- **`MemberArticlePreviews`** essay cards now include an avatar + name +
  market footer band instead of the old "By Name · Market" italic line.

## Phase 12 — RSS aggregator upgrade per spec (2026-02-16)
- **5 new news + 1 newsletter publishers seeded**: CNBC Real Estate,
  MarketWatch Real Estate, Commercial Observer, Multi-Housing News, Eye on
  Housing, and ResiClub (Lance Lambert) under the new `newsletter` category.
  Total active publishers: **34**.
- **URL normalization for dedup** (`services/rss_ingest.py::normalize_url`):
  strips `utm_*`, `mc_*`, `_hs*`, `hsa_*`, `ref_*`, `vero_*`, `pk_*`,
  `fbclid`, `gclid`, `dclid`, `msclkid`, `yclid`, `wbraid`, `gbraid`, and
  several other tracking params, lowercases host, drops `www.`, drops
  trailing slash + fragment, sorts remaining query params. The result is
  stored as `agg_articles.normalized_url` with a unique sparse Mongo index,
  so the same story re-shared with different tracking params won't
  double-store.
- **Per-spec error tracking**: each failed fetch now increments
  `agg_publishers.error_count` and writes the cause to
  `last_fetch_status`; successes reset the count to 0. One bad feed never
  blocks the others.
- **`POST /api/refresh-feeds`** — token-protected external-cron trigger.
  Token comes from `RSS_REFRESH_TOKEN` in `backend/.env`; caller passes it
  via `?token=` or `X-Refresh-Token` header. Returns the same per-publisher
  summary the in-process scheduler produces. The existing APScheduler job
  every 15 minutes still runs in addition.
- **Keyword search** on `GET /api/agg/articles?search=...` — case-insensitive
  substring across `title` + `snippet`. Regex-escaped at the boundary.
- **New `/news/latest` page** (`AggLatest.jsx`): per-article river of every
  story across all sources, with thumbnail / source attribution / time /
  excerpt. All cards open publisher URLs in new tabs (`target="_blank"
  rel="noopener noreferrer"`). Filters: category dropdown, source dropdown
  (grouped by category), free-text search, clear-filters button.
  Pagination via offset/limit (20 per page, 7-day rolling window). Filter
  state is mirrored to the URL so back/forward works. Existing per-publisher
  `/news` grid is preserved untouched.
- **`AggLayout`** gained a "Latest" link in the header desktop nav + mobile
  sheet, and the `Newsletters` chip in the category filter bar.

**Operator note**: `RSS_REFRESH_TOKEN` is provisioned in `backend/.env`.
Value: `agVvGK5zSxMwxxv-Y2sI4NOeNbM3s--tq7up0UzX-_hpBeCPlqEgjw`. External
cron can hit `POST /api/refresh-feeds` with header
`X-Refresh-Token: <token>` (recommended hourly) or rely on the existing
in-process APScheduler job that fires every 15 minutes.

## Phase 13 — Rebalance: publishing network as co-equal pillar (2026-02-16)
The user asked to make the Substack-style publishing network "as obvious as
the newsfeed". Three changes:

- **Hero rewrite**:
  - Headline now reads **"Where housing reads. And writes."** with "And
    writes." in gold to underline the duality.
  - Subhead: "A publishing network for real estate professionals. Read what
    the industry is publishing and publish what you're seeing — alongside
    twice-daily briefings pulled from 34 housing sources."
  - New WRITE / READ two-pillar eyebrow strip beneath the subhead.
  - Primary CTA changed from "Start 45-day free trial" → **"Join the
    network"**. Secondary CTAs: "Read member essays →" and "Today's
    headlines →". 45-day trial note kept beneath.
  - Preview cards reordered so the **Composer preview is now on top**
    (write) and **The Daily is below** (read). Equal visual weight.
- **New `TheNetworkSection`** mirrors `TheFeedSection` structure: same
  category-row layout, same Open-The-X CTA, but for member writers instead
  of news publishers. Members are best-effort bucketed into Agents &
  Brokers / Investors / Lenders & Mortgage / Builders & Devs / Vendors &
  Tech / Members based on their market + most-recent post text. Empty rows
  hide. Section gracefully omits when fewer than 3 active members exist.
- **Section order** now: Hero → TheFeed → **TheNetwork** → Intelligence →
  WhatYouGet → MemberCommunity → ... The two pillars read as equals.
- **`/api/agg/recent-members?limit`** cap raised from 20 → 30.

## Phase 14 — Personal Access Tokens + Trending tags strip (2026-02-16)

**Personal Access Tokens (PATs)** — programmatic posting for LLM agents
- **`services/pat_service.py`**: token format `thn_pat_<32 url-safe chars>`,
  stored as SHA-256 hash + 12-char display prefix. Raw value is shown to the
  user exactly once at creation. `resolve_pat(db, raw)` verifies + stamps
  `last_used_at`; never raises (callers fall back to session-token path).
- **`services/auth_helpers.get_current_user`** now recognizes any Bearer
  token starting with `thn_pat_` and resolves it through the PAT path. All
  existing protected endpoints (`/api/posts`, `/api/essays`, `/api/auth/me`,
  etc.) automatically work with PATs — no per-route changes needed.
- **`routes/pats.py`** (`/api/pats`):
  - `POST /api/pats` — create (returns raw token ONCE)
  - `GET /api/pats` — list user's PATs (sanitized: prefix + last_used_at)
  - `DELETE /api/pats/{id}` — soft revoke (sets `revoked_at`; row kept for audit)
  - 10-token live cap per user; only `status=approved` members can create.
- **Settings UI** (`/settings`): new "Access Tokens · Programmatic posting"
  section with create-form, one-time reveal panel with copy button, list
  view (prefix · created date · last used · Revoke), and an expandable
  "How to use a token" curl example.
- **Mongo indexes added**: `pats.id` (unique), `pats.prefix` (unique),
  `pats.[user_id, revoked_at]`.

**Trending tags strip** — public social proof on Landing
- **`GET /api/agg/trending-tags?days=14&limit=8`** — public endpoint
  returning top hashtags from approved member posts in the last 14 days.
  No auth required (used by the public Landing page).
- **`TrendingTagsStrip`** component on `/`, positioned between
  `TheFeedSection` and `TheNetworkSection` so the visitor sees actual
  content topics members are writing about, right between the news pillar
  and the writers pillar. Tag chips link to `/tag/:tag`.
- Eyebrow: "What members are writing about · last 14 days". Tag pills
  display `#tag` + count.

## Phase 15 — "Connect Claude" recipe card in /settings (2026-02-16)
- Replaced the simple `<details>How to use a token` curl block with a
  **tabbed "Quick connect" recipes panel** showing copy-pasteable snippets
  for the four most common integrations:
  - **Claude (Projects)** — drop-in Project Instructions that teach Claude
    how to POST to `/api/posts` on the user's behalf with their PAT.
  - **ChatGPT (Custom GPT Actions)** — full OpenAPI 3.0 schema ready to
    paste into the Custom GPT Actions editor; `bearerAuth` security wired.
  - **n8n / Zapier / Make** — HTTP-Request-node config (method, URL,
    headers, body shape).
  - **Curl / Script** — bash + Python `requests` snippets.
- Each tab has its own Copy button and a 1-line note about where to paste
  the snippet. If the user just created a token this session, the snippets
  inline the actual raw value; otherwise a `<your-thn-pat-token>`
  placeholder is shown with a footer hint to substitute it.
- API base URL is auto-derived from `window.location.origin` so the
  recipes are accurate in any deployment.

## Backlog
- P0 (user action): DNS for thehousingnews.com.
- P0 (user action): Newsletter provider choice + API key.
- P0 (user action): Analytics provider choice + domain key.
- P1 (Phase 3): Morning + Evening briefing email templates + Brevo dispatcher
  (8:30 AM / 5:30 PM cron).
- P2: Add real member profile photos to Landing "From the feed" rows.
- P2: Personal Access Tokens (PATs) for programmatic posting — user said WAIT.
- P3: Upgrade LinkedIn URL import to Proxycurl for full work-history fetch.
- P0 Epic (long-term): Migrate React SPA to Next.js + TS per aggregator brief.

## Next Actions
1. Build Phase 3 email templates + Brevo dispatcher for 8:30 AM / 5:30 PM
   briefings (P1).
2. Add real member photos to Landing "From the feed" rows (P2).

