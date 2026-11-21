from collections import defaultdict
from datetime import datetime
from typing import TypedDict

from django.db.models import QuerySet, Sum
from django.utils import timezone

from app.display_names import first_name
from app.models import Organization
from org.models import ContributionEntry, OrgUser
from org.standing import ledger
from org.standing.periods import Period, month_period, resolve_org_tz
from user.querysets import with_user_profiles


class LeaderboardRow(TypedDict):
    org_user_pk: int
    user_pk: int
    username: str
    nickname: str | None
    discordNickname: str | None
    guildNickname: str | None
    avatarUrl: str | None
    points: int
    entries: int


class MonthPoints(TypedDict):
    month: str
    points: int


class MemberTotals(TypedDict):
    all_time: int
    this_month: int


def org_total(org: Organization, period: Period) -> int:
    return ledger.total(org.pk, track="contribution", period=period)


def leaderboard(
    org: Organization, period: Period, *, limit: int = 100
) -> list[LeaderboardRow]:
    sums = list(
        ledger.sum_by_member(org.pk, track="contribution", period=period)[:limit]
    )
    org_users = with_user_profiles(
        OrgUser.objects.filter(pk__in=[s["org_user"] for s in sums]), "user"
    ).in_bulk()
    rows: list[LeaderboardRow] = []
    for s in sums:
        org_user = org_users[s["org_user"]]
        user = org_user.user
        rows.append(
            LeaderboardRow(
                org_user_pk=s["org_user"],
                user_pk=user.pk,
                username=user.username,
                nickname=user.nickname,
                discordNickname=first_name(user.discordNickname),
                guildNickname=first_name(org_user.guild_nickname),
                avatarUrl=user.avatarUrl,
                points=s["total"],
                entries=s["entries"],
            )
        )
    return rows


def _sum(qs: QuerySet[ContributionEntry]) -> int:
    return qs.aggregate(total=Sum("points"))["total"] or 0


def member_entries(org_user: OrgUser, period: Period) -> QuerySet[ContributionEntry]:
    return (
        ledger.in_period(
            ContributionEntry.objects.nocache().filter(org_user=org_user), period
        )
        .select_related("event")
        .order_by("-occurred_at", "-pk")
    )


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


MAX_MONTHS = 120


def member_monthly(
    org_user: OrgUser, *, months: int = 12, now: datetime | None = None
) -> list[MonthPoints]:
    months = max(1, min(months, MAX_MONTHS))
    tz = resolve_org_tz(org_user.organization)
    local_now = (now or timezone.now()).astimezone(tz)
    index = local_now.year * 12 + local_now.month - 1
    first = index - months + 1
    keys = [_month_key(i // 12, i % 12 + 1) for i in range(first, index + 1)]
    start = month_period(tz, first // 12, first % 12 + 1).start
    end = month_period(tz, local_now.year, local_now.month).end
    buckets: defaultdict[str, int] = defaultdict(int)
    for occurred_at, points in (
        ContributionEntry.objects.nocache()
        .filter(org_user=org_user, occurred_at__gte=start, occurred_at__lt=end)
        .values_list("occurred_at", "points")
    ):
        local = occurred_at.astimezone(tz)
        buckets[_month_key(local.year, local.month)] += points
    return [MonthPoints(month=key, points=buckets.get(key, 0)) for key in keys]


def member_totals(org_user: OrgUser, *, now: datetime | None = None) -> MemberTotals:
    tz = resolve_org_tz(org_user.organization)
    local_now = (now or timezone.now()).astimezone(tz)
    this_month = month_period(tz, local_now.year, local_now.month)
    qs = ContributionEntry.objects.nocache().filter(org_user=org_user)
    return MemberTotals(
        all_time=_sum(qs),
        this_month=_sum(ledger.in_period(qs, this_month)),
    )
