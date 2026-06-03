"""Quick baseline perf measurement. Used for memory/PERF_BASELINE.md + PERF_AFTER.md.

Measures:
- p50/p95 latency of GET /api/agg/articles, /api/agg/publishers-latest,
  /api/essays, /api/today (20 hits each, parallel).
- Full RSS ingest wall-clock time (via direct ingest_all_active call).

Run twice — once before refactor (saves PERF_BASELINE.md), once after
(saves PERF_AFTER.md). The destination file is controlled by `--out`.
"""
from __future__ import annotations
import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE = os.environ.get("PERF_API_BASE", "http://127.0.0.1:8001")
HITS = 20


PUBLIC_GETS = [
    "/api/agg/articles?limit=20&hours=48",
    "/api/agg/publishers-latest?hours=168",
    "/api/essays?limit=10",
    "/api/agg/trending?hours=24&limit=6",
    "/api/agg/network-stats",
]


async def hit(client: httpx.AsyncClient, path: str) -> float:
    t0 = time.perf_counter()
    r = await client.get(f"{API_BASE}{path}")
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000


async def measure_latency() -> dict:
    out: dict = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Warm-up
        for path in PUBLIC_GETS:
            try:
                await hit(client, path)
            except Exception:
                pass
        # Real measurement: 20 sequential hits per path (so we don't
        # measure server concurrency, just per-request latency).
        for path in PUBLIC_GETS:
            latencies = []
            for _ in range(HITS):
                try:
                    latencies.append(await hit(client, path))
                except Exception as e:
                    out[path] = {"error": str(e)}
                    latencies = []
                    break
            if latencies:
                latencies.sort()
                out[path] = {
                    "p50_ms": round(statistics.median(latencies), 1),
                    "p95_ms": round(latencies[int(len(latencies) * 0.95) - 1], 1),
                    "min_ms": round(min(latencies), 1),
                    "max_ms": round(max(latencies), 1),
                }
    return out


async def measure_ingest() -> dict:
    """Time a full ingest_all_active call against the live DB."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.rss_ingest import ingest_all_active

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    # Bump last_fetched_at back 24h so refresh window doesn't skip
    # everything.
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    await db.agg_publishers.update_many(
        {"active": True},
        {"$set": {"last_fetched_at": cutoff}},
    )
    t0 = time.perf_counter()
    res = await ingest_all_active(db)
    elapsed = time.perf_counter() - t0
    return {
        "wall_clock_s": round(elapsed, 2),
        "publishers_ran": res.get("ran", 0),
    }


async def run(out_path: str) -> None:
    print(f"Measuring against {API_BASE} ...")
    latency = await measure_latency()
    print("Latency done. Now measuring ingest (may take 60-180s).")
    try:
        ingest = await measure_ingest()
    except Exception as e:
        ingest = {"error": str(e)}

    body = ["# Perf snapshot", ""]
    body.append("## Endpoint latency (20 hits, sequential)")
    body.append("")
    body.append("| Endpoint | p50 ms | p95 ms | min ms | max ms |")
    body.append("|---|---|---|---|---|")
    for path, stats in latency.items():
        if "error" in stats:
            body.append(f"| `{path}` | error: {stats['error']} | | | |")
        else:
            body.append(
                f"| `{path}` | {stats['p50_ms']} | {stats['p95_ms']} | "
                f"{stats['min_ms']} | {stats['max_ms']} |"
            )
    body.append("")
    body.append("## Full RSS ingest")
    body.append("")
    if "error" in ingest:
        body.append(f"- error: {ingest['error']}")
    else:
        body.append(f"- wall_clock_s: {ingest['wall_clock_s']}")
        body.append(f"- publishers_ran: {ingest['publishers_ran']}")
    body.append("")
    Path(out_path).write_text("\n".join(body))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="Output markdown path")
    args = p.parse_args()
    asyncio.run(run(args.out))
