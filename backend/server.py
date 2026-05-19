"""The Housing News - FastAPI server."""
from fastapi import FastAPI
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from datetime import timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import sys
sys.path.insert(0, str(ROOT_DIR))

from routes.auth import setup as setup_auth
from routes.applications import setup as setup_apps
from routes.profiles import setup as setup_profiles
from routes.posts import setup as setup_posts
from routes.replies import setup as setup_replies
from routes.uploads import setup as setup_uploads
from routes.users import setup as setup_users
from routes.moderation import setup as setup_moderation
from routes.picks import setup as setup_picks
from routes.analytics import setup as setup_analytics
from routes.payments import setup as setup_payments
from routes.essays import setup as setup_essays
from routes.drafts import setup as setup_drafts
from routes.reader import setup as setup_reader
from routes.writer import setup as setup_writer
from routes.tracking import setup as setup_tracking
from routes.invites import setup as setup_invites
from routes.email_health import setup as setup_email_health
from routes.prompts import setup as setup_prompts
from routes.admin_rss import setup as setup_admin_rss
from routes.admin_orphans import setup as setup_admin_orphans
from routes.partners import setup as setup_partners
from routes.aggregator import setup as setup_aggregator
from routes.aggregator_admin import setup as setup_aggregator_admin
from routes.aggregator_suggestions import setup as setup_aggregator_suggestions
from routes.admin_reset import setup as setup_admin_reset
from routes.admin_invite import setup as setup_admin_invite
from routes.admin_briefings import setup as setup_admin_briefings
from routes.admin_dashboard import setup as setup_admin_dashboard
from routes.refresh_feeds import setup as setup_refresh_feeds
from routes.pats import setup as setup_pats
from routes.podcasts import setup as setup_podcasts
from routes.today import setup as setup_today
from routes.admin_moderation import setup as setup_admin_moderation
from routes.admin_launch import setup as setup_admin_launch
from routes.newsletter import setup as setup_newsletter
from routes.improvements import setup as setup_improvements
from routes.admin_users import setup as setup_admin_users
from routes.admin_posts import setup as setup_admin_posts
from routes.auth_email import setup as setup_auth_email
from routes.regions import setup as setup_regions
from routes.mcp import setup as setup_mcp
from routes.events import setup as setup_events
from routes.admin_analytics import setup as setup_admin_analytics
from services.object_storage import init_storage
from services.release_window import next_window, now_chicago
from services.scheduler import start_scheduler, release_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Mongo
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="The Housing News")
app.state.scheduler = None

_cors_env = os.environ.get("CORS_ORIGINS", "*")
if _cors_env.strip() == "*":
    # Reflect the request Origin so credentialed requests work
    # (browsers reject Access-Control-Allow-Origin: * with credentials).
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=".*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=[o.strip() for o in _cors_env.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
async def on_startup():
    try:
        init_storage()
    except Exception as e:
        logger.warning("Object storage init failed at startup: %s", e)
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at")
    await db.applications.create_index("application_id", unique=True)
    await db.applications.create_index("user_id")
    await db.applications.create_index("status")
    await db.profiles.create_index("user_id", unique=True)
    # Used by the /auth/session profile-recovery path to reattach a returning
    # member to their existing profile when the user row was wiped out of band.
    await db.profiles.create_index("email", sparse=True)
    # Partial unique index on posts.source_guid scoped to substack imports so
    # the daily RSS cron can never duplicate an essay even if the dedupe
    # check races. Other post kinds (manual essays, short posts) do not have
    # a source_guid and are excluded by the partialFilterExpression.
    try:
        await db.posts.create_index(
            "source_guid",
            unique=True,
            partialFilterExpression={"source": "substack_import"},
        )
    except Exception as _e:
        # Index may have been created with different options on a prior boot;
        # surface a warning but do not block startup.
        logger.warning("posts.source_guid partial unique index not created: %s", _e)
    await db.posts.create_index("post_id", unique=True)
    await db.posts.create_index([("release_at", -1)])
    await db.posts.create_index([("user_id", 1), ("created_at", -1)])
    await db.posts.create_index("status")
    await db.posts.create_index("tags")
    # Full-text search across post body, title, subtitle (members-only `/posts/search`).
    try:
        await db.posts.create_index(
            [("text", "text"), ("title", "text"), ("subtitle", "text")],
            name="posts_text_search",
            default_language="english",
            weights={"title": 10, "subtitle": 4, "text": 1},
        )
    except Exception as _e:
        logger.warning("posts text index not created: %s", _e)
    await db.replies.create_index("reply_id", unique=True)
    await db.replies.create_index([("post_id", 1), ("created_at", 1)])
    await db.replies.create_index("status")
    await db.files.create_index("storage_path")
    await db.follows.create_index([("follower_id", 1), ("followed_id", 1)], unique=True)
    await db.follows.create_index("followed_id")
    await db.flags.create_index("flag_id", unique=True)
    await db.flags.create_index([("target_kind", 1), ("target_id", 1)])
    await db.flags.create_index("resolved")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index("user_id")
    await db.payment_transactions.create_index("payment_status")
    await db.essay_dispatches.create_index([("post_id", 1), ("recipient_user_id", 1)], unique=True)
    await db.essay_dispatches.create_index("post_id")
    await db.drafts.create_index("user_id", unique=True)
    await db.bookmarks.create_index([("user_id", 1), ("post_id", 1)], unique=True)
    await db.bookmarks.create_index([("user_id", 1), ("created_at", -1)])

    # === Aggregator (thehousingnews.com) collections ===
    try:
        await db.agg_publishers.create_index("id", unique=True)
        await db.agg_publishers.create_index("slug", unique=True)
        await db.agg_publishers.create_index("category")
        await db.agg_articles.create_index("id", unique=True)
        await db.agg_articles.create_index([("publisher_id", 1), ("guid", 1)], unique=True)
        await db.agg_articles.create_index("normalized_url", unique=True, sparse=True)
        await db.agg_articles.create_index([("published_at", -1)])
        await db.agg_articles.create_index("hidden")
        # Title-based fuzzy dedup: fast lookup for cross-publisher near-dupes.
        await db.agg_articles.create_index(
            [("title_signature", 1), ("published_at", -1)],
            sparse=True,
        )
        await db.agg_newsletter_signups.create_index("email", unique=True)
    except Exception as _e:
        logger.warning("aggregator indexes not created: %s", _e)

    # Seed publishers (idempotent — only inserts missing slugs).
    try:
        from services.agg_seed import SEED_PUBLISHERS, KEYWORD_FILTERS
        from datetime import datetime as _dt
        import uuid as _uuid
        _now = _dt.utcnow().isoformat()
        for name, slug, category, feed_url, homepage_url, display_mode, perm in SEED_PUBLISHERS:
            await db.agg_publishers.update_one(
                {"slug": slug},
                {"$setOnInsert": {
                    "id": str(_uuid.uuid4()),
                    "name": name, "slug": slug, "category": category,
                    "feed_url": feed_url, "homepage_url": homepage_url,
                    "logo_url": None, "display_mode": display_mode,
                    "refresh_minutes": 30, "active": True,
                    "permission_status": perm,
                    "last_fetched_at": None, "last_fetch_status": None,
                    "created_at": _now, "updated_at": _now,
                }},
                upsert=True,
            )
        # Apply per-publisher keyword filters (always overwrite so config in
        # agg_seed.py is the source of truth).
        for slug, kws in KEYWORD_FILTERS.items():
            await db.agg_publishers.update_one(
                {"slug": slug},
                {"$set": {"keyword_filter": kws, "updated_at": _now}},
            )
        # Reddit subreddits, sorted by Top of the month. Per editorial brief,
        # we use a descriptive UA and bypass our default robots.txt check
        # (Reddit's robots.txt blanket-disallows; the per-subreddit RSS
        # endpoint itself returns 200).
        from services.agg_seed import REDDIT_PUBLISHERS, REDDIT_UA, REDDIT_EXCLUDE_PATTERNS
        for name, slug, feed_url, homepage_url in REDDIT_PUBLISHERS:
            await db.agg_publishers.update_one(
                {"slug": slug},
                {"$setOnInsert": {
                    "id": str(_uuid.uuid4()),
                    "name": name, "slug": slug,
                    "homepage_url": homepage_url,
                    "logo_url": None, "display_mode": "headline_and_snippet",
                    "refresh_minutes": 240, "active": True,
                    "permission_status": "not_required",
                    "last_fetched_at": None, "last_fetch_status": None,
                    "created_at": _now,
                 },
                 "$set": {
                    "source_type": "reddit",
                    "user_agent": REDDIT_UA,
                    "bypass_robots": True,
                    "exclude_patterns": REDDIT_EXCLUDE_PATTERNS,
                    "feed_url": feed_url,
                    "category": "community_discussion",
                    "updated_at": _now,
                 }},
                upsert=True,
            )
    except Exception as _e:
        logger.warning("aggregator seed failed: %s", _e)
    await db.reads.create_index([("user_id", 1), ("post_id", 1)], unique=True)
    await db.email_dispatches.create_index("dispatch_id", unique=True)
    await db.email_dispatches.create_index("created_at")
    await db.email_dispatches.create_index([("kind", 1), ("post_id", 1)])
    await db.email_events.create_index([("dispatch_id", 1), ("kind", 1), ("created_at", -1)])
    await db.invite_codes.create_index("code", unique=True)
    await db.invite_codes.create_index([("owner_user_id", 1), ("quarter_key", 1)])
    await db.prompts.create_index("prompt_id", unique=True)
    await db.prompts.create_index([("status", 1), ("week_start", -1)])
    await db.prompt_suggestions.create_index("suggestion_id", unique=True)
    await db.prompt_suggestions.create_index([("status", 1), ("created_at", -1)])
    await db.posts.create_index("prompt_id")
    await db.transcode_jobs.create_index("job_id", unique=True)
    await db.transcode_jobs.create_index([("user_id", 1), ("created_at", -1)])
    await db.app_settings.create_index("key", unique=True)
    # PATs (Personal Access Tokens) — programmatic posting via Bearer thn_pat_*
    await db.pats.create_index("id", unique=True)
    await db.pats.create_index("prefix", unique=True)
    await db.pats.create_index([("user_id", 1), ("revoked_at", 1)])

    # Improvements (user-submitted feedback widget)
    try:
        await db.improvements.create_index("id", unique=True)
        await db.improvements.create_index([("status", 1), ("created_at", -1)])
    except Exception as _e:
        logger.warning("improvements indexes not created: %s", _e)

    # Email auth — single-use tokens + brute-force counters
    try:
        await db.auth_tokens.create_index("token", unique=True)
        await db.auth_tokens.create_index([("email", 1), ("kind", 1), ("created_at", -1)])
        await db.auth_tokens.create_index("expires_at")
        await db.login_attempts.create_index("identifier", unique=True)
    except Exception as _e:
        logger.warning("auth_tokens / login_attempts indexes not created: %s", _e)

    # Load DB-stored APP_PUBLIC_URL override into the process env so tracking links use it
    try:
        row = await db.app_settings.find_one({"key": "APP_PUBLIC_URL"}, {"_id": 0})
        if row and row.get("value"):
            import os as _os
            _os.environ["APP_PUBLIC_URL"] = row["value"]
            logger.info("APP_PUBLIC_URL loaded from db: %s", row["value"])
    except Exception:
        logger.exception("loading APP_PUBLIC_URL from db failed")
    # Warm the podcast directory cache in the background so the first user
    # request to /news doesn't pay the 10-feed cold-start cost.
    try:
        import asyncio
        from services.podcasts_directory import get_directory as _warm_podcasts
        asyncio.get_event_loop().run_in_executor(None, _warm_podcasts)
        logger.info("Podcast directory cache warmup scheduled")
    except Exception as _e:
        logger.warning("Podcast warmup failed to schedule: %s", _e)
    # Start scheduler
    try:
        app.state.scheduler = start_scheduler(db)
    except Exception as e:
        logger.warning("Scheduler start failed: %s", e)
    logger.info("Startup complete")


@app.on_event("shutdown")
async def on_shutdown():
    try:
        if app.state.scheduler:
            app.state.scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()


# Health
@app.get("/api/")
async def root():
    return {"name": "The Housing News", "ok": True}


@app.get("/api/release-window")
async def release_window():
    nxt = next_window()
    return {
        "next_release_iso": nxt.astimezone(timezone.utc).isoformat(),
        "next_release_local": nxt.isoformat(),
        "next_release_label": nxt.strftime("%-I:%M%p").lower(),
        "timezone": "America/Chicago",
        "now_local": now_chicago().isoformat(),
    }


from fastapi import Cookie, Header, HTTPException
from services.auth_helpers import get_current_user, is_admin_email


@app.post("/api/admin/release-now")
async def admin_release_now(
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
):
    """Admin trigger to fire the release job immediately. Useful for testing or recovery."""
    user = await get_current_user(db, session_token, authorization)
    if not is_admin_email(user["email"]):
        raise HTTPException(status_code=403, detail="Admin only")
    summary = await release_batch(db)
    return summary


# Mount routers
app.include_router(setup_auth(db))
app.include_router(setup_apps(db))
app.include_router(setup_profiles(db))
app.include_router(setup_posts(db))
app.include_router(setup_replies(db))
app.include_router(setup_uploads(db))
app.include_router(setup_users(db))
app.include_router(setup_moderation(db))
app.include_router(setup_picks(db))
app.include_router(setup_analytics(db))
app.include_router(setup_payments(db))
app.include_router(setup_essays(db))
app.include_router(setup_drafts(db))
app.include_router(setup_reader(db))
app.include_router(setup_writer(db))
app.include_router(setup_tracking(db))
invites_r, invite_public_r, referrals_r = setup_invites(db)
app.include_router(invites_r)
app.include_router(invite_public_r)
app.include_router(referrals_r)
app.include_router(setup_email_health(db))
prompts_pub_r, prompts_admin_r = setup_prompts(db)
app.include_router(prompts_pub_r)
app.include_router(prompts_admin_r)
app.include_router(setup_admin_rss(db))
app.include_router(setup_admin_orphans(db))
app.include_router(setup_partners(db))
app.include_router(setup_aggregator(db))
app.include_router(setup_aggregator_admin(db))
app.include_router(setup_aggregator_suggestions(db))
app.include_router(setup_admin_reset(db))
app.include_router(setup_admin_invite(db))
app.include_router(setup_admin_briefings(db))
app.include_router(setup_admin_dashboard(db))
app.include_router(setup_refresh_feeds(db))
app.include_router(setup_pats(db))
app.include_router(setup_podcasts(db))
app.include_router(setup_today(db))
app.include_router(setup_admin_moderation(db))
app.include_router(setup_mcp(db))
app.include_router(setup_events(db))
app.include_router(setup_admin_analytics(db))
app.include_router(setup_admin_launch(db))
app.include_router(setup_newsletter(db))
app.include_router(setup_improvements(db))
app.include_router(setup_admin_users(db))
app.include_router(setup_admin_posts(db))
app.include_router(setup_auth_email(db))
app.include_router(setup_regions(db))
