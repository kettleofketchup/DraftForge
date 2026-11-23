from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final, TypedDict

from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from app.models import CustomUser, PositionsModel, Tournament
from discordbot.services.discord_members import (
    DiscordMembersFetchError,
    get_discord_members_data,
)
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.display_names import guild_nicknames
from org.models import Organization, OrgUser
from org.models_promotion import PromoSend
from org.promotion.render import player_name
from org.user_search import user_name_q
from telemetry.logging import get_logger
from user.querysets import with_user_profiles

log = get_logger(__name__)

MAX_POOL_N: Final[int] = 10
DEFAULT_POOL_N: Final[int] = 3
MIN_POOL_N: Final[int] = 1

MAX_DAYS: Final[int] = 90
DEFAULT_DAYS: Final[int] = 30
MIN_DAYS: Final[int] = 1
MAX_DISCORD_ROWS: Final[int] = 200

DECLINED_STATUSES: Final[tuple[str, ...]] = (
    SignupStatus.REJECTED,
    SignupStatus.CANCELLED,
    SignupStatus.DROPPED,
)


class CandidateSource(StrEnum):
    RECENT = "recent"
    ACTIVE = "active"
    DISCORD = "discord"


class LastMessaged(TypedDict):
    send_id: int
    by: str | None
    sent_at: datetime
    can_undo: bool


class CandidateRow(TypedDict):
    user_pk: int | None
    username: str
    nickname: str | None
    discordUsername: str | None
    discordNickname: str | None
    guildNickname: str | None
    discordId: str | None
    avatarUrl: str | None
    recent_count: int | None
    last_active_at: datetime | None
    discord_joined_at: datetime | None
    last_messaged: LastMessaged | None
    earning_send_exists: bool
    signed_up: bool


class GuildJoiner(TypedDict):
    member: dict[str, Any]
    joined_at: datetime


def _clamp(value: str | int | None, *, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except ValueError:
        return default
    return max(low, min(high, n))


def clamp_pool_n(value: str | int | None) -> int:
    return _clamp(value, default=DEFAULT_POOL_N, low=MIN_POOL_N, high=MAX_POOL_N)


def clamp_days(value: str | int | None) -> int:
    return _clamp(value, default=DEFAULT_DAYS, low=MIN_DAYS, high=MAX_DAYS)


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


def _with_discord(qs: QuerySet[CustomUser]) -> QuerySet[CustomUser]:
    return qs.filter(discordId__isnull=False).exclude(discordId="")


def _with_guild_nickname(
    qs: QuerySet[CustomUser], org: Organization
) -> QuerySet[CustomUser]:
    return qs.annotate(
        org_guild_nickname=Subquery(
            OrgUser.objects.filter(user=OuterRef("pk"), organization=org).values(
                "guild_nickname"
            )[:1]
        )
    )


def candidate_pool(
    org: Organization, event: Event, *, n: int, sender: CustomUser
) -> QuerySet[CustomUser]:
    tournament_ids = recent_org_tournaments(org, exclude_event=event, n=n)
    qs = _with_discord(
        CustomUser.objects.filter(tournaments__pk__in=tournament_ids)
    ).exclude(pk=sender.pk)
    qs = _with_guild_nickname(
        qs.annotate(recent_count=Count("tournaments", distinct=True)), org
    )
    return with_user_profiles(qs)


def active_pool(org: Organization, event: Event, *, days: int) -> QuerySet[CustomUser]:
    """Users who signed up for, or played in, any other org event within ``days``."""
    now = timezone.now()
    since = now - timedelta(days=days)
    last_signup = (
        EventSignup.objects.filter(
            user=OuterRef("pk"),
            event__organization=org,
            signed_up_at__gte=since,
        )
        .exclude(event=event)
        .order_by("-signed_up_at")
        .values("signed_up_at")[:1]
    )
    played = Tournament.objects.filter(
        Q(league__organization=org) | Q(source_event__organization=org),
        users=OuterRef("pk"),
        date_played__gte=since,
        date_played__lte=now,
    )
    if event.tournament_id is not None:
        played = played.exclude(pk=event.tournament_id)
    last_played = played.order_by("-date_played").values("date_played")[:1]
    qs = (
        _with_discord(CustomUser.objects.all())
        .annotate(
            last_signup_at=Subquery(last_signup),
            last_played_at=Subquery(last_played),
        )
        .annotate(
            last_active_at=Greatest(
                Coalesce("last_signup_at", "last_played_at"),
                Coalesce("last_played_at", "last_signup_at"),
            )
        )
        .filter(last_active_at__isnull=False)
    )
    return with_user_profiles(_with_guild_nickname(qs, org))


def _parse_joined_at(member: dict[str, Any]) -> datetime | None:
    raw = member.get("joined_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def guild_members(org: Organization) -> list[dict[str, Any]]:
    if not org.discord_server_id:
        return []
    try:
        return get_discord_members_data(guild_id=org.discord_server_id)
    except DiscordMembersFetchError as exc:
        log.warning(
            "promo_guild_members_unavailable",
            system="org",
            subsystem="promotion",
            org_id=org.pk,
            error=str(exc),
        )
        return []


def recent_guild_joiners(org: Organization, *, days: int) -> list[GuildJoiner]:
    """Human guild members who joined within ``days``, newest first."""
    since = timezone.now() - timedelta(days=days)
    joiners: list[GuildJoiner] = []
    for member in guild_members(org):
        user = member.get("user") or {}
        if user.get("bot") or not user.get("id"):
            continue
        joined_at = _parse_joined_at(member)
        if joined_at is not None and joined_at >= since:
            joiners.append({"member": member, "joined_at": joined_at})
    joiners.sort(key=lambda j: j["joined_at"], reverse=True)
    return joiners


def find_guild_joiner(
    org: Organization, discord_id: str, *, days: int = MAX_DAYS
) -> GuildJoiner | None:
    for joiner in recent_guild_joiners(org, days=days):
        if joiner["member"]["user"]["id"] == discord_id:
            return joiner
    return None


def _member_matches(member: dict[str, Any], term: str) -> bool:
    user = member.get("user") or {}
    names = (
        user.get("username"),
        user.get("global_name"),
        member.get("nick"),
    )
    needle = term.casefold()
    return any(name and needle in name.casefold() for name in names)


def _unsaved_user(member: dict[str, Any]) -> CustomUser:
    return CustomUser().createFromDiscordData(member)


def user_for_guild_member(member: dict[str, Any]) -> CustomUser:
    """Return the account linked to a guild member, creating one if none exists."""
    discord_id = member["user"]["id"]
    existing = CustomUser.objects.filter(discordId=discord_id).first()
    if existing is not None:
        return existing
    user = CustomUser(positions=PositionsModel.objects.create())
    user.createFromDiscordData(member)
    user.save()
    return user


def _member_row(joiner: GuildJoiner) -> CandidateRow:
    member = joiner["member"]
    user = _unsaved_user(member)
    return {
        "user_pk": None,
        "username": user.username,
        "nickname": user.nickname,
        "discordUsername": user.discordUsername,
        "discordNickname": user.discordNickname,
        "guildNickname": member.get("nick"),
        "discordId": user.discordId,
        "avatarUrl": user.avatarUrl,
        "recent_count": None,
        "last_active_at": None,
        "discord_joined_at": joiner["joined_at"],
        "last_messaged": None,
        "earning_send_exists": False,
        "signed_up": False,
    }


def _pool_users(
    org: Organization,
    event: Event,
    *,
    source: CandidateSource,
    n: int,
    days: int,
    sender: CustomUser,
) -> QuerySet[CustomUser]:
    if source == CandidateSource.RECENT:
        return candidate_pool(org, event, n=n, sender=sender).order_by(
            "-recent_count", "username", "pk"
        )
    if source == CandidateSource.ACTIVE:
        return (
            active_pool(org, event, days=days)
            .exclude(pk=sender.pk)
            .order_by("-last_active_at", "username", "pk")
        )
    raise ValueError(source)


def candidates(
    org: Organization,
    event: Event,
    *,
    n: int,
    sender: CustomUser,
    source: CandidateSource = CandidateSource.RECENT,
    days: int = DEFAULT_DAYS,
    hide_signed_up: bool = True,
    hide_messaged: bool = True,
    q: str = "",
) -> list[CandidateRow]:
    event_signups = EventSignup.objects.nocache().filter(event=event)
    active_signups = event_signups.exclude(status__in=DECLINED_STATUSES)
    declined = event_signups.filter(status__in=DECLINED_STATUSES)
    event_sends = PromoSend.objects.filter(event=event, recipient__isnull=False)
    term = q.strip()

    joiners: list[GuildJoiner] = []
    joined_at: dict[str, datetime] = {}
    if source == CandidateSource.DISCORD:
        joiners = [
            j
            for j in recent_guild_joiners(org, days=days)
            if j["member"]["user"]["id"] != sender.discordId
        ][:MAX_DISCORD_ROWS]
        joined_at = {j["member"]["user"]["id"]: j["joined_at"] for j in joiners}
        qs = with_user_profiles(
            _with_guild_nickname(
                CustomUser.objects.filter(discordId__in=list(joined_at)), org
            )
        ).exclude(pk=sender.pk)
    else:
        qs = _pool_users(org, event, source=source, n=n, days=days, sender=sender)

    qs = qs.exclude(pk__in=declined.values("user_id"))
    if hide_signed_up:
        qs = qs.exclude(pk__in=active_signups.values("user_id"))
    if hide_messaged:
        qs = qs.exclude(pk__in=event_sends.values("recipient_id"))
    if term:
        qs = qs.filter(user_name_q(term, org_id=org.pk))
    users = list(qs)
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

    sender_nicks = guild_nicknames(
        org.pk, {s.sender_id for s in latest.values() if s.sender_id is not None}
    )
    user_rows: dict[str, CandidateRow] = {}
    rows: list[CandidateRow] = []
    for user in users:
        send = latest.get(user.pk)
        last_messaged: LastMessaged | None = None
        if send is not None:
            last_messaged = {
                "send_id": send.pk,
                "by": (
                    player_name(send.sender, sender_nicks.get(send.sender_id))
                    if send.sender
                    else None
                ),
                "sent_at": send.sent_at,
                "can_undo": False,
            }
        row: CandidateRow = {
            "user_pk": user.pk,
            "username": user.username,
            "nickname": user.nickname,
            "discordUsername": user.discordUsername,
            "discordNickname": user.discordNickname,
            "guildNickname": user.org_guild_nickname,
            "discordId": user.discordId,
            "avatarUrl": user.avatarUrl,
            "recent_count": getattr(user, "recent_count", None),
            "last_active_at": getattr(user, "last_active_at", None),
            "discord_joined_at": joined_at.get(user.discordId or ""),
            "last_messaged": last_messaged,
            "earning_send_exists": user.pk in earning,
            "signed_up": user.pk in signed_up,
        }
        user_rows[user.discordId or ""] = row
        rows.append(row)

    if source != CandidateSource.DISCORD:
        return rows

    linked = set(
        CustomUser.objects.filter(discordId__in=list(joined_at)).values_list(
            "discordId", flat=True
        )
    )
    merged: list[CandidateRow] = []
    for joiner in joiners:
        discord_id = joiner["member"]["user"]["id"]
        if discord_id in user_rows:
            merged.append(user_rows[discord_id])
        elif discord_id not in linked and (
            not term or _member_matches(joiner["member"], term)
        ):
            merged.append(_member_row(joiner))
    return merged


def in_pool(org: Organization, event: Event, recipient: CustomUser) -> bool:
    if not recipient.discordId:
        return False
    tournament_ids = recent_org_tournaments(org, exclude_event=event, n=MAX_POOL_N)
    recent = CustomUser.objects.nocache().filter(
        pk=recipient.pk, tournaments__pk__in=tournament_ids
    )
    if recent.exists():
        return True
    if active_pool(org, event, days=MAX_DAYS).filter(pk=recipient.pk).exists():
        return True
    return find_guild_joiner(org, recipient.discordId) is not None
