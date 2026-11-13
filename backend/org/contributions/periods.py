import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import Organization
from telemetry.logging import get_logger

log = get_logger(__name__)

ALL_TIME = "all"
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_MIN_YEAR = 1970
_MAX_YEAR = 9998


@dataclass(frozen=True)
class Period:
    start: datetime | None
    end: datetime | None
    label: str


def resolve_org_tz(org: Organization) -> ZoneInfo:
    name = org.timezone or ""
    try:
        if not name:
            raise ZoneInfoNotFoundError(name)
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        log.warning(
            "org_timezone_invalid",
            system="org",
            subsystem="contributions",
            org_id=org.pk,
            timezone=name,
        )
        return ZoneInfo("UTC")


def _local_to_utc(tz: ZoneInfo, d: date, t: time) -> datetime:
    try:
        return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)
    except OverflowError as exc:
        raise ValueError(f"date {d.isoformat()} out of range") from exc


def local_noon_utc(org: Organization, d: date) -> datetime:
    return _local_to_utc(resolve_org_tz(org), d, time(12))


def local_day_start_utc(org: Organization, d: date) -> datetime:
    return _local_to_utc(resolve_org_tz(org), d, time(0))


def parse_period(org: Organization, value: str | None) -> Period:
    if value is None or value == ALL_TIME:
        return Period(start=None, end=None, label=ALL_TIME)
    match = _MONTH_RE.match(value)
    if not match:
        raise ValueError(f"invalid period {value!r}, expected 'all' or YYYY-MM")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month in period {value!r}")
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        raise ValueError(f"year out of range in period {value!r}")
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    tz = resolve_org_tz(org)
    return Period(
        start=_local_to_utc(tz, date(year, month, 1), time(0)),
        end=_local_to_utc(tz, date(next_year, next_month, 1), time(0)),
        label=value,
    )
