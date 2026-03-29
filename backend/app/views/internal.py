"""Internal API endpoints for celery workers and Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
All cached model writes use invalidate_after_commit() for safety — this fires
immediately when called outside a transaction (Django autocommit mode), and
defers until commit when called inside @transaction.atomic.

Field whitelists on update endpoints prevent unintended field modifications.
"""

import logging

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit

logger = logging.getLogger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


def _validate_required(data, fields):
    """Return error Response if required fields are missing, else None."""
    missing = [f for f in fields if f not in data]
    if missing:
        return Response(
            {"error": f"Missing required fields: {missing}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


# ---------------------------------------------------------------------------
# DiscordMessageLog (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_message_log(request):
    """Create a DiscordMessageLog entry.

    For reminder-type sources, checks idempotency: if a successful log
    with the same source+source_id already exists, returns it instead
    of creating a duplicate.
    """
    from discordbot.models import DiscordMessageLog

    ALLOWED_FIELDS = {
        "channel_id",
        "embed_data",
        "source",
        "source_id",
        "discord_message_id",
        "status_code",
        "response_data",
        "success",
    }
    IDEMPOTENT_SOURCES = {
        "signup_reminder",
        "attendance_reminder",
        "profile_reminder",
    }
    err = _validate_required(
        request.data, ["channel_id", "source", "source_id", "embed_data"]
    )
    if err:
        return err
    data = {k: v for k, v in request.data.items() if k in ALLOWED_FIELDS}

    # Idempotency for reminder sources — prevent duplicate posts
    source = data.get("source")
    source_id = data.get("source_id")
    if source in IDEMPOTENT_SOURCES and source_id:
        existing = DiscordMessageLog.objects.filter(
            source=source, source_id=source_id, success=True
        ).first()
        if existing:
            return Response(
                {"id": existing.pk, "deduplicated": True},
                status=status.HTTP_200_OK,
            )

    entry = DiscordMessageLog.objects.create(**data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def check_message_log_exists(request):
    """Check if a successful DiscordMessageLog exists (for celery idempotency)."""
    from discordbot.models import DiscordMessageLog

    source = request.query_params.get("source")
    source_id = request.query_params.get("source_id")
    if not source or not source_id:
        return Response(
            {"error": "source and source_id required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    exists = DiscordMessageLog.objects.filter(
        source=source, source_id=source_id, success=True
    ).exists()
    return Response({"exists": exists})


# ---------------------------------------------------------------------------
# DiscordEventLog (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_event_log(request):
    """Create a DiscordEventLog audit entry."""
    from discordbot.models import DiscordEvent, DiscordEventLog

    err = _validate_required(
        request.data, ["discord_event_id", "action", "target_type"]
    )
    if err:
        return err
    EVENT_LOG_FIELDS = {
        "action",
        "target_type",
        "message_id",
        "status_code",
        "response_data",
        "success",
        "error_message",
    }
    data = {k: v for k, v in request.data.items() if k in EVENT_LOG_FIELDS}
    discord_event = DiscordEvent.objects.get(pk=request.data["discord_event_id"])
    entry = DiscordEventLog.objects.create(discord_event=discord_event, **data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# DiscordEvent (CACHED — invalidate after writes)
# ---------------------------------------------------------------------------

DISCORD_EVENT_UPDATE_FIELDS = {
    "scheduled_event_id",
    "signup_message_id",
    "announcement_id",
}


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_or_create_discord_event(request):
    """Get or create a DiscordEvent for an event."""
    from discordbot.models import DiscordEvent

    err = _validate_required(request.data, ["event_id"])
    if err:
        return err
    de, created = DiscordEvent.objects.get_or_create(
        event_id=request.data["event_id"],
        defaults={"guild_id": request.data.get("guild_id", "")},
    )
    if created:
        invalidate_after_commit(de)
    return Response(
        {"id": de.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_discord_event(request, pk):
    """Update DiscordEvent fields (whitelisted only)."""
    from discordbot.models import DiscordEvent

    de = DiscordEvent.objects.get(pk=pk)
    changed = False
    for field in DISCORD_EVENT_UPDATE_FIELDS:
        if field in request.data:
            setattr(de, field, request.data[field])
            changed = True
    if changed:
        de.save()
        invalidate_after_commit(de)
    return Response({"id": de.pk})


# ---------------------------------------------------------------------------
# DiscordEventMsgSignup (CACHED — invalidate after writes)
# ---------------------------------------------------------------------------

SIGNUP_MSG_UPDATE_FIELDS = {
    "message_id",
    "thread_id",
    "channel_type",
    "has_posted",
    "message_last_updated",
}


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_signup_message(request):
    """Create/update DiscordEventMsgSignup (whitelisted fields only)."""
    from discordbot.models import ChannelType, DiscordEventMsgSignup

    err = _validate_required(request.data, ["event_id", "channel_id"])
    if err:
        return err
    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgSignup.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field in SIGNUP_MSG_UPDATE_FIELDS:
        if field in data:
            setattr(msg, field, data[field])
    msg.save()
    invalidate_after_commit(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# DiscordEventMsgAnnouncement (CACHED — invalidate after writes)
# ---------------------------------------------------------------------------

ANNOUNCEMENT_UPDATE_FIELDS = {
    "message_id",
    "channel_type",
    "has_posted",
    "message_last_updated",
}


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_announcement(request):
    """Create/update DiscordEventMsgAnnouncement (whitelisted fields only)."""
    from discordbot.models import ChannelType, DiscordEventMsgAnnouncement

    err = _validate_required(request.data, ["event_id", "channel_id"])
    if err:
        return err
    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgAnnouncement.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field in ANNOUNCEMENT_UPDATE_FIELDS:
        if field in data:
            setattr(msg, field, data[field])
    msg.save()
    invalidate_after_commit(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# DiscordEventDM (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_event_dm(request):
    """Create DiscordEventDM record (crash-safe: create before send)."""
    from discordbot.models import DiscordEventDM

    DM_CREATE_FIELDS = {"discord_event", "org_user", "dm_type", "delivered"}
    err = _validate_required(request.data, ["discord_event", "org_user", "dm_type"])
    if err:
        return err
    data = {k: v for k, v in request.data.items() if k in DM_CREATE_FIELDS}
    dm = DiscordEventDM.objects.create(**data)
    return Response({"id": dm.pk}, status=status.HTTP_201_CREATED)


DM_UPDATE_FIELDS = {"message_id", "sent_at", "delivered"}


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_event_dm(request, pk):
    """Update DiscordEventDM delivery status (whitelisted fields only)."""
    from discordbot.models import DiscordEventDM

    dm = DiscordEventDM.objects.get(pk=pk)
    for field in DM_UPDATE_FIELDS:
        if field in request.data:
            setattr(dm, field, request.data[field])
    dm.save()
    return Response({"id": dm.pk})


# ---------------------------------------------------------------------------
# ScheduledEvent (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------

SCHEDULED_EVENT_UPDATE_FIELDS = {"discord_message_id", "next_post_at"}


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_scheduled_event(request, pk):
    """Update ScheduledEvent fields (whitelisted only)."""
    from discordbot.models import ScheduledEvent

    se = ScheduledEvent.objects.get(pk=pk)
    for field in SCHEDULED_EVENT_UPDATE_FIELDS:
        if field in request.data:
            setattr(se, field, request.data[field])
    se.save()
    return Response({"id": se.pk})


# ---------------------------------------------------------------------------
# Event state transition (CACHED — invalidate after writes)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def transition_event_state(request, pk):
    """Transition event to a new state."""
    from events.models import Event

    event = Event.objects.get(pk=pk)
    new_state = request.data.get("state")
    if not new_state:
        return Response({"error": "state required"}, status=status.HTTP_400_BAD_REQUEST)
    event.transition_state(new_state)
    invalidate_after_commit(event)
    return Response({"id": event.pk, "state": event.state})
