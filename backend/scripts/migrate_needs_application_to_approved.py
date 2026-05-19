"""One-shot migration: bump every legacy `needs_application` user to
`approved` as part of the "free forever" pivot.

Run inside the backend container:
    cd /app/backend && python -m scripts.migrate_needs_application_to_approved

After running, the Members directory will include those users immediately
(profile-less rows surface with a fallback name from the email username).
The migration is idempotent — a second run is a no-op.
"""
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    pending = await db.users.count_documents({"status": "needs_application"})
    print(f"Users still in legacy needs_application status: {pending}")
    if pending == 0:
        print("Nothing to migrate.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_many(
        {"status": "needs_application"},
        {"$set": {
            "status": "approved",
            "free_forever_migrated_at": now_iso,
        }},
    )
    print(f"Updated {result.modified_count} users to status=approved")


if __name__ == "__main__":
    asyncio.run(main())
