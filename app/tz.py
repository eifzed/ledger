"""Timezone utilities."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings

JAKARTA = ZoneInfo(settings.timezone)


def now_jakarta() -> datetime:
    return datetime.now(tz=JAKARTA)
