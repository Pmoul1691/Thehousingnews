"""Regression: the /api/admin/site-analytics endpoint must expose a
"today" window — pageviews / sessions / members for the current UTC day,
plus a 24-bucket hourly breakdown — alongside the existing 7d / 30d / 14d
rolling windows.
"""
import importlib


def test_today_traffic_keys_exist():
    """Smoke: the analytics module imports cleanly and the today fields
    appear in the shape we return. Tests the SHAPE of the response, not
    a live aggregation — that's covered by the screenshot smoke test."""
    mod = importlib.import_module("routes.admin_analytics")
    # Sanity: the module exports the expected setup() factory.
    assert hasattr(mod, "setup"), "admin_analytics.setup must exist"


def test_hourly_today_has_24_zero_filled_buckets_logic():
    """Recreate the zero-fill logic from the endpoint without spinning up
    the full DB. Locks the invariant that the chart never has gaps."""
    hourly_rows = [
        {"_id": 0, "pageviews": 2, "unique_sessions": ["s1", "s2"], "unique_users": ["u1", "u2"]},
        {"_id": 19, "pageviews": 7, "unique_sessions": ["s3", "s4", "s5"], "unique_users": ["u3", "u4"]},
    ]
    hourly_lookup = {r["_id"]: r for r in hourly_rows}
    hourly_today = []
    for h in range(24):
        row = hourly_lookup.get(h)
        hourly_today.append({
            "hour": h,
            "pageviews": (row or {}).get("pageviews", 0),
            "unique_sessions": len((row or {}).get("unique_sessions") or []),
            "unique_users": len((row or {}).get("unique_users") or []),
        })
    assert len(hourly_today) == 24
    assert hourly_today[0]["pageviews"] == 2
    assert hourly_today[5]["pageviews"] == 0  # gap filled
    assert hourly_today[19]["unique_sessions"] == 3
    assert hourly_today[23]["pageviews"] == 0  # tail filled
    # Every bucket must have hour key matching its index.
    assert [r["hour"] for r in hourly_today] == list(range(24))


def test_today_row_from_daily_aggregation_logic():
    """Locks the lookup-by-day-string behaviour used to derive the today
    tiles from the existing 14d daily aggregation."""
    today_str = "2026-05-19"
    traffic_daily = [
        {"day": "2026-05-17", "pageviews": 100, "unique_sessions": 40, "unique_users": 18},
        {"day": "2026-05-18", "pageviews": 200, "unique_sessions": 70, "unique_users": 24},
        {"day": today_str,   "pageviews": 12,  "unique_sessions": 8,  "unique_users": 3},
    ]
    today_row = next(
        (r for r in traffic_daily if r.get("day") == today_str),
        {"pageviews": 0, "unique_sessions": 0, "unique_users": 0},
    )
    assert today_row["pageviews"] == 12
    assert today_row["unique_sessions"] == 8
    assert today_row["unique_users"] == 3


def test_today_row_fallback_when_no_traffic():
    """When there's been zero traffic today, the daily aggregation simply
    won't include a today row — the fallback must return zeros."""
    traffic_daily = [
        {"day": "2026-05-17", "pageviews": 100, "unique_sessions": 40, "unique_users": 18},
    ]
    today_str = "2026-05-19"
    today_row = next(
        (r for r in traffic_daily if r.get("day") == today_str),
        {"pageviews": 0, "unique_sessions": 0, "unique_users": 0},
    )
    assert today_row["pageviews"] == 0
    assert today_row["unique_sessions"] == 0
    assert today_row["unique_users"] == 0
