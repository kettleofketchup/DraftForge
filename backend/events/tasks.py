import logging

from celery import shared_task
from django.utils import timezone

from discordbot.models import DiscordMessageLog
from discordbot.utils import sync_send_embed
from events.models import Event, EventRepeater, EventState
from events.services import generate_events_for_repeater

logger = logging.getLogger(__name__)


@shared_task
def generate_upcoming_events():
    """Generate upcoming events for all active repeaters. Runs hourly."""
    repeaters = EventRepeater.objects.filter(is_active=True).select_related(
        "organization",
        "tournament_league",
        "created_by",
    )
    total = 0
    for repeater in repeaters:
        try:
            events = generate_events_for_repeater(repeater)
            total += len(events)
        except Exception:
            logger.exception("Failed to generate events for repeater %s", repeater.pk)
    return f"Generated {total} events from {repeaters.count()} repeaters"


@shared_task
def open_scheduled_signups():
    """Open signups for events where signups_open_at has passed. Runs every minute."""
    now = timezone.now()
    events = Event.objects.filter(
        state=EventState.UPCOMING,
        signups_open_at__isnull=False,
        signups_open_at__lte=now,
    )
    opened = 0
    for event in events:
        try:
            event.transition_state(EventState.SIGNUPS_OPEN)
            opened += 1
            logger.info(
                "Auto-opened signups for event %s (pk=%s)", event.name, event.pk
            )
        except Exception:
            logger.exception("Failed to auto-open signups for event %s", event.pk)
    return f"Opened signups for {opened} events"


@shared_task
def send_event_announcement(event_id):
    """Create event signup post + announcement.

    1. Signup post: full embed + buttons in the signups channel (forum thread
       or regular message). This is where users sign up. Updated on changes.
    2. Announcement: lightweight message in the announcement channel linking
       to the signup post. Posted once, not updated.

    If no signups channel is configured, the signup post goes to the
    announcement channel instead (no separate announcement needed).
    """
    from discordbot.utils import sync_send_embed, sync_send_embed_with_components
    from events.discord.embeds import build_announcement_v2

    event = Event.objects.select_related("organization", "event_repeater").get(
        pk=event_id
    )
    if not event.discord_announcement or not event.discord_announcement_channel_id:
        return "Skipped: announcement disabled"

    result = build_announcement_v2(event)
    embeds = result["embeds"]
    components = result["components"]
    thread_name = event.discord_event_title or event.name
    guild_id = event.organization.discord_server_id

    # Step 1: Create the signup post
    signup_post_result = None
    signup_message_link = None

    if event.discord_post_signups and event.discord_post_signups_channel_id:
        # Signups channel configured — post there (forum thread or regular)
        signup_post_result = sync_send_embed_with_components(
            channel_id=event.discord_post_signups_channel_id,
            embed=embeds,
            components=components,
            source="event_announcement",
            source_id=event.pk,
            forum_thread_name=thread_name,
        )

        if signup_post_result and guild_id:
            # Build Discord message link
            if signup_post_result.get("message"):
                # Forum thread — link is /guild/thread_id/message_id
                thread_id = signup_post_result["id"]
                msg_id = signup_post_result["message"]["id"]
                signup_message_link = (
                    f"https://discord.com/channels/{guild_id}/{thread_id}/{msg_id}"
                )
            else:
                # Regular message
                channel_id = event.discord_post_signups_channel_id
                msg_id = signup_post_result["id"]
                signup_message_link = (
                    f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"
                )

    if not signup_post_result:
        # No signups channel or it failed — post to announcement channel directly
        sync_send_embed_with_components(
            channel_id=event.discord_announcement_channel_id,
            embed=embeds,
            components=components,
            source="event_announcement",
            source_id=event.pk,
        )
        return f"Announced event {event.pk}"

    # Step 2: Post lightweight announcement linking to the signup post
    from events.discord.embeds import build_announcement_notice

    notice_embed = build_announcement_notice(event, signup_message_link)
    sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=notice_embed,
        source="event_notice",
        source_id=event.pk,
    )

    return f"Announced event {event.pk} (signup: {signup_message_link})"


@shared_task
def send_signup_update(event_id):
    """Edit the original announcement embed with updated signup lists."""
    from discordbot.utils import sync_edit_message
    from events.discord.embeds import build_announcement_v2

    event = Event.objects.select_related("organization", "event_repeater").get(
        pk=event_id
    )

    log_entry = (
        DiscordMessageLog.objects.filter(
            source="event_announcement",
            source_id=event.pk,
            success=True,
        )
        .order_by("-created_at")
        .first()
    )

    if not log_entry or not log_entry.discord_message_id:
        logger.info(
            "No announcement message found for event %s, skipping update", event.pk
        )
        return "Skipped: no announcement message"

    result = build_announcement_v2(event)

    # For forum threads, the message lives in the thread channel
    edit_channel_id = log_entry.channel_id
    if log_entry.response_data and log_entry.response_data.get("id"):
        thread_id = log_entry.response_data.get("id")
        if log_entry.response_data.get("message"):
            edit_channel_id = thread_id

    sync_edit_message(
        channel_id=edit_channel_id,
        message_id=log_entry.discord_message_id,
        embed=result["embeds"],
        components=result["components"],
    )
    return f"Updated announcement for event {event.pk}"


@shared_task
def send_new_event_notification(event_id):
    """Notify Discord channel about a new event from a repeater."""
    from events.discord import build_new_event_embed

    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_announcement or not event.discord_announcement_channel_id:
        return "Skipped: announcements disabled"
    embed = build_new_event_embed(event)
    sync_send_embed(
        channel_id=event.discord_announcement_channel_id,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        fields=embed.get("fields"),
        source="new_event",
        source_id=event.pk,
    )
    return f"Notified new event {event.pk}"


@shared_task
def create_discord_scheduled_event(event_id):
    """Create a Discord scheduled event via the API."""
    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_create_event:
        return "Skipped: discord_create_event disabled"
    guild_id = event.organization.discord_server_id
    if not guild_id:
        return "Skipped: no discord_server_id on organization"
    import requests as req

    from discordbot.utils import DISCORD_API_BASE, _get_headers

    title = event.discord_event_title or event.name
    description = event.discord_event_description or event.description or ""
    payload = {
        "name": title,
        "description": description[:1000],
        "scheduled_start_time": event.scheduled_at.isoformat(),
        "privacy_level": 2,
        "entity_type": 3,
        "entity_metadata": {"location": "DraftForge"},
    }
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events"
    try:
        response = req.post(url, json=payload, headers=_get_headers())
        data = response.json()
        DiscordMessageLog.objects.create(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            discord_message_id=data.get("id"),
            status_code=response.status_code,
            response_data=data,
            success=response.status_code in (200, 201),
        )
        return f"Created Discord event for event {event.pk}"
    except Exception as e:
        DiscordMessageLog.objects.create(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            success=False,
        )
        logger.exception(
            "Failed to create Discord scheduled event for event %s", event.pk
        )
        return f"Failed: {e}"


@shared_task
def sync_discord_event_signups(event_id):
    """Sync signup count to Discord scheduled event description."""
    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_sync_signups:
        return "Skipped: sync disabled"
    creation_log = (
        DiscordMessageLog.objects.filter(
            source="create_discord_event",
            source_id=event.pk,
            success=True,
        )
        .order_by("-created_at")
        .first()
    )
    if not creation_log or not creation_log.discord_message_id:
        return "Skipped: no Discord event found"
    import requests as req

    from discordbot.utils import DISCORD_API_BASE, _get_headers
    from events.discord import _signup_counts

    guild_id = event.organization.discord_server_id
    discord_event_id = creation_log.discord_message_id
    active, confirmed = _signup_counts(event)
    payload = {
        "description": (
            f"{event.description or ''}\n\n"
            f"Signups: {active}/{event.max_players or '∞'} | Confirmed: {confirmed}"
        ),
    }
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events/{discord_event_id}"
    try:
        response = req.patch(url, json=payload, headers=_get_headers())
        DiscordMessageLog.objects.create(
            channel_id=guild_id,
            embed_data=payload,
            source="sync_discord_signups",
            source_id=event.pk,
            status_code=response.status_code,
            response_data=response.json(),
            success=response.status_code == 200,
        )
        return f"Synced signups for event {event.pk}"
    except Exception as e:
        logger.exception("Failed to sync Discord event signups for event %s", event.pk)
        return f"Failed: {e}"


@shared_task
def mark_interested_discord_event(event_id, user_id):
    """Mark a user as 'interested' on the Discord scheduled event."""
    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_mark_interested:
        return "Skipped: mark_interested disabled"
    from app.models import CustomUser

    user = CustomUser.objects.get(pk=user_id)
    if not user.discordId:
        return "Skipped: user has no discordId"
    creation_log = (
        DiscordMessageLog.objects.filter(
            source="create_discord_event",
            source_id=event.pk,
            success=True,
        )
        .order_by("-created_at")
        .first()
    )
    if not creation_log or not creation_log.discord_message_id:
        return "Skipped: no Discord event found"
    import requests as req

    from discordbot.utils import DISCORD_API_BASE, _get_headers

    guild_id = event.organization.discord_server_id
    discord_event_id = creation_log.discord_message_id
    url = (
        f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events"
        f"/{discord_event_id}/users/{user.discordId}"
    )
    try:
        response = req.put(url, headers=_get_headers())
        return f"Marked user {user.pk} interested: {response.status_code}"
    except Exception as e:
        logger.exception(
            "Failed to mark interested for event %s user %s", event.pk, user.pk
        )
        return f"Failed: {e}"


@shared_task
def check_event_reminders():
    """Check for events needing reminders. Runs every 30 seconds.

    Idempotency: checks DiscordMessageLog for existing entries. DiscordMessageLog
    is NOT cached by cacheops, so queries always hit the DB.
    All reminders post to discord_announcement_channel_id (v1).
    """
    from datetime import timedelta

    from events.discord import (
        build_attendance_reminder_embed,
        build_profile_reminder_embed,
        build_signup_reminder_embed,
    )

    now = timezone.now()

    # 1. Signup reminders
    signup_reminder_events = Event.objects.filter(
        state__in=[EventState.SIGNUPS_OPEN],
        discord_signup_reminder=True,
        discord_announcement_channel_id__gt="",
    ).exclude(
        pk__in=DiscordMessageLog.objects.filter(source="signup_reminder").values_list(
            "source_id", flat=True
        )
    )
    for event in signup_reminder_events:
        threshold = event.scheduled_at - timedelta(
            hours=event.discord_signup_reminder_hours
        )
        if now >= threshold:
            embed = build_signup_reminder_embed(event)
            sync_send_embed(
                channel_id=event.discord_announcement_channel_id,
                title=embed["title"],
                description=embed["description"],
                color=embed["color"],
                fields=embed.get("fields"),
                source="signup_reminder",
                source_id=event.pk,
            )

    # 2. Attendance confirmation reminders
    attendance_events = Event.objects.filter(
        state__in=[EventState.SIGNUPS_OPEN, EventState.ROLL_CALL],
        discord_confirm_attendance=True,
        discord_announcement_channel_id__gt="",
    ).exclude(
        pk__in=DiscordMessageLog.objects.filter(
            source="attendance_reminder"
        ).values_list("source_id", flat=True)
    )
    for event in attendance_events:
        threshold = event.scheduled_at - timedelta(
            hours=event.discord_confirm_attendance_hours
        )
        if now >= threshold:
            embed = build_attendance_reminder_embed(event)
            sync_send_embed(
                channel_id=event.discord_announcement_channel_id,
                title=embed["title"],
                description=embed["description"],
                color=embed["color"],
                source="attendance_reminder",
                source_id=event.pk,
            )

    # 3. Profile completion reminders
    profile_events = Event.objects.filter(
        state__in=[EventState.SIGNUPS_OPEN],
        discord_profile_reminder=True,
        discord_announcement_channel_id__gt="",
    ).exclude(
        pk__in=DiscordMessageLog.objects.filter(source="profile_reminder").values_list(
            "source_id", flat=True
        )
    )
    for event in profile_events:
        threshold = event.scheduled_at - timedelta(
            hours=event.discord_profile_reminder_hours
        )
        if now >= threshold:
            embed = build_profile_reminder_embed(event)
            sync_send_embed(
                channel_id=event.discord_announcement_channel_id,
                title=embed["title"],
                description=embed["description"],
                color=embed["color"],
                source="profile_reminder",
                source_id=event.pk,
            )

    return "Checked reminders"
