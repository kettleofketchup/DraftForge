"""Upcoming/archived bucket math for the tournament list."""

from datetime import UTC, datetime, timedelta

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

UPCOMING_STATES: list[str] = ["future", "in_progress"]


def _now() -> datetime:
    return timezone.now()


def utc_day_start(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(UTC).date(), datetime.min.time(), tzinfo=UTC)


def tournament_bucket_cutoff(now: datetime | None = None) -> datetime:
    return utc_day_start(now if now is not None else _now()) - timedelta(days=2)


def upcoming_q(cutoff: datetime) -> Q:
    return Q(state__in=UPCOMING_STATES, date_played__gte=cutoff)


def upcoming_rank(today_start: datetime) -> Case:
    return Case(
        When(state="in_progress", then=Value(0)),
        When(date_played__gte=today_start, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
