from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import Throttled

from org.models import OrgApiLimits, OrgApiToken, OrgApiTokenUsage
from org.models_api_tokens import DEFAULT_PER_DAY, DEFAULT_PER_MINUTE
from telemetry.logging import get_logger

log = get_logger(__name__)

MINUTE_KEY = "org_api_rl:{token_id}:{window}"


@dataclass(frozen=True)
class Limits:
    per_minute: int
    per_day: int


def limits_for(org_id: int) -> Limits:
    row = OrgApiLimits.objects.filter(organization_id=org_id).first()
    if row is None:
        return Limits(per_minute=DEFAULT_PER_MINUTE, per_day=DEFAULT_PER_DAY)
    return Limits(per_minute=row.per_minute, per_day=row.per_day)


def _minute_count(token_id: int, now: datetime) -> int | None:
    window = int(now.timestamp()) // 60
    key = MINUTE_KEY.format(token_id=token_id, window=window)
    try:
        cache.add(key, 0, timeout=120)
        return int(cache.incr(key))
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "org_api_rate_cache_unavailable",
            system="org",
            subsystem="api_tokens",
            token_id=token_id,
            error=str(exc),
        )
        return None


def _usage_row(token: OrgApiToken, day: date) -> OrgApiTokenUsage:
    row, _ = OrgApiTokenUsage.objects.get_or_create(
        token=token,
        date=day,
        defaults={"organization_id": token.organization_id, "user_id": token.user_id},
    )
    return row


def _reject(token: OrgApiToken, row: OrgApiTokenUsage, scope: str, wait: int) -> None:
    OrgApiTokenUsage.objects.filter(pk=row.pk).update(
        throttled_count=F("throttled_count") + 1
    )
    log.info(
        "org_api_throttled",
        system="org",
        subsystem="api_tokens",
        org_id=token.organization_id,
        token_id=token.pk,
        user_id=token.user_id,
        scope=scope,
    )
    raise Throttled(wait=wait, detail=f"Request limit exceeded ({scope}).")


def check_and_record(token: OrgApiToken) -> None:
    """Count one request against the token; raise Throttled when over a limit."""
    now = timezone.now()
    limits = limits_for(token.organization_id)
    row = _usage_row(token, now.date())

    minute = _minute_count(token.pk, now)
    if minute is not None and minute > limits.per_minute:
        _reject(token, row, "per_minute", 60 - now.second)

    admitted = OrgApiTokenUsage.objects.filter(
        pk=row.pk, request_count__lt=limits.per_day
    ).update(request_count=F("request_count") + 1)
    if not admitted:
        midnight = datetime.combine(
            now.date() + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo
        )
        _reject(token, row, "per_day", int((midnight - now).total_seconds()) + 1)

    OrgApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
