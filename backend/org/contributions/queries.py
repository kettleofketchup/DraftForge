from collections import defaultdict
from datetime import datetime
from typing import TypedDict

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from app.models import Organization
from org.contributions.periods import Period, parse_period, resolve_org_tz
from org.models import ContributionEntry, OrgUser
from user.querysets import with_user_profiles


class LeaderboardRow(TypedDict):
    org_user_pk: int
    user_pk: int
    username: str
    nickname: str | None
    avatarUrl: str | None
    points: int
    entries: int


class MonthPoints(TypedDict):
    month: str
    points: int


class MemberTotals(TypedDict):
    all_time: int
    this_month: int


def _in_period(
    qs: QuerySet[ContributionEntry], period: Period
) -> QuerySet[ContributionEntry]:
    if period.start is not None:
        qs = qs.filter(occurred_at__gte=period.start)
    if period.end is not None:
        qs = qs.filter(occurred_at__lt=period.end)
    return qs


def _sum(qs: QuerySet[ContributionEntry]) -> int:
    return qs.aggregate(total=Sum("points"))["total"] or 0


def org_total(org: Organization, period: Period) -> int:
    return _sum(
        _in_period(ContributionEntry.objects.nocache().filter(organization=org), period)
    )


def leaderboard(
    org: Organization, period: Period, *, limit: int = 100
) -> list[LeaderboardRow]:
    sums = list(
        _in_period(ContributionEntry.objects.nocache().filter(organization=org), period)
        .values("org_user")
        .annotate(total=Sum("points"), entries=Count("pk"))
        .filter(~Q(total=0))
        .order_by("-total", "org_user__user__username", "org_user")[:limit]
    )
    org_users = with_user_profiles(
        OrgUser.objects.filter(pk__in=[s["org_user"] for s in sums]), "user"
    ).in_bulk()
    rows: list[LeaderboardRow] = []
    for s in sums:
        user = org_users[s["org_user"]].user
        rows.append(
            LeaderboardRow(
                org_user_pk=s["org_user"],
                user_pk=user.pk,
                username=user.username,
                nickname=user.nickname,
                avatarUrl=user.avatarUrl,
                points=s["total"],
                entries=s["entries"],
            )
        )
    return rows


def member_entries(org_user: OrgUser, period: Period) -> QuerySet[ContributionEntry]:
    return (
        _in_period(
            ContributionEntry.objects.nocache().filter(org_user=org_user), period
        )
        .select_related("event")
        .order_by("-occurred_at", "-pk")
    )


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def member_monthly(
    org_user: OrgUser, *, months: int = 12, now: datetime | None = None
) -> list[MonthPoints]:
    org = org_user.organization
    tz = resolve_org_tz(org)
    local_now = (now or timezone.now()).astimezone(tz)
    index = local_now.year * 12 + local_now.month - 1
    keys = [
        _month_key(i // 12, i % 12 + 1) for i in range(index - months + 1, index + 1)
    ]
    start = parse_period(org, keys[0]).start
    buckets: defaultdict[str, int] = defaultdict(int)
    for occurred_at, points in (
        ContributionEntry.objects.nocache()
        .filter(org_user=org_user, occurred_at__gte=start)
        .values_list("occurred_at", "points")
    ):
        local = occurred_at.astimezone(tz)
        buckets[_month_key(local.year, local.month)] += points
    return [MonthPoints(month=key, points=buckets.get(key, 0)) for key in keys]


def member_totals(org_user: OrgUser, *, now: datetime | None = None) -> MemberTotals:
    org = org_user.organization
    local_now = (now or timezone.now()).astimezone(resolve_org_tz(org))
    this_month = parse_period(org, _month_key(local_now.year, local_now.month))
    qs = ContributionEntry.objects.nocache().filter(org_user=org_user)
    return MemberTotals(all_time=_sum(qs), this_month=_sum(_in_period(qs, this_month)))
