from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import Config


def get_display_timezone(config: Config):
    try:
        return ZoneInfo(config.display_timezone)
    except ZoneInfoNotFoundError:
        return timezone.utc


def to_display_datetime(dt: datetime, config: Config) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_display_timezone(config))


def format_local_dt(dt: datetime, config: Config, fmt: str = "%d.%m.%Y %H:%M") -> str:
    return to_display_datetime(dt, config).strftime(fmt)


def format_now_local(config: Config, fmt: str = "%d.%m.%Y %H:%M") -> str:
    return datetime.now(get_display_timezone(config)).strftime(fmt)
