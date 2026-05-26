"""One-shot cleanup: deactivate Reddit publishers in the aggregator and
delete all of their cached articles.

Reddit feeds were producing low-signal content. Rather than hard-delete
the publisher rows (which would orphan article references and break the
audit trail), we set ``active=False`` so the ingest job skips them, then
purge their articles so they vanish from the public feed immediately.

Usage:
    cd /app/backend && python scripts/remove_reddit_feeds.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

# Ensure /app/backend is importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Match by rss_url host, slug prefix `r-`, or name starting with `r/`.
    query = {
        "$or": [
            {"rss_url": {"$regex": "reddit\\.com", "$options": "i"}},
            {"slug": {"$regex": "^r-", "$options": "i"}},
            {"name": {"$regex": "^r/", "$options": "i"}},
        ]
    }

    targets = await db.agg_publishers.find(query, {"_id": 0, "id": 1, "slug": 1, "name": 1, "active": 1}).to_list(500)
    if not targets:
        print("No Reddit publishers found. Nothing to do.")
        return

    print(f"Found {len(targets)} Reddit publishers:")
    for p in targets:
        print(f"  - {p.get('slug')} | {p.get('name')} | active={p.get('active')}")

    publisher_ids = [p["id"] for p in targets]

    deact = await db.agg_publishers.update_many(
        {"id": {"$in": publisher_ids}},
        {"$set": {"active": False}},
    )
    print(f"Deactivated {deact.modified_count} publishers.")

    arts = await db.agg_articles.delete_many({"publisher_id": {"$in": publisher_ids}})
    print(f"Deleted {arts.deleted_count} articles.")

    # Sanity check the remaining state.
    remaining = await db.agg_publishers.count_documents({"id": {"$in": publisher_ids}, "active": True})
    print(f"Remaining active Reddit publishers: {remaining} (should be 0)")


if __name__ == "__main__":
    asyncio.run(main())
