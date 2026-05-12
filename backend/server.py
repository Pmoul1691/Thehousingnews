"""The Ultradian Network - FastAPI server."""
from fastapi import FastAPI
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import sys
sys.path.insert(0, str(ROOT_DIR))

from routes.auth import setup as setup_auth
from routes.applications import setup as setup_apps
from routes.profiles import setup as setup_profiles
from routes.posts import setup as setup_posts
from routes.uploads import setup as setup_uploads
from services.object_storage import init_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Mongo
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="The Ultradian Network")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
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
    await db.posts.create_index("post_id", unique=True)
    await db.posts.create_index([("created_at", -1)])
    await db.posts.create_index("user_id")
    await db.files.create_index("storage_path")
    logger.info("Startup complete")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# Health
@app.get("/api/")
async def root():
    return {"name": "The Ultradian Network", "ok": True}


@app.get("/api/release-window")
async def release_window():
    """Compute the next 8:30am or 5:30pm America/Chicago timestamp."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Chicago")
    except Exception:
        # Fallback to UTC if tz data missing
        tz = timezone.utc
    now_local = datetime.now(tz)
    am = now_local.replace(hour=8, minute=30, second=0, microsecond=0)
    pm = now_local.replace(hour=17, minute=30, second=0, microsecond=0)
    if now_local < am:
        nxt = am
    elif now_local < pm:
        nxt = pm
    else:
        nxt = (am + timedelta(days=1))
    return {
        "next_release_iso": nxt.isoformat(),
        "next_release_label": nxt.strftime("%-I:%M%p").lower(),
        "timezone": "America/Chicago",
    }


# Mount routers
app.include_router(setup_auth(db))
app.include_router(setup_apps(db))
app.include_router(setup_profiles(db))
app.include_router(setup_posts(db))
app.include_router(setup_uploads(db))
