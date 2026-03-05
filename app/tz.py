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
