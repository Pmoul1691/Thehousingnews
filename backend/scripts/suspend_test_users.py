"""Suspend obvious test accounts so they don't pollute the production
Members directory.

This script is DRY-RUN BY DEFAULT. It prints who would be affected and
exits. To actually apply the change, pass `--apply`.

Soft delete only: sets `suspended: true` and `suspended_reason`. The row
is preserved so it can be reversed by toggling the flag from the admin
panel, and so the audit trail (created_at, source, email) is intact.

Run inside the backend container:
    cd /app/backend && python -m scripts.suspend_test_users           # dry-run
    cd /app/backend && python -m scripts.suspend_test_users --apply    # commit
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

# Single source of truth for the "is this email a test fixture?" check.
# Lives in services/ so the live API endpoints can import it too.
from services.test_email_filter import is_test_email


async def main(apply: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Find every approved, not-already-suspended user whose email matches
    # a test pattern. Skip admins as a final guardrail.
    cur = db.users.find(
        {"status": "approved", "suspended": {"$ne": True}, "is_admin": {"$ne": True}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "created_at": 1, "source": 1},
    )
    candidates = []
    async for u in cur:
        if is_test_email(u.get("email") or ""):
            candidates.append(u)

    mode = "WOULD SUSPEND" if not apply else "SUSPENDING"
    print(f"\n{mode} {len(candidates)} test users on database {os.environ['DB_NAME']}\n")
    for u in candidates:
        print(f"  - {u.get('email'):60} {u.get('name') or '(no name)':30} src={u.get('source') or '?':18} created={u.get('created_at') or '?'}")

    if not apply:
        print("\nDry-run only. No changes made.")
        print("To apply, re-run with --apply.\n")
        return

    if not candidates:
        print("\nNothing to suspend.\n")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_many(
        {"user_id": {"$in": [u["user_id"] for u in candidates]}},
        {"$set": {
            "suspended": True,
            "suspended_at": now_iso,
            "suspended_reason": "test_account_cleanup",
        }},
    )
    print(f"\nSuspended {result.modified_count} users.")
    print("Reverse with: db.users.updateMany({suspended_reason:'test_account_cleanup'}, {$unset:{suspended:'', suspended_at:'', suspended_reason:''}})\n")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply=apply))
