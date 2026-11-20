"""HeroDraft chat rules: viewer resolution, tenure, parsing, posting and visibility."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import redis
from asgiref.sync import async_to_sync
from channels import layers
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from app.models import CustomUser, Team
from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from draft.models import (
    DraftTeam,
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    HeroDraftState,
)
from draft.services.heroes import get_available_heroes
from telemetry.logging import get_logger

log = get_logger(__name__)

ChatRole = Literal["member", "spectator", "ambiguous"]
ChatChannel = Literal["team", "all"]

ChatErrorCode = Literal[
    "not_participant",
    "ambiguous_team",
    "empty",
    "too_long",
    "rate_limited",
    "draft_closed",
    "draft_inactive",
    "hero_unavailable",
    "bad_request",
    "unavailable",
]

HISTORY_LIMIT = 100
MAX_BODY_LENGTH = 500
RATE_LIMIT_MAX = 8
RATE_LIMIT_WINDOW_S = 10
REJECT_LOG_MAX = 8
REJECT_LOG_WINDOW_S = 10.0

_CLOSED_STATES = frozenset({HeroDraftState.COMPLETED, HeroDraftState.ABANDONED})
_SUGGESTION_KINDS = frozenset(
    {HeroDraftChatMessage.Kind.SUGGEST_PICK, HeroDraftChatMessage.Kind.SUGGEST_BAN}
)

_NEWLINES = re.compile(r"[\r\n]")
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f]")
_ALL_PREFIX = re.compile(r"^/all(?:[ \t]+|$)", re.IGNORECASE)
_TRIM = " \t"


@dataclass(frozen=True)
class ChatViewer:
    user_id: int | None
    team_id: int | None
    role: ChatRole
    joined_at: datetime | None

    @property
    def can_post_team(self) -> bool:
        return self.role == "member"

    @property
    def can_post_all(self) -> bool:
        return self.role == "member"

    def as_payload(self) -> dict[str, object]:
        return {
            "role": self.role,
            "team_id": self.team_id,
            "can_post_team": self.can_post_team,
            "can_post_all": self.can_post_all,
        }


SPECTATOR = ChatViewer(user_id=None, team_id=None, role="spectator", joined_at=None)


def normalize_chat_text(raw: str) -> str:
    return _CONTROL.sub("", _NEWLINES.sub(" ", raw))


def parse_composer(raw: str) -> tuple[ChatChannel, str]:
    text = normalize_chat_text(raw).lstrip(_TRIM)
    match = _ALL_PREFIX.match(text)
    if match:
        return "all", text[match.end() :].strip(_TRIM)
    return "team", text.strip(_TRIM)


def team_group_name(draft_id: int, team_id: int) -> str:
    return f"herodraft_{draft_id}_team_{team_id}"


def _open_row(draft_id: int, user_id: int) -> HeroDraftChatMembership | None:
    return (
        HeroDraftChatMembership.objects.select_for_update()
        .filter(draft_id=draft_id, user_id=user_id, left_at__isnull=True)
        .first()
    )


def open_membership(
    draft_id: int, team_id: int, user_id: int, joined_at: datetime
) -> None:
    with transaction.atomic():
        row = _open_row(draft_id, user_id)
        if row is not None:
            if row.team_id == team_id:
                return
            row.left_at = joined_at
            row.save(update_fields=["left_at"])
        try:
            with transaction.atomic():
                HeroDraftChatMembership.objects.create(
                    draft_id=draft_id,
                    team_id=team_id,
                    user_id=user_id,
                    joined_at=joined_at,
                )
        except IntegrityError:
            log.warning(
                "herodraft_chat_membership_open_race",
                system="herodraft",
                subsystem="chat",
                draft_id=draft_id,
                user_id=user_id,
            )


def close_membership(
    draft_id: int,
    user_id: int,
    *,
    team_id: int | None = None,
    at: datetime | None = None,
) -> None:
    rows = HeroDraftChatMembership.objects.filter(
        draft_id=draft_id, user_id=user_id, left_at__isnull=True
    )
    if team_id is not None:
        rows = rows.filter(team_id=team_id)
    rows.update(left_at=at or timezone.now())


def _member_team_ids(draft_id: int, user_id: int) -> list[int]:
    return list(
        Team.objects.nocache()
        .filter(hero_draft_teams__draft_id=draft_id)
        .filter(Q(captain_id=user_id) | Q(members=user_id))
        .values_list("pk", flat=True)
        .distinct()
    )


def _active_draft_teams(team_ids: Iterable[int]) -> dict[int, list[int]]:
    wanted = set(team_ids)
    if not wanted:
        return {}
    by_draft: dict[int, list[int]] = {}
    pairs = (
        DraftTeam.objects.nocache()
        .filter(tournament_team_id__in=wanted)
        .exclude(draft__state__in=_CLOSED_STATES)
        .order_by("draft_id", "tournament_team_id")
        .values_list("draft_id", "tournament_team_id")
    )
    for draft_id, team_id in pairs:
        teams = by_draft.setdefault(draft_id, [])
        if team_id not in teams:
            teams.append(team_id)
    return by_draft


def active_drafts_for_teams(team_ids: Iterable[int]) -> list[int]:
    return list(_active_draft_teams(team_ids))


def _team_rosters(team_ids: Iterable[int]) -> dict[int, set[int]]:
    rosters: dict[int, set[int]] = {}
    teams = Team.objects.nocache().filter(pk__in=list(team_ids))
    for team_id, captain_id in teams.values_list("pk", "captain_id"):
        rosters[team_id] = {captain_id} if captain_id is not None else set()
    for team_id, user_id in Team.members.through.objects.filter(
        team_id__in=list(rosters)
    ).values_list("team_id", "customuser_id"):
        rosters[team_id].add(user_id)
    return rosters


def draft_roster_user_ids(draft_id: int) -> set[int]:
    team_ids = (
        DraftTeam.objects.nocache()
        .filter(draft_id=draft_id)
        .values_list("tournament_team_id", flat=True)
    )
    users: set[int] = set()
    for roster in _team_rosters(list(team_ids)).values():
        users |= roster
    return users


CHAT_RESYNC_EVENTS = frozenset({"team_changed", "draft_reset"})


def chat_roster_field(draft_id: int, event_type: str | None) -> dict[str, list[int]]:
    if event_type not in CHAT_RESYNC_EVENTS:
        return {}
    try:
        return {"chat_roster": sorted(draft_roster_user_ids(draft_id))}
    except Exception:
        log.warning(
            "herodraft_chat_roster_failed",
            system="herodraft",
            subsystem="chat",
            draft_id=draft_id,
            event_type=event_type,
            exc_info=True,
        )
        return {}


def _seed_teams(draft_id: int, team_ids: Iterable[int], joined_at: datetime) -> None:
    seeded = set(team_ids)
    if not seeded:
        return
    current = set(
        DraftTeam.objects.nocache()
        .filter(draft_id=draft_id)
        .values_list("tournament_team_id", flat=True)
    )
    rosters = _team_rosters(current | seeded)
    for team_id in sorted(seeded & set(rosters)):
        others: set[int] = set()
        for other_id, user_ids in rosters.items():
            if other_id != team_id:
                others |= user_ids
        for user_id in sorted(rosters[team_id] - others):
            open_membership(draft_id, team_id, user_id, joined_at)


def seed_draft_memberships(draft: HeroDraft) -> None:
    team_ids = (
        DraftTeam.objects.nocache()
        .filter(draft=draft)
        .values_list("tournament_team_id", flat=True)
    )
    _seed_teams(draft.pk, list(team_ids), draft.created_at)


def reset_draft_chat(draft: HeroDraft) -> None:
    with transaction.atomic():
        HeroDraftChatMessage.objects.filter(draft=draft).delete()
        HeroDraftChatMembership.objects.filter(draft=draft).delete()
        seed_draft_memberships(draft)


def reconcile_draft_memberships(draft_id: int, at: datetime | None = None) -> None:
    now = at or timezone.now()
    current = set(
        DraftTeam.objects.nocache()
        .filter(draft_id=draft_id)
        .values_list("tournament_team_id", flat=True)
    )
    owner: dict[int, int | None] = {}
    for team_id, user_ids in _team_rosters(current).items():
        for user_id in user_ids:
            owner[user_id] = None if user_id in owner else team_id
    with transaction.atomic():
        open_rows = HeroDraftChatMembership.objects.filter(
            draft_id=draft_id, left_at__isnull=True
        )
        stale = [
            pk
            for pk, user_id, team_id in open_rows.values_list(
                "pk", "user_id", "team_id"
            )
            if owner.get(user_id) != team_id
        ]
        if stale:
            HeroDraftChatMembership.objects.filter(pk__in=stale).update(left_at=now)
        _seed_teams(draft_id, current, now)


def delete_team_chat(team_ids: Iterable[int]) -> None:
    ids = list(team_ids)
    if not ids:
        return
    HeroDraftChatMessage.objects.filter(team_id__in=ids).delete()
    HeroDraftChatMembership.objects.filter(team_id__in=ids).delete()


def repoint_draft_memberships(
    draft_id: int, prior_team_ids: Iterable[int], new_team_ids: Iterable[int]
) -> None:
    prior = set(prior_team_ids)
    new = set(new_team_ids)
    now = timezone.now()
    HeroDraftChatMembership.objects.filter(
        draft_id=draft_id, team_id__in=prior - new, left_at__isnull=True
    ).update(left_at=now)
    _seed_teams(draft_id, new - prior, now)


def repoint_chat_attribution(drop: CustomUser, keep: CustomUser) -> int:
    HeroDraftChatMembership.objects.filter(
        user=drop,
        left_at__isnull=True,
        draft_id__in=HeroDraftChatMembership.objects.filter(
            user=keep, left_at__isnull=True
        ).values("draft_id"),
    ).update(left_at=timezone.now())
    return HeroDraftChatMessage.objects.filter(sender=drop).update(
        sender=keep
    ) + HeroDraftChatMembership.objects.filter(user=drop).update(user=keep)


def _sync_user_tenure(draft_id: int, user_ids: Iterable[int], at: datetime) -> None:
    for user_id in user_ids:
        team_ids = _member_team_ids(draft_id, user_id)
        if len(team_ids) == 1:
            open_membership(draft_id, team_ids[0], user_id, at)
        else:
            close_membership(draft_id, user_id, at=at)


def broadcast_chat_resync(
    draft_id: int, team_ids: list[int], user_ids: list[int]
) -> None:
    try:
        channel_layer = layers.get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"herodraft_{draft_id}",
            {
                "type": "herodraft.chat_resync",
                "team_ids": team_ids,
                "user_ids": user_ids,
            },
        )
    except Exception:
        log.warning(
            "herodraft_chat_resync_broadcast_failed",
            system="herodraft",
            subsystem="chat",
            draft_id=draft_id,
            exc_info=True,
        )


def apply_roster_tenure(team_ids: list[int], user_ids: list[int]) -> None:
    now = timezone.now()
    for draft_id, draft_team_ids in _active_draft_teams(team_ids).items():
        _sync_user_tenure(draft_id, user_ids, now)
        broadcast_chat_resync(draft_id, draft_team_ids, user_ids)


def schedule_roster_tenure(team_ids: Iterable[int], user_ids: Iterable[int]) -> None:
    teams = sorted(set(team_ids))
    users = sorted(set(user_ids))
    if not teams or not users:
        return
    transaction.on_commit(lambda: apply_roster_tenure(teams, users), robust=True)


def apply_captain_tenure(
    team_id: int, draft_ids: list[int], old_id: int | None, new_id: int
) -> None:
    now = timezone.now()
    user_ids = [uid for uid in (old_id, new_id) if uid is not None]
    active = set(active_drafts_for_teams([team_id]))
    for draft_id in draft_ids:
        if draft_id not in active:
            continue
        _sync_user_tenure(draft_id, user_ids, now)
        broadcast_chat_resync(draft_id, [team_id], user_ids)


def resolve_chat_viewer(
    draft_id: int, user: CustomUser | AnonymousUser | None
) -> ChatViewer:
    if user is None or not user.is_authenticated or user.pk is None:
        return SPECTATOR
    uid: int = user.pk
    team_ids = _member_team_ids(draft_id, uid)

    if len(team_ids) != 1:
        close_membership(draft_id, uid)
        if team_ids:
            log.warning(
                "herodraft_chat_ambiguous_membership",
                system="herodraft",
                subsystem="chat",
                draft_id=draft_id,
                user_id=uid,
                team_count=len(team_ids),
            )
            return ChatViewer(
                user_id=uid, team_id=None, role="ambiguous", joined_at=None
            )
        return ChatViewer(user_id=uid, team_id=None, role="spectator", joined_at=None)

    team_id = team_ids[0]
    open_membership(draft_id, team_id, uid, timezone.now())
    row = (
        HeroDraftChatMembership.objects.filter(
            draft_id=draft_id, user_id=uid, left_at__isnull=True
        )
        .only("team_id", "joined_at")
        .first()
    )
    if row is None or row.team_id != team_id:
        return ChatViewer(user_id=uid, team_id=None, role="spectator", joined_at=None)
    return ChatViewer(
        user_id=uid, team_id=team_id, role="member", joined_at=row.joined_at
    )


def _sender_payload(user: CustomUser) -> dict[str, Any]:
    return {
        "pk": user.pk,
        "username": user.username,
        "nickname": user.nickname,
        "avatarUrl": user.avatarUrl,
        "discordId": user.discordId,
    }


def serialize_message(msg: HeroDraftChatMessage) -> dict[str, Any]:
    return {
        "id": str(msg.public_id),
        "channel": msg.channel,
        "team_id": msg.team_id,
        "kind": msg.kind,
        "hero_id": msg.hero_id,
        "body": msg.body,
        "created_at": msg.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "sender": _sender_payload(msg.sender),
    }


def visible_messages(
    draft_id: int, viewer: ChatViewer, limit: int = HISTORY_LIMIT
) -> list[dict[str, Any]]:
    visible = Q(channel=HeroDraftChatMessage.Channel.ALL)
    if (
        viewer.role == "member"
        and viewer.team_id is not None
        and viewer.joined_at is not None
    ):
        current_team_ids = set(
            DraftTeam.objects.nocache()
            .filter(draft_id=draft_id)
            .values_list("tournament_team_id", flat=True)
        )
        if viewer.team_id in current_team_ids:
            visible |= Q(
                channel=HeroDraftChatMessage.Channel.TEAM,
                team_id=viewer.team_id,
                created_at__gte=viewer.joined_at,
            )
    rows = list(
        HeroDraftChatMessage.objects.nocache()
        .filter(draft_id=draft_id)
        .filter(visible)
        .select_related("sender__base_profile")
        .order_by("-id")[:limit]
    )
    rows.reverse()
    return [serialize_message(m) for m in rows]


class ChatError(Exception):
    def __init__(self, code: ChatErrorCode) -> None:
        super().__init__(code)
        self.code: ChatErrorCode = code


@dataclass(frozen=True)
class PostResult:
    viewer: ChatViewer
    channel: ChatChannel
    team_id: int | None
    message: dict[str, Any]


def rate_limit_key(draft_id: int, user_id: int) -> str:
    return namespaced_key(f"herodraft:chat:rate:{draft_id}:{user_id}")


def check_rate_limit(draft_id: int, user_id: int) -> None:
    key = rate_limit_key(draft_id, user_id)
    try:
        pipe = get_redis_client().pipeline(transaction=True)
        pipe.set(key, 0, ex=RATE_LIMIT_WINDOW_S, nx=True)
        pipe.incr(key)
        _, count = pipe.execute()
    except redis.RedisError:
        log.warning(
            "herodraft_chat_rate_limit_redis_unavailable",
            system="herodraft",
            subsystem="chat",
            draft_id=draft_id,
            user_id=user_id,
            exc_info=True,
        )
        raise ChatError("unavailable") from None
    if int(count) > RATE_LIMIT_MAX:
        raise ChatError("rate_limited")


def authorize_post(viewer: ChatViewer) -> None:
    if viewer.role == "ambiguous":
        raise ChatError("ambiguous_team")
    if viewer.role != "member" or viewer.team_id is None:
        raise ChatError("not_participant")


def _authorize_sender(user: CustomUser, viewer: ChatViewer) -> None:
    authorize_post(viewer)
    if user.pk is None or viewer.user_id != user.pk:
        raise ChatError("not_participant")


def _open_draft(draft_id: int) -> HeroDraft:
    draft = HeroDraft.objects.nocache().filter(pk=draft_id).first()
    if draft is None or draft.state in _CLOSED_STATES:
        raise ChatError("draft_closed")
    return draft


def _persist(
    draft_id: int,
    user: CustomUser,
    viewer: ChatViewer,
    channel: ChatChannel,
    kind: str,
    body: str,
    hero_id: int | None,
) -> PostResult:
    team_id = viewer.team_id if channel == "team" else None
    msg = HeroDraftChatMessage.objects.create(
        draft_id=draft_id,
        channel=channel,
        team_id=team_id,
        sender=user,
        kind=kind,
        hero_id=hero_id,
        body=body,
    )
    return PostResult(
        viewer=viewer,
        channel=channel,
        team_id=team_id,
        message=serialize_message(msg),
    )


def post_text(
    draft_id: int, user: CustomUser, raw: object, viewer: ChatViewer
) -> PostResult:
    _authorize_sender(user, viewer)
    _open_draft(draft_id)
    if not isinstance(raw, str):
        raise ChatError("bad_request")
    channel, body = parse_composer(raw)
    if not body:
        raise ChatError("empty")
    if len(body) > MAX_BODY_LENGTH:
        raise ChatError("too_long")
    return _persist(
        draft_id, user, viewer, channel, HeroDraftChatMessage.Kind.TEXT, body, None
    )


def post_suggestion(
    draft_id: int,
    user: CustomUser,
    kind: object,
    hero_id: object,
    viewer: ChatViewer,
) -> PostResult:
    _authorize_sender(user, viewer)
    draft = _open_draft(draft_id)
    if draft.state != HeroDraftState.DRAFTING:
        raise ChatError("draft_inactive")
    if not isinstance(kind, str) or kind not in _SUGGESTION_KINDS:
        raise ChatError("bad_request")
    if (
        not isinstance(hero_id, int)
        or isinstance(hero_id, bool)
        or hero_id not in get_available_heroes(draft)
    ):
        raise ChatError("hero_unavailable")
    return _persist(draft_id, user, viewer, "team", kind, "", hero_id)
