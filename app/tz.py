"""Timezone utilities.

All datetimes are stored as UTC in the database.
Jakarta (Asia/Jakarta, UTC+7) is used for display, month grouping, and as the
default timezone for users whose timezone is unknown.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func as sa_func

from app.config import settings

JAKARTA = ZoneInfo(settings.timezone)
UTC = timezone.utc

JAKARTA_UTC_OFFSET = "+7 hours"

USER_TIMEZONES: dict[str, str] = {
    "fazrin": "Asia/Jakarta",
    "magfira": "Australia/Sydney",
}

DEFAULT_TIMEZONE = settings.timezone


def get_user_timezone(user_id: str) -> ZoneInfo:
    """Look up a user's configured timezone, defaulting to Jakarta."""
    tz_name = USER_TIMEZONES.get(user_id, DEFAULT_TIMEZONE)
    return ZoneInfo(tz_name)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def now_jakarta() -> datetime:
    return datetime.now(tz=JAKARTA)


def to_utc(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to UTC.

    Naive datetimes are assumed to be Jakarta time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JAKARTA)
    return dt.astimezone(UTC)


def resolve_effective_at(
    dt: datetime | None,
    timezone_name: str | None,
    user_id: str,
) -> datetime:
    """Resolve an effective_at value to UTC.

    Resolution order:
    1. dt is None → now in UTC
    2. dt has tzinfo → convert to UTC directly
    3. dt is naive + timezone_name provided → localize, then convert
    4. dt is naive + no timezone_name → use user's configured timezone
    """
    if dt is None:
        return now_utc()

    if dt.tzinfo is not None:
        return dt.astimezone(UTC)

    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
        except (KeyError, ValueError):
            tz = get_user_timezone(user_id)
    else:
        tz = get_user_timezone(user_id)

    return dt.replace(tzinfo=tz).astimezone(UTC)


def to_jakarta(dt: datetime) -> datetime:
    """Convert any datetime to Jakarta time.

    Naive datetimes are assumed to be UTC (as stored in the database).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JAKARTA)


def col_as_jakarta(column):
    """SQLite expression: shift a UTC datetime column to Jakarta for grouping."""
    return sa_func.datetime(column, JAKARTA_UTC_OFFSET)
