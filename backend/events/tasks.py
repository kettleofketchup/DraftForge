import logging

from celery import shared_task
from django.utils import timezone

from discordbot.models import (
    DiscordEvent,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)
from discordbot.utils import sync_send_embed
from events.models import Event, EventRepeater, EventState
from events.services import generate_events_for_repeater

logger = logging.getLogger(__name__)


def _get_or_create_discord_event(event):
    """Get or create a DiscordEvent for the given Event."""
    guild_id = event.organization.discord_server_id or ""
    discord_event, _ = DiscordEvent.objects.get_or_create(
        event=event,
        defaults={"guild_id": guild_id},
    )
    return discord_event


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
def sync_discord_events():
    """Reconciliation task: ensure Discord matches the DB for all active events.

    Runs every 5 minutes via celery beat. Scans all active events and ensures:
    1. Signup posts exist (forum thread or regular message)
    2. Announcement notices exist (if announcement channel configured)
    3. Discord scheduled events exist (if discord_create_event enabled)

    Self-heals: catches failed dispatches, late config changes, events created
    before the Discord feature, worker downtime, and any other gaps.

    Checks both DiscordEvent (new) and DiscordMessageLog (legacy) models.
    """
    from datetime import timedelta

    from discordbot.models import DiscordMessageLog

    # Only process active events (not completed/cancelled) scheduled within 30 days
    active_events = Event.objects.filter(
        state__in=[EventState.UPCOMING, EventState.SIGNUPS_OPEN, EventState.ROLL_CALL],
        scheduled_at__gte=timezone.now() - timedelta(days=1),
        scheduled_at__lte=timezone.now() + timedelta(days=30),
    ).select_related("organization", "event_repeater")

    # Get all existing successful log entries in one query (legacy)
    existing_logs = set(
        DiscordMessageLog.objects.filter(
            success=True,
            source__in=["event_announcement", "event_notice", "create_discord_event"],
        ).values_list("source", "source_id")
    )

    # New model: event IDs that already have posted signup messages
    events_with_signup_post = set(
        DiscordEventMsgSignup.objects.filter(has_posted=True).values_list(
            "event_id", flat=True
        )
    )

    # New model: event IDs that already have scheduled Discord events
    events_with_scheduled = set(
        DiscordEvent.objects.filter(
            scheduled_event_id__isnull=False,
        )
        .exclude(scheduled_event_id="")
        .values_list("event_id", flat=True)
    )

    # Avoid retrying create_scheduled_event that failed recently (within 1 hour)
    events_with_recent_scheduled_attempt = set(
        DiscordEventLog.objects.filter(
            action="create_scheduled_event",
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).values_list("discord_event__event_id", flat=True)
    )

    signup_posts_created = 0
    notices_created = 0
    discord_events_created = 0

    for event in active_events:
        # 1. Signup post — only when signups are actually open
        has_signup = (
            event.pk in events_with_signup_post
            or ("event_announcement", event.pk) in existing_logs
        )
        if (
            event.state == EventState.SIGNUPS_OPEN
            and event.discord_announcement
            and event.discord_announcement_channel_id
            and not has_signup
        ):
            try:
                send_event_announcement(event.pk)
                signup_posts_created += 1
                logger.info("Sync: created signup post for event %s", event.pk)
            except Exception:
                logger.exception("Sync: failed signup post for event %s", event.pk)

        # 2. Discord scheduled event
        has_scheduled = (
            event.pk in events_with_scheduled
            or ("create_discord_event", event.pk) in existing_logs
            or event.pk in events_with_recent_scheduled_attempt
        )
        if (
            event.discord_create_event
            and event.organization.discord_server_id
            and not has_scheduled
        ):
            try:
                create_discord_scheduled_event(event.pk)
                discord_events_created += 1
                logger.info(
                    "Sync: created Discord scheduled event for event %s", event.pk
                )
            except Exception:
                logger.exception(
                    "Sync: failed Discord scheduled event for event %s", event.pk
                )

    total = signup_posts_created + notices_created + discord_events_created
    if total:
        logger.info(
            "sync_discord_events: %d signup posts, %d notices, %d scheduled events",
            signup_posts_created,
            notices_created,
            discord_events_created,
        )
    return (
        f"Scanned {active_events.count()} events: "
        f"{signup_posts_created} signup posts, "
        f"{discord_events_created} scheduled events created"
    )


@shared_task
def send_event_announcement(event_id):
    """Create event signup post + announcement.

    1. Signup post: full embed + buttons in the signups channel (forum thread
       or regular message). This is where users sign up. Updated on changes.
    2. Announcement: lightweight message in the announcement channel linking
       to the signup post. Posted once, not updated.

    If no signups channel is configured, the signup post goes to the
    announcement channel instead (no separate announcement needed).

    Also creates DiscordEvent/DiscordEventMsg* records alongside the existing
    DiscordMessageLog entries (coexistence during migration).
    """
    from cacheops import invalidate_obj

    from discordbot.models import ChannelType
    from discordbot.utils import sync_send_embed, sync_send_embed_with_components
    from events.discord.embeds import build_announcement_v2

    event = Event.objects.select_related("organization", "event_repeater").get(
        pk=event_id
    )
    if event.state != EventState.SIGNUPS_OPEN:
        return f"Skipped: event state is {event.state}, not signups_open"
    if not event.discord_announcement or not event.discord_announcement_channel_id:
        return "Skipped: announcement disabled"

    result = build_announcement_v2(event)
    embeds = result["embeds"]
    components = result["components"]
    signup_content = result.get("content")
    signup_mentions = result.get("allowed_mentions")
    thread_name = event.discord_event_title or event.name
    guild_id = event.organization.discord_server_id

    # Get or create DiscordEvent for this event
    discord_event = _get_or_create_discord_event(event)

    # Step 1: Create the signup post
    signup_post_result = None
    signup_message_link = None

    if event.discord_post_signups and event.discord_post_signups_channel_id:
        # Create DiscordEventMsgSignup record before sending
        signup_msg, _ = DiscordEventMsgSignup.objects.get_or_create(
            event=event,
            channel_id=event.discord_post_signups_channel_id,
            defaults={"channel_type": ChannelType.TEXT},
        )

        # Signups channel configured — post there (forum thread or regular)
        signup_post_result = sync_send_embed_with_components(
            channel_id=event.discord_post_signups_channel_id,
            embed=embeds,
            components=components,
            source="event_announcement",
            source_id=event.pk,
            forum_thread_name=thread_name,
            content=signup_content,
            allowed_mentions=signup_mentions,
        )

        if signup_post_result:
            # Update the signup message record with Discord IDs
            if signup_post_result.get("message"):
                # Forum thread
                signup_msg.thread_id = signup_post_result["id"]
                signup_msg.message_id = signup_post_result["message"]["id"]
                signup_msg.channel_type = ChannelType.FORUM
            else:
                # Regular message
                signup_msg.message_id = signup_post_result["id"]
            signup_msg.has_posted = True
            signup_msg.message_last_updated = timezone.now()
            signup_msg.save()

            # Link signup_message to discord_event
            discord_event.signup_message = signup_msg
            discord_event.save(update_fields=["signup_message", "updated_at"])
            invalidate_obj(discord_event)

            # Create audit log entry
            DiscordEventLog.objects.create(
                discord_event=discord_event,
                action="send_signup_post",
                target_type="DiscordEventMsgSignup",
                message_id=signup_msg.message_id,
                success=True,
            )

            if guild_id:
                # Build Discord message link
                if signup_post_result.get("message"):
                    thread_id = signup_post_result["id"]
                    msg_id = signup_post_result["message"]["id"]
                    signup_message_link = (
                        f"https://discord.com/channels/{guild_id}/{thread_id}/{msg_id}"
                    )
                else:
                    channel_id = event.discord_post_signups_channel_id
                    msg_id = signup_post_result["id"]
                    signup_message_link = (
                        f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"
                    )

    if not signup_post_result:
        # No signups channel or it failed — post to announcement channel directly
        # Create signup msg record for the announcement channel fallback
        signup_msg, _ = DiscordEventMsgSignup.objects.get_or_create(
            event=event,
            channel_id=event.discord_announcement_channel_id,
            defaults={"channel_type": ChannelType.TEXT},
        )

        fallback_result = sync_send_embed_with_components(
            channel_id=event.discord_announcement_channel_id,
            embed=embeds,
            components=components,
            source="event_announcement",
            source_id=event.pk,
        )

        if fallback_result:
            signup_msg.message_id = fallback_result.get("id")
            signup_msg.has_posted = True
            signup_msg.message_last_updated = timezone.now()
            signup_msg.save()

            discord_event.signup_message = signup_msg
            discord_event.save(update_fields=["signup_message", "updated_at"])
            invalidate_obj(discord_event)

            DiscordEventLog.objects.create(
                discord_event=discord_event,
                action="send_signup_post",
                target_type="DiscordEventMsgSignup",
                message_id=signup_msg.message_id,
                success=True,
            )

        return f"Announced event {event.pk}"

    # Step 2: Post lightweight announcement linking to the signup post
    from events.discord.embeds import build_announcement_notice

    # Create DiscordEventMsgAnnouncement record
    announcement_msg, _ = DiscordEventMsgAnnouncement.objects.get_or_create(
        event=event,
        channel_id=event.discord_announcement_channel_id,
        defaults={"channel_type": ChannelType.TEXT},
    )

    notice_result = build_announcement_notice(event, signup_message_link)
    notice_api_result = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=notice_result["embed"],
        source="event_notice",
        source_id=event.pk,
        content=notice_result.get("content"),
        allowed_mentions=notice_result.get("allowed_mentions"),
    )

    if notice_api_result:
        announcement_msg.message_id = notice_api_result.get("id")
        announcement_msg.has_posted = True
        announcement_msg.message_last_updated = timezone.now()
        announcement_msg.save()

        discord_event.announcement = announcement_msg
        discord_event.save(update_fields=["announcement", "updated_at"])
        invalidate_obj(discord_event)

        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="send_announcement_notice",
            target_type="DiscordEventMsgAnnouncement",
            message_id=announcement_msg.message_id,
            success=True,
        )

    return f"Announced event {event.pk} (signup: {signup_message_link})"


@shared_task
def send_signup_update(event_id):
    """Edit the original announcement embed with updated signup lists.

    Tries the new DiscordEvent.signup_message first, falls back to
    DiscordMessageLog for pre-migration events.
    """
    from cacheops import invalidate_obj

    from discordbot.utils import sync_edit_message
    from events.discord.embeds import build_announcement_v2

    event = Event.objects.select_related("organization", "event_repeater").get(
        pk=event_id
    )

    # Try new model first
    edit_channel_id = None
    message_id = None
    signup_msg = None
    discord_event = None

    try:
        discord_event = event.discord_event
        signup_msg = discord_event.signup_message
        if signup_msg and signup_msg.has_posted and signup_msg.message_id:
            message_id = signup_msg.message_id
            # For forum threads, edit within the thread channel
            if signup_msg.thread_id:
                edit_channel_id = signup_msg.thread_id
            else:
                edit_channel_id = signup_msg.channel_id
    except DiscordEvent.DoesNotExist:
        pass

    # Fall back to DiscordMessageLog for pre-migration events
    if not message_id:
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
                "No announcement message found for event %s, skipping update",
                event.pk,
            )
            return "Skipped: no announcement message"

        message_id = log_entry.discord_message_id
        edit_channel_id = log_entry.channel_id
        if log_entry.response_data and log_entry.response_data.get("id"):
            thread_id = log_entry.response_data.get("id")
            if log_entry.response_data.get("message"):
                edit_channel_id = thread_id

    result = build_announcement_v2(event)

    sync_edit_message(
        channel_id=edit_channel_id,
        message_id=message_id,
        embed=result["embeds"],
        components=result["components"],
    )

    # Update tracking on the new model if available
    if signup_msg:
        signup_msg.message_last_updated = timezone.now()
        signup_msg.save(update_fields=["message_last_updated", "updated_at"])
        invalidate_obj(signup_msg)

        if discord_event:
            DiscordEventLog.objects.create(
                discord_event=discord_event,
                action="edit_signup_post",
                target_type="DiscordEventMsgSignup",
                message_id=message_id,
                success=True,
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
    """Create a Discord scheduled event via the API.

    Also stores the scheduled_event_id on the DiscordEvent model and creates
    a DiscordEventLog entry.
    """
    from cacheops import invalidate_obj

    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_create_event:
        return "Skipped: discord_create_event disabled"
    guild_id = event.organization.discord_server_id
    if not guild_id:
        return "Skipped: no discord_server_id on organization"
    from datetime import timedelta

    import requests as req

    from discordbot.utils import DISCORD_API_BASE, _get_headers

    title = event.discord_event_title or event.name
    description = event.discord_event_description or event.description or ""
    payload = {
        "name": title,
        "description": description[:1000],
        "scheduled_start_time": event.scheduled_at.isoformat(),
        "scheduled_end_time": (event.scheduled_at + timedelta(hours=3)).isoformat(),
        "privacy_level": 2,
        "entity_type": 3,
        "entity_metadata": {"location": "DraftForge"},
    }
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events"
    discord_event = _get_or_create_discord_event(event)

    try:
        response = req.post(url, json=payload, headers=_get_headers())
        data = response.json()
        success = response.status_code in (200, 201)

        # Legacy log
        DiscordMessageLog.objects.create(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            discord_message_id=data.get("id"),
            status_code=response.status_code,
            response_data=data,
            success=success,
        )

        # New model: store scheduled event ID
        if success and data.get("id"):
            discord_event.scheduled_event_id = data["id"]
            discord_event.save(update_fields=["scheduled_event_id", "updated_at"])
            invalidate_obj(discord_event)

        # Audit log
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="create_scheduled_event",
            target_type="DiscordEvent",
            status_code=response.status_code,
            response_data=data,
            success=success,
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
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="create_scheduled_event",
            target_type="DiscordEvent",
            success=False,
            error_message=str(e),
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

    # 4. Subscriber DM notifications
    from discordbot.models import DMType as DMTypeChoices

    dm_events = Event.objects.filter(
        state__in=[EventState.SIGNUPS_OPEN, EventState.ROLL_CALL],
        discord_subscriber_dm=True,
        event_repeater__isnull=False,
    )
    for event in dm_events:
        # Skip if any DMs already sent for this event
        from discordbot.models import DiscordEventDM

        has_dms = DiscordEventDM.objects.filter(
            discord_event__event=event,
            dm_type=DMTypeChoices.SIGNUP_REMINDER,
        ).exists()
        if has_dms:
            continue
        threshold = event.scheduled_at - timedelta(
            hours=event.discord_subscriber_dm_hours
        )
        if now >= threshold:
            send_subscriber_notifications(event.pk)

    return "Checked reminders"


@shared_task
def send_subscriber_notifications(event_id):
    """Send DM to all repeater subscribers for an upcoming event.

    Uses create-first pattern for crash safety:
    1. Create DiscordEventDM record (delivered=False)
    2. Send DM
    3. Update record with delivery status

    Rate-limited at 1 DM/second to respect Discord limits.
    """
    import time

    from discordbot.models import DiscordEventDM, DMType
    from discordbot.utils import sync_send_dm
    from events.discord.embeds import build_subscriber_dm_embed
    from events.models import RepeaterSubscription
    from org.models import OrgUser

    try:
        event = Event.objects.select_related("event_repeater", "organization").get(
            pk=event_id
        )
    except Event.DoesNotExist:
        return f"Event {event_id} not found"

    if not event.event_repeater:
        return "No repeater"

    try:
        discord_event = event.discord_event
    except DiscordEvent.DoesNotExist:
        return "No Discord event"

    embed = build_subscriber_dm_embed(event)
    subs = RepeaterSubscription.objects.filter(
        event_repeater=event.event_repeater
    ).select_related("user")

    sent = 0
    skipped = 0
    failed = 0

    for sub in subs:
        if not sub.user.discordId:
            continue

        # Get OrgUser — skip if not a member
        org_user = OrgUser.objects.filter(
            user=sub.user, organization=event.organization
        ).first()
        if not org_user:
            continue

        # Idempotency: skip if already tracked
        if DiscordEventDM.objects.filter(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        ).exists():
            skipped += 1
            continue

        # Create record FIRST (crash safety + idempotency)
        dm_record = DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
            delivered=False,
        )

        # Send DM
        result = sync_send_dm(sub.user.discordId, embed=embed)

        # Update delivery status
        if result:
            dm_record.message_id = result.get("id", "")
            dm_record.sent_at = timezone.now()
            dm_record.delivered = True
            dm_record.save(update_fields=["message_id", "sent_at", "delivered"])
            sent += 1
        else:
            failed += 1

        time.sleep(1.0)  # Respect Discord DM rate limits

    logger.info(
        "Subscriber DMs for event %s: sent=%d, skipped=%d, failed=%d",
        event_id,
        sent,
        skipped,
        failed,
    )
    return f"Sent {sent} DMs, skipped {skipped}, failed {failed} for event {event_id}"
