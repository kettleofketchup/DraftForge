from datetime import datetime
from typing import Final, TypedDict

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from app.models import CustomUser, Organization, Tournament
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.models_promotion import PromoSend
from org.promotion.render import player_name
from user.querysets import with_user_profiles

MAX_POOL_N: Final[int] = 10
DEFAULT_POOL_N: Final[int] = 3
MIN_POOL_N: Final[int] = 1

ACTIVE_SIGNUP_EXCLUDED: Final[tuple[str, ...]] = (
    SignupStatus.REJECTED,
    SignupStatus.CANCELLED,
)


class LastMessaged(TypedDict):
    send_id: int
    by: str | None
    sent_at: datetime
    can_undo: bool


class CandidateRow(TypedDict):
    user_pk: int
    username: str
    nickname: str | None
    discordUsername: str | None
    discordId: str | None
    avatarUrl: str | None
    recent_count: int
    last_messaged: LastMessaged | None
    earning_send_exists: bool
    signed_up: bool


def clamp_pool_n(value: str | int | None) -> int:
    if value is None:
        return DEFAULT_POOL_N
    try:
        n = int(value)
    except ValueError:
        return DEFAULT_POOL_N
    return max(MIN_POOL_N, min(MAX_POOL_N, n))


def recent_org_tournaments(
    org: Organization, *, exclude_event: Event, n: int
) -> list[int]:
    qs = (
        Tournament.objects.nocache()
        .filter(
            Q(league__organization=org) | Q(source_event__organization=org),
            date_played__lte=timezone.now(),
        )
        .exclude(source_event__state=EventState.CANCELLED)
    )
    if exclude_event.tournament_id is not None:
        qs = qs.exclude(pk=exclude_event.tournament_id)
    return list(
        qs.distinct().order_by("-date_played", "-pk").values_list("pk", flat=True)[:n]
    )


def candidate_pool(
    org: Organization, event: Event, *, n: int, sender: CustomUser
) -> QuerySet[CustomUser]:
    tournament_ids = recent_org_tournaments(org, exclude_event=event, n=n)
    qs = (
        CustomUser.objects.filter(
            tournaments__pk__in=tournament_ids, discordId__isnull=False
        )
        .exclude(discordId="")
        .exclude(pk=sender.pk)
        .annotate(recent_count=Count("tournaments", distinct=True))
    )
    return with_user_profiles(qs)


def candidates(
    org: Organization,
    event: Event,
    *,
    n: int,
    sender: CustomUser,
    hide_signed_up: bool = True,
    hide_messaged: bool = True,
    q: str = "",
) -> list[CandidateRow]:
    active_signups = (
        EventSignup.objects.nocache()
        .filter(event=event)
        .exclude(status__in=ACTIVE_SIGNUP_EXCLUDED)
    )
    event_sends = PromoSend.objects.filter(event=event, recipient__isnull=False)

    qs = candidate_pool(org, event, n=n, sender=sender)
    if hide_signed_up:
        qs = qs.exclude(pk__in=active_signups.values("user_id"))
    if hide_messaged:
        qs = qs.exclude(pk__in=event_sends.values("recipient_id"))
    term = q.strip()
    if term:
        qs = qs.filter(
            Q(username__icontains=term)
            | Q(base_profile__nickname__icontains=term)
            | Q(discordUsername__icontains=term)
            | Q(discordNickname__icontains=term)
            | Q(guildNickname__icontains=term)
        )
    users = list(qs.order_by("-recent_count", "username", "pk"))
    user_pks = [u.pk for u in users]

    signed_up = set(
        active_signups.filter(user_id__in=user_pks).values_list("user_id", flat=True)
    )
    latest: dict[int, PromoSend] = {}
    earning: set[int] = set()
    for send in with_user_profiles(
        event_sends.filter(recipient_id__in=user_pks), "sender"
    ).order_by("-sent_at", "-pk"):
        latest.setdefault(send.recipient_id, send)
        if send.earns_points:
            earning.add(send.recipient_id)

    rows: list[CandidateRow] = []
    for user in users:
        send = latest.get(user.pk)
        last_messaged: LastMessaged | None = None
        if send is not None:
            last_messaged = {
                "send_id": send.pk,
                "by": player_name(send.sender) if send.sender else None,
                "sent_at": send.sent_at,
                "can_undo": False,
            }
        rows.append(
            {
                "user_pk": user.pk,
                "username": user.username,
                "nickname": user.nickname,
                "discordUsername": user.discordUsername,
                "discordId": user.discordId,
                "avatarUrl": user.avatarUrl,
                "recent_count": user.recent_count,
                "last_messaged": last_messaged,
                "earning_send_exists": user.pk in earning,
                "signed_up": user.pk in signed_up,
            }
        )
    return rows


def in_pool(org: Organization, event: Event, recipient: CustomUser) -> bool:
    tournament_ids = recent_org_tournaments(org, exclude_event=event, n=MAX_POOL_N)
    return (
        CustomUser.objects.nocache()
        .filter(
            pk=recipient.pk,
            tournaments__pk__in=tournament_ids,
            discordId__isnull=False,
        )
        .exclude(discordId="")
        .exists()
    )
