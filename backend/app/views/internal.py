"""Internal API endpoints for celery workers and Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
All cached model writes use invalidate_after_commit() for safety — this fires
immediately when called outside a transaction (Django autocommit mode), and
defers until commit when called inside @transaction.atomic.

Field whitelists on update endpoints prevent unintended field modifications.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone as tz
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit
from discordbot.models import (
    ChannelType,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DiscordTournamentLog,
    ScheduledEvent,
)
from events.capacity import with_signup_counts
from events.completion import close_event
from events.constants import EventState
from events.ledger import SignupActor
from events.models import Event, EventRepeater, RepeaterSubscription
from events.ready_check import READY_CHECK_HELD_MESSAGE, transition_with_ready_check
from events.serializers import EventSerializer
from events.services import clear_signup_dedup_state, generate_events_for_repeater
from org.models import OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


def _validate_required(data: Mapping[str, Any], fields: list[str]) -> Response | None:
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
def create_discord_message_log(request: Request) -> Response:
    """Create a DiscordMessageLog entry.

    For reminder-type sources, checks idempotency: if a successful log
    with the same source+source_id already exists, returns it instead
    of creating a duplicate.
    """

    ALLOWED_FIELDS = {
        "channel_id",
        "embed_data",
        "source",
        "source_id",
        "discord_message_id",
        "status_code",
        "response_data",
        "success",
        "fired_by_user_id",
        "tournament_log_id",
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

    # Map fired_by_user_id → fired_by_id (Django FK column name)
    if "fired_by_user_id" in data:
        data["fired_by_id"] = data.pop("fired_by_user_id")

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


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def claim_discord_message_log(request: Request) -> Response:
    """Acquire a pre-send lease for a (source, source_id) Discord message.

    Worker passes channel_id + embed_data so the row is fully populated at
    INSERT time (DiscordMessageLog requires both as non-null fields). The
    partial unique index on (source, source_id) WHERE success IS NOT FALSE
    raises IntegrityError if a pending or successful row already exists for
    this (source, source_id) — we catch it and return 409 so the worker
    short-circuits before the Discord HTTP send.
    """

    err = _validate_required(
        request.data, ["source", "source_id", "channel_id", "embed_data"]
    )
    if err:
        return err

    create_kwargs = {
        "source": request.data["source"],
        "source_id": request.data["source_id"],
        "channel_id": request.data["channel_id"],
        "embed_data": request.data["embed_data"],
        "success": None,
        "claimed_at": tz.now(),
    }
    if "fired_by_user_id" in request.data:
        create_kwargs["fired_by_id"] = request.data["fired_by_user_id"]
    if "tournament_log_id" in request.data:
        create_kwargs["tournament_log_id"] = request.data["tournament_log_id"]

    try:
        with transaction.atomic():
            row = DiscordMessageLog.objects.create(**create_kwargs)
        return Response({"id": row.pk}, status=status.HTTP_201_CREATED)
    except IntegrityError:
        return Response({}, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def finalize_discord_message_log(request: Request, log_id: int) -> Response:
    """Update the lease row to its final state after the Discord HTTP send.

    Returns 200 on update or 410 Gone if the row was already swept by
    sweep_stale_discord_leases (worker took >5 min between claim and finalize).
    """

    err = _validate_required(request.data, ["success"])
    if err:
        return err

    update_fields = {"success": bool(request.data["success"])}
    for k in ("discord_message_id", "status_code", "response_data"):
        if k in request.data:
            update_fields[k] = request.data[k]

    updated = DiscordMessageLog.objects.filter(pk=log_id).update(**update_fields)
    if updated == 0:
        return Response(
            {"detail": "log row not found (likely swept)"},
            status=status.HTTP_410_GONE,
        )
    return Response({}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def check_message_log_exists(request: Request) -> Response:
    """Check if a non-failed DiscordMessageLog row exists (for celery idempotency).

    Matches the partial unique condition: NULL pending or True succeeded
    rows count as "exists"; False failed rows do not. This is a load-shedder
    in the fire path — the actual idempotency guarantee is the DB constraint
    on the claim endpoint above.
    """

    source = request.query_params.get("source")
    source_id = request.query_params.get("source_id")
    if not source or not source_id:
        return Response(
            {"error": "source and source_id required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    exists = (
        DiscordMessageLog.objects.filter(source=source, source_id=source_id)
        .filter(Q(success__isnull=True) | Q(success=True))
        .exists()
    )
    return Response({"exists": exists})


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def search_message_logs(request: Request) -> Response:
    """Search DiscordMessageLog entries with filters.

    Query params: source, source_id, success, source__in (comma-separated),
    order_by (default: -created_at), limit (default: 10)
    """

    qs = DiscordMessageLog.objects.all()
    params = request.query_params

    if params.get("source"):
        qs = qs.filter(source=params["source"])
    if params.get("source__in"):
        qs = qs.filter(source__in=params["source__in"].split(","))
    if params.get("source_id"):
        qs = qs.filter(source_id=params["source_id"])
    if params.get("success"):
        qs = qs.filter(success=params["success"].lower() == "true")

    order_by = params.get("order_by", "-created_at")
    if order_by in ("created_at", "-created_at"):
        qs = qs.order_by(order_by)

    limit = min(int(params.get("limit", 10)), 100)
    entries = qs[:limit]

    data = [
        {
            "id": e.pk,
            "channel_id": e.channel_id,
            "source": e.source,
            "source_id": e.source_id,
            "discord_message_id": e.discord_message_id,
            "status_code": e.status_code,
            "success": e.success,
            "response_data": e.response_data,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
    return Response(data)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_discord_event_state(request: Request, event_id: int) -> Response:
    """Get DiscordEvent + related records for an event (celery reads)."""

    result = {
        "has_discord_event": False,
        "scheduled_event_id": None,
        "signup_posted": False,
        "fired_actions": [],
        "has_dms": False,
    }

    try:
        de = DiscordEvent.objects.get(event_id=event_id)
        result["has_discord_event"] = True
        result["discord_event_pk"] = de.pk
        result["scheduled_event_id"] = de.scheduled_event_id or None

        result["fired_actions"] = list(
            DiscordEventLog.objects.filter(discord_event=de, success=True).values_list(
                "action", flat=True
            )
        )

        result["has_dms"] = DiscordEventDM.objects.filter(discord_event=de).exists()
    except DiscordEvent.DoesNotExist:
        pass

    signup_msg = DiscordEventMsgSignup.objects.filter(
        event_id=event_id, has_posted=True
    ).first()
    result["signup_posted"] = signup_msg is not None
    if signup_msg:
        result["signup_message_id"] = signup_msg.message_id
        result["signup_channel_id"] = signup_msg.channel_id
        result["signup_thread_id"] = signup_msg.thread_id
        # "text" | "forum" — drives explicit edit routing in
        # events.tasks._send_signup_update_impl. Legacy rows may have ""
        # (unset); workers fall back to a thread_id-vs-channel_id heuristic
        # in that case and emit a `legacy_channel_type` warning.
        result["signup_channel_type"] = signup_msg.channel_type or None

    return Response(result)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_sync_discord_state(request: Request) -> Response:
    """Bulk state for sync_discord_events — all active events' Discord status.

    Returns event IDs that have: signup posts, scheduled events, recent log attempts.
    Replaces 4 separate queries in sync_discord_events task.
    """

    now = tz.now()

    # Active events (same filter as sync_discord_events)
    active_events = list(
        Event.objects.filter(
            state__in=[
                EventState.UPCOMING,
                EventState.SIGNUPS_OPEN,
                EventState.ROLL_CALL,
            ],
            scheduled_at__gte=now - timedelta(days=1),
            scheduled_at__lte=now + timedelta(days=30),
        )
        .select_related("organization", "event_repeater")
        .values(
            "pk",
            "name",
            "state",
            "scheduled_at",
            "discord_announcement",
            "discord_announcement_channel_id",
            "discord_post_signups",
            "discord_post_signups_channel_id",
            "discord_create_event",
            "organization__discord_server_id",
        )
    )

    # Existing successful logs (legacy)
    existing_logs = set(
        DiscordMessageLog.objects.filter(
            success=True,
            source__in=["event_announcement", "event_notice", "create_discord_event"],
        ).values_list("source", "source_id")
    )

    # Events with posted signup messages
    events_with_signup = set(
        DiscordEventMsgSignup.objects.filter(has_posted=True).values_list(
            "event_id", flat=True
        )
    )

    # Events with scheduled Discord events
    events_with_scheduled = set(
        DiscordEvent.objects.filter(scheduled_event_id__isnull=False)
        .exclude(scheduled_event_id="")
        .values_list("event_id", flat=True)
    )

    # Recent create_scheduled_event attempts (5-min backoff)
    events_with_recent_attempt = set(
        DiscordEventLog.objects.filter(
            action="create_scheduled_event",
            created_at__gte=now - timedelta(minutes=5),
        ).values_list("discord_event__event_id", flat=True)
    )

    return Response(
        {
            "active_events": active_events,
            "existing_logs": list(existing_logs),
            "events_with_signup": list(events_with_signup),
            "events_with_scheduled": list(events_with_scheduled),
            "events_with_recent_attempt": list(events_with_recent_attempt),
        }
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_repeater_subscribers(request: Request, repeater_id: int) -> Response:
    """Get subscribers for a repeater with Discord IDs and org membership."""

    subs = RepeaterSubscription.objects.filter(
        event_repeater_id=repeater_id
    ).select_related("user")

    data = []
    for sub in subs:
        if not sub.user.discordId:
            continue
        org_user = OrgUser.objects.filter(
            user=sub.user,
            organization=sub.event_repeater.organization,
        ).first()
        data.append(
            {
                "user_pk": sub.user.pk,
                "discord_id": sub.user.discordId,
                "org_user_pk": org_user.pk if org_user else None,
            }
        )
    return Response(data)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_due_scheduled_events(request: Request) -> Response:
    """Get ScheduledEvents that are due for posting."""

    now = tz.now()
    due = ScheduledEvent.objects.filter(
        is_active=True,
        next_post_at__lte=now,
        discord_message_id__isnull=True,
    ).select_related("template")

    data = [
        {
            "pk": se.pk,
            "is_recurring": se.is_recurring,
            "next_post_at": se.next_post_at.isoformat() if se.next_post_at else None,
            "template": {
                "name": se.template.name,
                "template_type": se.template.template_type,
                "title": se.template.title,
                "description": se.template.description,
                "color": se.template.color,
                "channel_id": se.template.channel_id,
                "include_rsvp": se.template.include_rsvp,
            },
        }
        for se in due
    ]
    return Response(data)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_event_for_task(request: Request, event_id: int) -> Response:
    """Get full event data + org Discord config needed by celery tasks."""
    try:
        event = with_signup_counts(
            Event.objects.select_related("organization", "event_repeater").filter(
                pk=event_id
            )
        ).get()
    except Event.DoesNotExist:
        return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

    data = EventSerializer(event).data
    data["organization_id"] = event.organization_id
    data["organization_discord_server_id"] = event.organization.discord_server_id or ""
    data["organization_logo"] = event.organization.logo or ""
    data["event_repeater_id"] = event.event_repeater_id
    return Response(data)


# ---------------------------------------------------------------------------
# DiscordEventLog (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_event_log(request: Request) -> Response:
    """Create a DiscordEventLog audit entry."""

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
        "message_log_id",
    }
    data = {k: v for k, v in request.data.items() if k in EVENT_LOG_FIELDS}
    discord_event = DiscordEvent.objects.get(pk=request.data["discord_event_id"])
    entry = DiscordEventLog.objects.create(discord_event=discord_event, **data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# DiscordTournamentLog (NOT cached — no invalidation needed)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_tournament_log(request: Request) -> Response:
    """Create DiscordTournamentLog entry."""

    ALLOWED_FIELDS = {
        "tournament_id",
        "category",
        "notification_type",
        "message",
        "recipient_count",
        "success",
    }
    err = _validate_required(
        request.data, ["tournament_id", "notification_type", "message"]
    )
    if err:
        return err
    data = {k: v for k, v in request.data.items() if k in ALLOWED_FIELDS}
    entry = DiscordTournamentLog.objects.create(**data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


TOURNAMENT_LOG_UPDATE_FIELDS = {"recipient_count", "message", "success"}


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_tournament_log(request: Request, pk: int) -> Response:
    """Update DiscordTournamentLog entry (recipient_count, message, success)."""

    log = DiscordTournamentLog.objects.get(pk=pk)
    for field in TOURNAMENT_LOG_UPDATE_FIELDS:
        if field in request.data:
            setattr(log, field, request.data[field])
    log.save()
    return Response({"id": log.pk})


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
def get_or_create_discord_event(request: Request) -> Response:
    """Get or create a DiscordEvent for an event."""

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
def update_discord_event(request: Request, pk: int) -> Response:
    """Update DiscordEvent fields (whitelisted only)."""

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
def clear_event_signup_state(request: Request) -> Response:
    """Reset the signup-post dedup state so the next sync (or manual re-fire)
    recreates the post.

    Flips:
      - DiscordEventMsgSignup.has_posted=False (clears `events_with_signup_post`)
      - DiscordMessageLog.success=False for source=event_announcement+source_id=event_id
        (clears `existing_logs` dedup)

    Called by:
      - send_signup_update on MessageDeletedError (auto-recovery for externally
        deleted posts)
      - fire_event_task for task_name="signup_post" (admin "repost" button)
    """

    err = _validate_required(request.data, ["event_id"])
    if err:
        return err
    event_id = request.data["event_id"]

    result = clear_signup_dedup_state(event_id)
    log.info(
        "events_signup_dedup_cleared",
        system="events",
        subsystem="discord",
        event_id=event_id,
        signups_changed=result["signup_rows_cleared"],
        logs_changed=result["message_log_rows_cleared"],
    )
    return Response({"event_id": event_id, **result})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_signup_message(request: Request) -> Response:
    """Create/update DiscordEventMsgSignup (whitelisted fields only)."""

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
def create_or_update_announcement(request: Request) -> Response:
    """Create/update DiscordEventMsgAnnouncement (whitelisted fields only)."""

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
def create_event_dm(request: Request) -> Response:
    """Create DiscordEventDM record (crash-safe: create before send)."""

    DM_CREATE_FIELDS = {"discord_event", "org_user", "dm_type", "delivered"}
    err = _validate_required(request.data, ["discord_event", "org_user", "dm_type"])
    if err:
        return err
    data = {k: v for k, v in request.data.items() if k in DM_CREATE_FIELDS}
    # Map FK fields to _id columns for raw PK assignment
    if "discord_event" in data:
        data["discord_event_id"] = data.pop("discord_event")
    if "org_user" in data:
        data["org_user_id"] = data.pop("org_user")
    dm = DiscordEventDM.objects.create(**data)
    return Response({"id": dm.pk}, status=status.HTTP_201_CREATED)


DM_UPDATE_FIELDS = {"message_id", "sent_at", "delivered"}


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_event_dm(request: Request, pk: int) -> Response:
    """Update DiscordEventDM delivery status (whitelisted fields only)."""

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
def update_scheduled_event(request: Request, pk: int) -> Response:
    """Update ScheduledEvent fields (whitelisted only)."""

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
def transition_event_state(request: Request, pk: int) -> Response:
    """Transition event to a new state."""
    event = Event.objects.nocache().get(pk=pk)
    new_state = request.data.get("state")
    if not new_state:
        return Response({"error": "state required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        started = transition_with_ready_check(
            event, new_state, actor=SignupActor.system()
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    if not started:
        return Response(
            {"code": "ready_check_held", "error": READY_CHECK_HELD_MESSAGE},
            status=status.HTTP_409_CONFLICT,
        )
    return Response({"id": event.pk, "state": event.state})


_AUTO_CLOSE_TARGETS: dict[str, EventState] = {
    EventState.UPCOMING: EventState.CANCELLED,
    EventState.SIGNUPS_OPEN: EventState.CANCELLED,
    EventState.ROLL_CALL: EventState.COMPLETED,
    EventState.IN_PROGRESS: EventState.COMPLETED,
}
_AUTO_CLOSE_TERMINAL: frozenset[str] = frozenset(
    {EventState.COMPLETED, EventState.CANCELLED}
)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def auto_close_event(request: Request, pk: int) -> Response:
    event = Event.objects.nocache().select_related("organization").filter(pk=pk).first()
    if event is None:
        return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)
    if event.state in _AUTO_CLOSE_TERMINAL:
        return Response({"closed": False, "state": event.state})
    target = _AUTO_CLOSE_TARGETS.get(event.state)
    if target is None:
        return Response(
            {"error": f"Cannot auto-close an event in state {event.state!r}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    result = close_event(
        event,
        new_state=target,
        source="auto",
        expected_from=[s for s, t in _AUTO_CLOSE_TARGETS.items() if t == target],
    )
    return Response({"closed": result.closed, "state": result.state})


# ---------------------------------------------------------------------------
# User avatar management
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def list_users_for_avatar_check(request: Request) -> Response:
    """Return users with Discord IDs for avatar validation.

    Query params:
        has_avatar: "true" (only users with existing avatar) or "false"
        limit: max results (default 100)
        offset: pagination offset (default 0)
    """

    User = get_user_model()

    qs = User.objects.filter(discordId__isnull=False)

    has_avatar = request.query_params.get("has_avatar")
    # avatar lives on base_profile; ORM filters need the relation path
    if has_avatar == "true":
        qs = qs.exclude(base_profile__avatar__isnull=True).exclude(
            base_profile__avatar=""
        )
    elif has_avatar == "false":
        qs = qs.filter(
            Q(base_profile__avatar__isnull=True) | Q(base_profile__avatar="")
        )

    limit = int(request.query_params.get("limit", 100))
    offset = int(request.query_params.get("offset", 0))

    users = qs[offset : offset + limit]
    return Response(
        [
            {
                "pk": u.pk,
                "discord_id": u.discordId,
                "avatar": u.avatar,
                "username": u.username,
            }
            for u in users
        ]
    )


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_user_avatar(request: Request, pk: int) -> Response:
    """Update a user's avatar hash.

    Body: {"avatar": "new_avatar_hash"} or {"avatar": null} to clear.
    """

    User = get_user_model()

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Discord avatar hashes are 32 chars (or 34 with the `a_` animated prefix).
    # Cap at 64 to defend the TextField from accidental URL/blob payloads —
    # this endpoint is internal-only but the only celery-driven ingress for
    # avatar refresh, so a sanity cap closes a tail-risk.
    avatar = request.data.get("avatar")
    if avatar is not None:
        if not isinstance(avatar, str):
            return Response(
                {"error": "avatar must be a string or null"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(avatar) > 64:
            return Response(
                {"error": "avatar exceeds 64 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # avatar setter persists + invalidates base_profile; also evict the user
    # row since UserSerializer.avatar reads through base_profile.
    user.avatar = avatar
    invalidate_after_commit(user)

    return Response({"pk": user.pk, "avatar": user.avatar})


# ---------------------------------------------------------------------------
# EventRepeater (for generate_upcoming_events task)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_active_repeaters(request: Request) -> Response:
    """List active repeaters for event generation task."""

    repeaters = EventRepeater.objects.filter(is_active=True).select_related(
        "organization", "tournament_league", "created_by"
    )
    data = []
    for r in repeaters:
        data.append(
            {
                "pk": r.pk,
                "name": r.name,
                "organization_id": r.organization_id,
            }
        )
    return Response(data)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def generate_repeater_events(request: Request, repeater_id: int) -> Response:
    """Generate upcoming events for a specific repeater."""

    try:
        repeater = EventRepeater.objects.select_related(
            "organization", "tournament_league", "created_by"
        ).get(pk=repeater_id)
    except EventRepeater.DoesNotExist:
        return Response({"error": "Repeater not found"}, status=404)

    try:
        events = generate_events_for_repeater(repeater)
        return Response({"created_count": len(events)})
    except Exception as e:
        log.exception(
            "events_repeater_generate_failed",
            system="events",
            subsystem="scheduling",
            repeater_id=repeater_id,
            error=str(e),
        )
        return Response({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Discord lease sweeper
# ---------------------------------------------------------------------------


def _parse_nonneg_int(
    value: Any, field_name: str, default: int
) -> tuple[int | None, Response | None]:
    """Parse a non-negative integer threshold field.

    Returns (parsed, error_response). Refuses negatives explicitly —
    a negative threshold would push the cutoff into the future and the
    sweep would match every row in the table.
    """
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, Response(
            {"error": f"{field_name} must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if parsed < 0:
        return None, Response(
            {"error": f"{field_name} must be >= 0"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return parsed, None


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def sweep_stale_discord_leases(request: Request) -> Response:
    """Reap stuck DiscordMessageLog rows.

    Body (all optional, must be non-negative):
        pending_threshold_minutes: default 5 — NULL-success rows older
            than this are considered crashed workers, deleted so the
            next poll can re-claim.
        failed_threshold_hours: default 1 — success=False rows older
            than this are considered transiently failed, deleted so the
            next poll can retry. Admins should investigate via the
            original log row before it ages out.

    Returns {pending_swept, failed_swept, total}.
    """

    pending_minutes, err = _parse_nonneg_int(
        request.data.get("pending_threshold_minutes"),
        "pending_threshold_minutes",
        default=5,
    )
    if err is not None:
        return err
    failed_hours, err = _parse_nonneg_int(
        request.data.get("failed_threshold_hours"),
        "failed_threshold_hours",
        default=1,
    )
    if err is not None:
        return err

    now = tz.now()
    pending_threshold = now - timedelta(minutes=pending_minutes)
    failed_threshold = now - timedelta(hours=failed_hours)

    pending_swept, _ = DiscordMessageLog.objects.filter(
        success__isnull=True,
        claimed_at__lt=pending_threshold,
    ).delete()
    failed_swept, _ = DiscordMessageLog.objects.filter(
        success=False,
        claimed_at__lt=failed_threshold,
    ).delete()

    total = pending_swept + failed_swept
    if total:
        log.info(
            "discord_leases_swept",
            system="discord",
            subsystem="lease",
            pending_swept=pending_swept,
            failed_swept=failed_swept,
            total=total,
            pending_threshold_minutes=pending_minutes,
            failed_threshold_hours=failed_hours,
        )
    return Response(
        {
            "pending_swept": pending_swept,
            "failed_swept": failed_swept,
            "total": total,
        }
    )
