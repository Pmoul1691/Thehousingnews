"""One-time data migrations that run on backend startup.

Each migration writes a marker doc to `db.migrations` so it never runs
again. Adding a migration is just appending another entry to MIGRATIONS.

Why a custom runner and not Alembic-style tooling? Mongo schema is
flexible enough that we don't need a heavy framework, and these are
data-cleanups (not schema changes). The marker collection keeps it
idempotent across pod restarts and across multiple replicas (a write
race on insert is harmless — the migration is still safe to run twice
because the underlying ops use update_many / delete_many on stable
queries).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _migration_001_remove_reddit_feeds(db) -> dict:
    """Deactivate Reddit aggregator publishers and purge their articles.

    Matches by rss_url regex, slug prefix `r-`, or name prefix `r/`.
    Sets `active=False` rather than hard-deleting publisher rows so audit
    history (e.g. trending counts, article→publisher joins) keeps working.
    Articles are hard-deleted so they vanish from the public feed.
    """
    query = {
        "$or": [
            {"rss_url": {"$regex": "reddit\\.com", "$options": "i"}},
            {"slug": {"$regex": "^r-", "$options": "i"}},
            {"name": {"$regex": "^r/", "$options": "i"}},
        ]
    }
    targets = await db.agg_publishers.find(
        query, {"_id": 0, "id": 1, "slug": 1, "name": 1}
    ).to_list(500)
    if not targets:
        return {"publishers_deactivated": 0, "articles_deleted": 0}

    ids = [p["id"] for p in targets]
    deact = await db.agg_publishers.update_many(
        {"id": {"$in": ids}}, {"$set": {"active": False}}
    )
    arts = await db.agg_articles.delete_many({"publisher_id": {"$in": ids}})
    logger.info(
        "migration_001_remove_reddit_feeds: deactivated %s publishers (%s), deleted %s articles",
        deact.modified_count,
        ", ".join(p.get("slug", "?") for p in targets),
        arts.deleted_count,
    )
    return {
        "publishers_deactivated": deact.modified_count,
        "articles_deleted": arts.deleted_count,
    }


# Ordered list of (migration_id, async runner). New entries get appended.
MIGRATIONS = [
    ("001_remove_reddit_feeds", _migration_001_remove_reddit_feeds),
]


async def run_pending_migrations(db) -> None:
    """Run every migration that hasn't been recorded yet. Safe to call on
    every startup — already-run migrations are skipped via the marker
    collection."""
    try:
        await db.migrations.create_index("migration_id", unique=True)
    except Exception:
        # Index creation is best-effort; the unique constraint protects
        # us anyway on insert.
        pass

    for mig_id, runner in MIGRATIONS:
        existing = await db.migrations.find_one(
            {"migration_id": mig_id}, {"_id": 0, "migration_id": 1}
        )
        if existing:
            continue
        logger.info("Running migration: %s", mig_id)
        try:
            result = await runner(db)
            await db.migrations.insert_one({
                "migration_id": mig_id,
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            })
            logger.info("Migration %s complete: %s", mig_id, result)
        except Exception:
            # Don't crash startup over a single migration failure — log
            # loudly and skip. We don't mark it as run so it gets
            # retried on next boot.
            logger.exception("Migration %s failed", mig_id)
