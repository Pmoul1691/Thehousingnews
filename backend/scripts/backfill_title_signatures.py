"""One-shot backfill: stamp title_signature + title_normalized on every
existing agg_articles row that doesn't have them yet.

Run inside the backend container:
    cd /app/backend && python -m scripts.backfill_title_signatures
"""
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

# Allow importing services/ when run as a module from /app/backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rss_ingest import normalize_title, title_signature  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    total = await db.agg_articles.count_documents({})
    todo = await db.agg_articles.count_documents(
        {"$or": [{"title_signature": {"$exists": False}}, {"title_signature": ""}]}
    )
    print(f"agg_articles total={total}  needs_backfill={todo}")
    if todo == 0:
        print("Nothing to do.")
        return

    cur = db.agg_articles.find(
        {"$or": [{"title_signature": {"$exists": False}}, {"title_signature": ""}]},
        {"_id": 0, "id": 1, "title": 1},
    )
    updated = 0
    async for row in cur:
        title = row.get("title") or ""
        norm = normalize_title(title)
        sig = title_signature(title)
        if not sig:
            continue
        await db.agg_articles.update_one(
            {"id": row["id"]},
            {"$set": {"title_normalized": norm, "title_signature": sig}},
        )
        updated += 1
        if updated % 200 == 0:
            print(f"  ...{updated} updated")

    print(f"Done. Stamped {updated} articles.")


if __name__ == "__main__":
    asyncio.run(main())
