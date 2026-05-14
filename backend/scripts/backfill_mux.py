"""One-off: backfill Mux video metadata on existing Substack-imported essays
that were saved before substack_fetch existed.
"""
import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient
from services.substack_fetch import fetch_substack_media

logging.basicConfig(level=logging.INFO)


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    cursor = db.posts.find({"source": "substack_import"}, {"_id": 0, "post_id": 1, "source_url": 1, "media": 1, "title": 1})
    fixed = 0
    skipped = 0
    async for p in cursor:
        existing = p.get("media") or []
        if any((m.get("source") == "substack_mux") for m in existing):
            skipped += 1
            continue
        if not p.get("source_url"):
            skipped += 1
            continue
        mux = fetch_substack_media(p["source_url"])
        if not mux:
            print("no mux for", p["post_id"], p["title"][:50])
            skipped += 1
            continue
        new_media = [mux] + [m for m in existing if m.get("source") != "substack_mux"]
        await db.posts.update_one({"post_id": p["post_id"]}, {"$set": {"media": new_media}})
        print("attached mux for", p["post_id"], "->", mux["external_hls_url"][:80])
        fixed += 1
    print(f"\nfixed: {fixed}, skipped: {skipped}")

asyncio.run(main())
