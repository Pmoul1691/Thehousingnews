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
