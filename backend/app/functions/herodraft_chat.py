"""HeroDraft chat rules: viewer resolution, tenure, parsing and visibility."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from app.models import (
    CustomUser,
    DraftTeam,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    Team,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

ChatRole = Literal["member", "spectator", "ambiguous"]
ChatChannel = Literal["team", "all"]

HISTORY_LIMIT = 100

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
        HeroDraftChatMessage.objects.filter(draft_id=draft_id)
        .filter(visible)
        .select_related("sender__base_profile")
        .order_by("-id")[:limit]
    )
    rows.reverse()
    return [serialize_message(m) for m in rows]
