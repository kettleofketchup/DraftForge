"""Internal API endpoints for celery workers and Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
All cached model writes use invalidate_after_commit() for safety — this fires
immediately when called outside a transaction (Django autocommit mode), and
defers until commit when called inside @transaction.atomic.

Field whitelists on update endpoints prevent unintended field modifications.
"""

import logging

from django.utils import timezone as tz
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


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def search_message_logs(request):
    """Search DiscordMessageLog entries with filters.

    Query params: source, source_id, success, source__in (comma-separated),
    order_by (default: -created_at), limit (default: 10)
    """
    from discordbot.models import DiscordMessageLog

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
def get_discord_event_state(request, event_id):
    """Get DiscordEvent + related records for an event (celery reads)."""
    from discordbot.models import (
        DiscordEvent,
        DiscordEventDM,
        DiscordEventLog,
        DiscordEventMsgSignup,
    )

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

    return Response(result)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_sync_discord_state(request):
    """Bulk state for sync_discord_events — all active events' Discord status.

    Returns event IDs that have: signup posts, scheduled events, recent log attempts.
    Replaces 4 separate queries in sync_discord_events task.
    """
    from datetime import timedelta

    from discordbot.models import (
        DiscordEvent,
        DiscordEventLog,
        DiscordEventMsgSignup,
        DiscordMessageLog,
    )
    from events.constants import EventState
    from events.models import Event

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
def get_repeater_subscribers(request, repeater_id):
    """Get subscribers for a repeater with Discord IDs and org membership."""
    from events.models import RepeaterSubscription
    from org.models import OrgUser

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
def get_due_scheduled_events(request):
    """Get ScheduledEvents that are due for posting."""
    from discordbot.models import ScheduledEvent

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
def get_event_for_task(request, event_id):
    """Get full event data + org Discord config needed by celery tasks."""
    from events.models import Event

    try:
        event = Event.objects.select_related("organization", "event_repeater").get(
            pk=event_id
        )
    except Event.DoesNotExist:
        return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

    from events.serializers import EventSerializer

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
def create_tournament_log(request):
    """Create DiscordTournamentLog entry."""
    from discordbot.models import DiscordTournamentLog

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
def update_tournament_log(request, pk):
    """Update DiscordTournamentLog entry (recipient_count, message, success)."""
    from discordbot.models import DiscordTournamentLog

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


# ---------------------------------------------------------------------------
# Tournament reads (for Celery tasks)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_tournament_for_task(request, tournament_id):
    """Get tournament config data for Celery tasks."""
    from app.models import Tournament

    try:
        t = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "id": t.pk,
            "name": t.name,
            "state": t.state,
            "date_played": t.date_played.isoformat() if t.date_played else None,
            "auto_create_hero_drafts": t.auto_create_hero_drafts,
            "discord_send_draft_link": t.discord_send_draft_link,
            "discord_send_herodraft_link": t.discord_send_herodraft_link,
            "tournament_type": t.tournament_type,
            "draft_type": t.draft_type,
        }
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_tournament_participants(request, tournament_id):
    """Get tournament participants with Discord IDs (for DM sending)."""
    from app.models import CustomUser

    users = (
        CustomUser.objects.filter(
            teams_as_member__tournament_id=tournament_id,
            discordId__isnull=False,
        )
        .exclude(discordId="")
        .distinct()
        .values("pk", "discordId", "username")
    )
    return Response(
        [
            {
                "user_pk": u["pk"],
                "discord_id": u["discordId"],
                "username": u["username"] or "",
            }
            for u in users
        ]
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_match_participants(request, game_id):
    """Get players from both teams in a match (for hero draft DMs)."""
    from app.models import CustomUser, Game

    try:
        game = Game.objects.select_related("radiant_team", "dire_team").get(pk=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    users = (
        CustomUser.objects.filter(
            teams_as_member__in=[game.radiant_team, game.dire_team],
            discordId__isnull=False,
        )
        .exclude(discordId="")
        .distinct()
        .values("pk", "discordId", "username")
    )
    return Response(
        [
            {
                "user_pk": u["pk"],
                "discord_id": u["discordId"],
                "username": u["username"] or "",
            }
            for u in users
        ]
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_games_without_herodraft(request, tournament_id):
    """Get games with both teams assigned but no hero draft."""
    from app.models import Game

    games = Game.objects.filter(
        tournament_id=tournament_id,
        radiant_team__isnull=False,
        dire_team__isnull=False,
        herodraft__isnull=True,
    ).select_related("radiant_team", "dire_team")
    return Response(
        [
            {
                "id": g.pk,
                "radiant_team_id": g.radiant_team_id,
                "radiant_team_name": g.radiant_team.name,
                "dire_team_id": g.dire_team_id,
                "dire_team_name": g.dire_team.name,
                "round": g.round,
                "has_captains": bool(g.radiant_team.captain and g.dire_team.captain),
            }
            for g in games
        ]
    )


# ---------------------------------------------------------------------------
# Tournament writes (CACHED — invalidate after writes)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_herodraft_for_game(request, game_id):
    """Atomically create a HeroDraft for a game (select_for_update guard).

    Returns existing herodraft if one already exists (idempotent).
    Returns 400 if teams missing captains.
    """
    from django.db import transaction

    from app.models import DraftTeam, Game, HeroDraft, HeroDraftState

    with transaction.atomic():
        game = (
            Game.objects.select_for_update()
            .select_related("radiant_team", "dire_team")
            .get(pk=game_id)
        )

        # Idempotent: return existing
        if hasattr(game, "herodraft"):
            return Response({"id": game.herodraft.pk, "created": False})

        if not game.radiant_team.captain or not game.dire_team.captain:
            return Response(
                {"error": "Both teams must have captains"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        herodraft = HeroDraft.objects.create(
            game=game, state=HeroDraftState.WAITING_FOR_CAPTAINS
        )
        DraftTeam.objects.create(draft=herodraft, tournament_team=game.radiant_team)
        DraftTeam.objects.create(draft=herodraft, tournament_team=game.dire_team)
        invalidate_after_commit(game)

    return Response(
        {"id": herodraft.pk, "created": True},
        status=status.HTTP_201_CREATED,
    )
