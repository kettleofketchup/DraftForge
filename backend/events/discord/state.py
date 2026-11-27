"""In-process reads of the signup list and Discord state the internal API serves."""

from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q, QuerySet

from app.auth import InternalServiceUser
from discordbot.models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)
from discordbot.schemas import DiscordEventStateSchema
from events.models import EventSignup
from events.schemas import EventSignupSchema
from events.serializers import EventSignupSerializer
from user.querysets import with_user_profiles


@dataclass(frozen=True)
class _ServiceRequest:
    user: InternalServiceUser = field(default_factory=InternalServiceUser)


def signup_list_queryset(
    event_id: int | str | None, *, for_list: bool
) -> QuerySet[EventSignup]:
    qs = with_user_profiles(
        EventSignup.objects.select_related(
            "event__tournament__league__organization", "event_team"
        ),
        "user",
        steam_verified_org=True,
    )
    if event_id:
        qs = qs.filter(event_id=event_id)
    if for_list:
        qs = qs.annotate_line_rank()
    return qs


def load_signups_for_embed(event_id: int) -> list[EventSignupSchema]:
    qs = signup_list_queryset(event_id, for_list=True)
    rows = EventSignupSerializer(
        qs, many=True, context={"request": _ServiceRequest()}
    ).data
    return [EventSignupSchema.model_validate(row) for row in rows]


def load_discord_event_state(event_id: int) -> DiscordEventStateSchema:
    result: dict[str, object] = {
        "has_discord_event": False,
        "scheduled_event_id": None,
        "signup_posted": False,
        "fired_actions": [],
        "has_dms": False,
    }

    de = DiscordEvent.objects.filter(event_id=event_id).first()
    if de is not None:
        result["has_discord_event"] = True
        result["discord_event_pk"] = de.pk
        result["scheduled_event_id"] = de.scheduled_event_id or None
        result["fired_actions"] = list(
            DiscordEventLog.objects.filter(discord_event=de, success=True).values_list(
                "action", flat=True
            )
        )
        result["has_dms"] = DiscordEventDM.objects.filter(discord_event=de).exists()

    signup_msg = DiscordEventMsgSignup.objects.filter(
        event_id=event_id, has_posted=True
    ).first()
    result["signup_posted"] = signup_msg is not None
    if signup_msg:
        result["signup_message_id"] = signup_msg.message_id
        result["signup_channel_id"] = signup_msg.channel_id
        result["signup_thread_id"] = signup_msg.thread_id
        # Legacy rows store "" (unset); workers fall back to a thread heuristic.
        result["signup_channel_type"] = signup_msg.channel_type or None

    return DiscordEventStateSchema.model_validate(result)


def message_log_exists(source: str, source_id: int | str) -> bool:
    return (
        DiscordMessageLog.objects.filter(source=source, source_id=source_id)
        .filter(Q(success__isnull=True) | Q(success=True))
        .exists()
    )


def latest_message_log_discord_id(source: str, source_id: int | str) -> str | None:
    return (
        DiscordMessageLog.objects.filter(
            source=source, source_id=source_id, success=True
        )
        .order_by("-created_at")
        .values_list("discord_message_id", flat=True)
        .first()
    )


def latest_message_log_embed_data(
    source: str, source_id: int | str
) -> dict[str, Any] | None:
    data = (
        DiscordMessageLog.objects.filter(
            source=source, source_id=source_id, success=True
        )
        .order_by("-created_at")
        .values_list("embed_data", flat=True)
        .first()
    )
    return data if isinstance(data, dict) else None
