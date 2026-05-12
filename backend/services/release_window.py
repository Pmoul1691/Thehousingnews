"""Release window helpers. The Network releases posts at 8:30am and 5:30pm America/Chicago."""
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    CHICAGO = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    from datetime import timezone
    CHICAGO = timezone.utc


def now_chicago() -> datetime:
    return datetime.now(CHICAGO)


def next_window(after: datetime | None = None) -> datetime:
    """Return the next 8:30am or 5:30pm in America/Chicago after the given moment.

    after: timezone-aware datetime. Defaults to now.
    """
    if after is None:
        after = now_chicago()
    else:
        after = after.astimezone(CHICAGO)
    am = after.replace(hour=8, minute=30, second=0, microsecond=0)
    pm = after.replace(hour=17, minute=30, second=0, microsecond=0)
    if after < am:
        return am
    if after < pm:
        return pm
    return am + timedelta(days=1)


def previous_window(before: datetime | None = None) -> datetime:
    """Return the most recent release window strictly before the given moment."""
    if before is None:
        before = now_chicago()
    else:
        before = before.astimezone(CHICAGO)
    am = before.replace(hour=8, minute=30, second=0, microsecond=0)
    pm = before.replace(hour=17, minute=30, second=0, microsecond=0)
    if before > pm:
        return pm
    if before > am:
        return am
    return pm - timedelta(days=1)


def window_label(dt: datetime) -> str:
    """Format a window time. e.g. '8:30am CT' or '5:30pm CT'."""
    dt_local = dt.astimezone(CHICAGO)
    return dt_local.strftime("%-I:%M%p").lower() + " CT"


def window_kind(dt: datetime) -> str:
    """Return 'am' or 'pm' for a window datetime."""
    dt_local = dt.astimezone(CHICAGO)
    return "am" if dt_local.hour < 12 else "pm"
