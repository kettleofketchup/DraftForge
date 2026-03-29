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
def cleanup_stale_events():
    """Auto-close events whose scheduled_at + 1 day has passed. Runs hourly.

    - upcoming / signups_open → cancelled (event never started)
    - roll_call / in_progress → completed (event ran but wasn't formally closed)

    State transitions go through internal HTTP API (no direct DB writes).
    """
    from datetime import timedelta

    from app.internal_client import transition_event_state

    cutoff = timezone.now() - timedelta(days=1)

    # Never-started events → cancelled
    never_started = Event.objects.filter(
        state__in=[EventState.UPCOMING, EventState.SIGNUPS_OPEN],
        scheduled_at__lt=cutoff,
    )
    cancelled_count = 0
    for event in never_started:
        try:
            resp = transition_event_state(event.pk, "cancelled")
            if resp and resp.ok:
                cancelled_count += 1
                logger.info(
                    "Auto-cancelled stale event %s (pk=%s)", event.name, event.pk
                )
            else:
                logger.warning("Failed to auto-cancel event %s: %s", event.pk, resp)
        except Exception:
            logger.exception("Failed to auto-cancel event %s", event.pk)

    # Started but not closed → completed
    started = Event.objects.filter(
        state__in=[EventState.ROLL_CALL, EventState.IN_PROGRESS],
        scheduled_at__lt=cutoff,
    )
    completed_count = 0
    for event in started:
        try:
            resp = transition_event_state(event.pk, "completed")
            if resp and resp.ok:
                completed_count += 1
                logger.info(
                    "Auto-completed stale event %s (pk=%s)", event.name, event.pk
                )
            else:
                logger.warning("Failed to auto-complete event %s: %s", event.pk, resp)
        except Exception:
            logger.exception("Failed to auto-complete event %s", event.pk)

    return f"Cleaned up {cancelled_count} cancelled, {completed_count} completed"


@shared_task
def open_scheduled_signups():
    """Open signups for events where signups_open_at has passed. Runs every minute.

    State transition via internal HTTP API (no direct DB writes).
    """
    from app.internal_client import transition_event_state

    now = timezone.now()
    events = Event.objects.filter(
        state=EventState.UPCOMING,
        signups_open_at__isnull=False,
        signups_open_at__lte=now,
    )
    opened = 0
    for event in events:
        try:
            resp = transition_event_state(event.pk, "signups_open")
            if resp and resp.ok:
                opened += 1
                logger.info(
                    "Auto-opened signups for event %s (pk=%s)", event.name, event.pk
                )
            else:
                logger.warning(
                    "Failed to auto-open signups for event %s: %s", event.pk, resp
                )
        except Exception:
            logger.exception("Failed to auto-open signups for event %s", event.pk)
    return f"Opened signups for {opened} events"


@shared_task
def sync_discord_events():
    """Reconciliation task: ensure Discord matches the DB for all active events.

    Runs every 5 minutes via celery beat. All reads via internal HTTP API.
    """
    from app.internal_client import get_sync_discord_state

    state = get_sync_discord_state()
    if not state:
        logger.error("Failed to fetch sync Discord state from internal API")
        return "Failed: could not fetch sync state"

    existing_logs = {tuple(x) for x in state["existing_logs"]}
    events_with_signup_post = set(state["events_with_signup"])
    events_with_scheduled = set(state["events_with_scheduled"])
    events_with_recent_attempt = set(state["events_with_recent_attempt"])

    signup_posts_created = 0
    notices_created = 0
    discord_events_created = 0

    for event in state["active_events"]:
        pk = event["pk"]

        # 1. Signup post — only when signups are actually open
        has_signup = (
            pk in events_with_signup_post or ("event_announcement", pk) in existing_logs
        )
        if (
            event["state"] == "signups_open"
            and event["discord_announcement"]
            and event["discord_announcement_channel_id"]
            and not has_signup
        ):
            try:
                send_event_announcement(pk)
                signup_posts_created += 1
                logger.info("Sync: created signup post for event %s", pk)
            except Exception:
                logger.exception("Sync: failed signup post for event %s", pk)

        # 2. Discord scheduled event
        has_scheduled = (
            pk in events_with_scheduled
            or ("create_discord_event", pk) in existing_logs
            or pk in events_with_recent_attempt
        )
        if (
            event["discord_create_event"]
            and event["organization__discord_server_id"]
            and not has_scheduled
        ):
            try:
                create_discord_scheduled_event(pk)
                discord_events_created += 1
                logger.info("Sync: created Discord scheduled event for event %s", pk)
            except Exception:
                logger.exception(
                    "Sync: failed Discord scheduled event for event %s", pk
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

    All DB writes go through the internal HTTP API — no direct ORM access.
    """
    from app.internal_client import (
        create_event_log,
        create_or_update_announcement,
        create_or_update_signup_message,
        get_or_create_discord_event,
        update_discord_event,
    )
    from discordbot.utils import sync_send_embed_with_components
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

    # Get or create DiscordEvent via internal API
    de_resp = get_or_create_discord_event(event_id=event.pk, guild_id=guild_id or "")
    if not de_resp or not de_resp.ok:
        logger.error("Failed to get/create DiscordEvent for event %s", event.pk)
        return "Failed: could not get/create DiscordEvent"
    discord_event_pk = de_resp.json().get("id")

    # Step 1: Create the signup post
    signup_post_result = None
    signup_message_link = None

    def _update_signup_msg(channel_id, post_result):
        """Update signup message record via internal API after Discord post."""
        update_data = {
            "event_id": event.pk,
            "channel_id": channel_id,
            "has_posted": True,
            "message_last_updated": timezone.now().isoformat(),
        }
        if post_result.get("message"):
            update_data["thread_id"] = post_result["id"]
            update_data["message_id"] = post_result["message"]["id"]
            update_data["channel_type"] = "forum"
        else:
            update_data["message_id"] = post_result.get("id")

        msg_resp = create_or_update_signup_message(**update_data)
        signup_msg_pk = msg_resp.json().get("id") if msg_resp and msg_resp.ok else None

        if signup_msg_pk:
            update_discord_event(discord_event_pk, signup_message_id=signup_msg_pk)
            create_event_log(
                discord_event_id=discord_event_pk,
                action="send_signup_post",
                target_type="DiscordEventMsgSignup",
                message_id=update_data.get("message_id"),
                success=True,
            )
        return update_data.get("message_id")

    if event.discord_post_signups and event.discord_post_signups_channel_id:
        # Signups channel configured — post there (forum thread or regular)
        # DiscordMessageLog is written by sync_send_embed_with_components via HTTP
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
            _update_signup_msg(
                event.discord_post_signups_channel_id, signup_post_result
            )

            if guild_id:
                if signup_post_result.get("message"):
                    thread_id = signup_post_result["id"]
                    msg_id = signup_post_result["message"]["id"]
                    signup_message_link = (
                        f"https://discord.com/channels/{guild_id}/{thread_id}/{msg_id}"
                    )
                else:
                    msg_id = signup_post_result["id"]
                    signup_message_link = f"https://discord.com/channels/{guild_id}/{event.discord_post_signups_channel_id}/{msg_id}"

    if not signup_post_result:
        # No signups channel or it failed — post to announcement channel
        fallback_result = sync_send_embed_with_components(
            channel_id=event.discord_announcement_channel_id,
            embed=embeds,
            components=components,
            source="event_announcement",
            source_id=event.pk,
        )

        if fallback_result:
            _update_signup_msg(event.discord_announcement_channel_id, fallback_result)

        return f"Announced event {event.pk}"

    # Step 2: Post lightweight announcement linking to the signup post
    from events.discord.embeds import build_announcement_notice

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
        ann_resp = create_or_update_announcement(
            event_id=event.pk,
            channel_id=event.discord_announcement_channel_id,
            has_posted=True,
            message_id=notice_api_result.get("id"),
            message_last_updated=timezone.now().isoformat(),
        )
        ann_pk = ann_resp.json().get("id") if ann_resp and ann_resp.ok else None
        if ann_pk:
            update_discord_event(discord_event_pk, announcement_id=ann_pk)
            create_event_log(
                discord_event_id=discord_event_pk,
                action="send_announcement_notice",
                target_type="DiscordEventMsgAnnouncement",
                message_id=notice_api_result.get("id"),
                success=True,
            )

    return f"Announced event {event.pk} (signup: {signup_message_link})"


@shared_task
def send_signup_update(event_id):
    """Edit the original announcement embed with updated signup lists.

    Tries the new DiscordEvent.signup_message first, falls back to
    DiscordMessageLog for pre-migration events.
    """
    from app.internal_client import create_event_log, create_or_update_signup_message
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

    # Update tracking via internal API
    if signup_msg:
        create_or_update_signup_message(
            event_id=event.pk,
            channel_id=signup_msg.channel_id,
            message_last_updated=timezone.now().isoformat(),
        )

        if discord_event:
            create_event_log(
                discord_event_id=discord_event.pk,
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

    Stores the scheduled_event_id on the DiscordEvent model and creates
    audit log entries — all via internal HTTP API (no direct DB writes).
    """
    from datetime import timedelta

    import requests as req

    from app.internal_client import (
        create_event_log,
        create_message_log,
        get_or_create_discord_event,
        update_discord_event,
    )
    from discordbot.utils import DISCORD_API_BASE, _get_headers

    event = Event.objects.select_related("organization").get(pk=event_id)
    if not event.discord_create_event:
        return "Skipped: discord_create_event disabled"
    guild_id = event.organization.discord_server_id
    if not guild_id:
        return "Skipped: no discord_server_id on organization"

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

    # Get or create DiscordEvent via internal API
    de_resp = get_or_create_discord_event(event_id=event.pk, guild_id=guild_id)
    if not de_resp or not de_resp.ok:
        logger.error("Failed to get/create DiscordEvent for event %s", event.pk)
        return "Failed: could not get/create DiscordEvent"
    discord_event_pk = de_resp.json().get("id")

    try:
        response = req.post(url, json=payload, headers=_get_headers())
        data = response.json()
        success = response.status_code in (200, 201)

        # Legacy log via internal API
        create_message_log(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            discord_message_id=data.get("id"),
            status_code=response.status_code,
            response_data=data,
            success=success,
        )

        # Store scheduled event ID via internal API
        if success and data.get("id"):
            update_discord_event(discord_event_pk, scheduled_event_id=data["id"])

        # Audit log via internal API
        create_event_log(
            discord_event_id=discord_event_pk,
            action="create_scheduled_event",
            target_type="DiscordEvent",
            status_code=response.status_code,
            response_data=data,
            success=success,
        )

        return f"Created Discord event for event {event.pk}"
    except Exception as e:
        create_message_log(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            success=False,
        )
        create_event_log(
            discord_event_id=discord_event_pk,
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
        from app.internal_client import create_message_log

        create_message_log(
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

    from app.internal_client import check_message_log_exists

    # 1. Signup reminders
    signup_reminder_events = Event.objects.filter(
        state__in=[EventState.SIGNUPS_OPEN],
        discord_signup_reminder=True,
        discord_announcement_channel_id__gt="",
    )
    for event in signup_reminder_events:
        if check_message_log_exists("signup_reminder", event.pk):
            continue
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
    )
    for event in attendance_events:
        if check_message_log_exists("attendance_reminder", event.pk):
            continue
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
    )
    for event in profile_events:
        if check_message_log_exists("profile_reminder", event.pk):
            continue
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

        # Create record FIRST via internal API (crash safety + idempotency)
        from app.internal_client import create_event_dm, update_event_dm

        dm_resp = create_event_dm(
            discord_event=discord_event.pk,
            org_user=org_user.pk,
            dm_type=DMType.SIGNUP_REMINDER,
            delivered=False,
        )
        dm_pk = dm_resp.json().get("id") if dm_resp and dm_resp.ok else None

        # Send DM
        result = sync_send_dm(sub.user.discordId, embed=embed)

        # Update delivery status via internal API
        if result and dm_pk:
            update_event_dm(
                dm_pk,
                message_id=result.get("id", ""),
                sent_at=timezone.now().isoformat(),
                delivered=True,
            )
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
