import time
from datetime import datetime, timedelta
from datetime import timezone as tz

import requests as req
from celery import shared_task
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.internal_client import (
    _api_get,
    check_message_log_exists,
    claim_discord_message_log,
    clear_event_signup_state,
    create_event_dm,
    create_event_log,
    create_message_log,
    create_or_update_announcement,
    create_or_update_signup_message,
    finalize_discord_message_log,
    generate_repeater_events,
    get_active_repeaters,
    get_discord_event_state,
    get_event_for_task,
    get_event_signups,
    get_events_list,
    get_first_message_log,
    get_or_create_discord_event,
    get_repeater_subscribers,
    get_sync_discord_state,
    search_message_logs,
    transition_event_state,
    update_discord_event,
    update_event_dm,
)
from discordbot.utils import (
    DISCORD_API_BASE,
    MessageDeletedError,
    _get_headers,
    sync_edit_message,
    sync_send_dm,
    sync_send_embed_with_components,
)
from events.discord import (
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_signup_reminder_embed,
)
from events.discord.embeds import (
    build_announcement_notice,
    build_announcement_v2,
    build_subscriber_dm_embed,
)
from telemetry.logging import get_logger

logger = get_logger(__name__)
log = get_logger(__name__)


def _bind_celery_context(
    task_name: str, event_id: int, interaction_id: str | None
) -> None:
    fields = {
        "system": "discord",
        "subsystem": "celery",
        "tags": ["events", "signup"],
        "tags_csv": "events,signup",
        "event_id": event_id,
        "task": task_name,
    }
    if interaction_id is not None:
        fields["interaction_id"] = interaction_id
    bind_contextvars(**fields)


def _celery_bookend_fields(
    task_name: str, event_id: int, interaction_id: str | None, **extra
) -> dict:
    """Build kwargs dict for bookend log lines, dropping None values from interaction_id and extras."""
    fields = {
        "system": "discord",
        "subsystem": "celery",
        "tags_csv": "events,signup",
        "task": task_name,
        "event_id": event_id,
    }
    if interaction_id is not None:
        fields["interaction_id"] = interaction_id
    fields.update({k: v for k, v in extra.items() if v is not None})
    return fields


def _run_with_bookends(
    task_name: str, event_id: int, interaction_id: str | None, work, **extra
):
    """Wrap a task body with celery_task_started/finished/failed bookend logs.

    `work` is a zero-arg callable returning the task's return value. Extra
    contextvar fields (e.g. user_id) are merged into the bookend kwargs.
    """
    _bind_celery_context(task_name, event_id, interaction_id)
    fields = _celery_bookend_fields(task_name, event_id, interaction_id, **extra)
    log.info("celery_task_started", **fields)
    started = time.monotonic()
    failed = False
    try:
        return work()
    except Exception as exc:
        failed = True
        log.error(
            "celery_task_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
            **fields,
        )
        raise
    finally:
        if not failed:
            log.info(
                "celery_task_finished",
                duration_ms=round((time.monotonic() - started) * 1000),
                **fields,
            )
        clear_contextvars()


def _build_signup_message_link(guild_id, channel_id, post_result):
    """Construct a discord.com message permalink from a sync_send_embed result."""
    if not guild_id:
        return None
    if post_result.get("message"):
        thread_id = post_result["id"]
        msg_id = post_result["message"]["id"]
        return f"https://discord.com/channels/{guild_id}/{thread_id}/{msg_id}"
    msg_id = post_result["id"]
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"


def _update_signup_msg(event_id, discord_event_pk, channel_id, post_result):
    """Update signup message record via internal API after Discord post.

    Returns the resolved message_id (or None if the post had no id).
    """
    update_data = {
        "event_id": event_id,
        "channel_id": channel_id,
        "has_posted": True,
        "message_last_updated": datetime.now(tz.utc).isoformat(),
    }
    # post_result shape tells us forum-vs-text:
    #   forum: {"id": <thread_id>, "message": {"id": <msg_id>}, ...}
    #   text:  {"id": <msg_id>}
    # channel_type is the contract that downstream edit/modify paths read;
    # always set it explicitly so the worker doesn't have to infer.
    if post_result.get("message"):
        update_data["thread_id"] = post_result["id"]
        update_data["message_id"] = post_result["message"]["id"]
        update_data["channel_type"] = "forum"
    else:
        update_data["message_id"] = post_result.get("id")
        update_data["channel_type"] = "text"

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


@shared_task
def generate_upcoming_events():
    """Generate upcoming events for all active repeaters. Runs hourly.

    Calls internal API — no direct ORM access.
    """
    repeaters = get_active_repeaters()
    total = 0
    for repeater in repeaters:
        try:
            count = generate_repeater_events(repeater["pk"])
            total += count
        except Exception as e:
            logger.exception(
                "repeater_events_generate_failed",
                system="events",
                subsystem="tasks",
                repeater_id=repeater["pk"],
                error=str(e),
            )
    return f"Generated {total} events from {len(repeaters)} repeaters"


@shared_task
def cleanup_stale_events():
    """Auto-close events whose scheduled_at + 1 day has passed. Runs hourly.

    - upcoming / signups_open → cancelled (event never started)
    - roll_call / in_progress → completed (event ran but wasn't formally closed)

    State transitions go through internal HTTP API (no direct DB writes).
    """
    cutoff = (datetime.now(tz.utc) - timedelta(days=1)).isoformat()

    # Never-started events → cancelled
    never_started = get_events_list(
        states="upcoming,signups_open", scheduled_before=cutoff
    )
    cancelled_count = 0
    for event in never_started:
        try:
            resp = transition_event_state(event["id"], "cancelled")
            if resp and resp.ok:
                cancelled_count += 1
                logger.info(
                    "event_auto_cancelled",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
            else:
                logger.warning(
                    "event_auto_cancel_failed",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
        except Exception as e:
            logger.exception(
                "event_auto_cancel_error",
                system="events",
                subsystem="tasks",
                event_id=event["id"],
                error=str(e),
            )

    # Started but not closed → completed
    started = get_events_list(states="roll_call,in_progress", scheduled_before=cutoff)
    completed_count = 0
    for event in started:
        try:
            resp = transition_event_state(event["id"], "completed")
            if resp and resp.ok:
                completed_count += 1
                logger.info(
                    "event_auto_completed",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
            else:
                logger.warning(
                    "event_auto_complete_failed",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
        except Exception as e:
            logger.exception(
                "event_auto_complete_error",
                system="events",
                subsystem="tasks",
                event_id=event["id"],
                error=str(e),
            )

    return f"Cleaned up {cancelled_count} cancelled, {completed_count} completed"


@shared_task
def open_scheduled_signups():
    """Open signups for events where signups_open_at has passed. Runs every minute.

    State transition via internal HTTP API (no direct DB writes).
    """
    now = datetime.now(tz.utc).isoformat()
    events = get_events_list(states="upcoming", signups_due_before=now)
    opened = 0
    for event in events:
        try:
            resp = transition_event_state(event["id"], "signups_open")
            if resp and resp.ok:
                opened += 1
                logger.info(
                    "signups_auto_opened",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
            else:
                logger.warning(
                    "signups_auto_open_failed",
                    system="events",
                    subsystem="tasks",
                    event_id=event["id"],
                )
        except Exception as e:
            logger.exception(
                "signups_auto_open_error",
                system="events",
                subsystem="tasks",
                event_id=event["id"],
                error=str(e),
            )
    return f"Opened signups for {opened} events"


@shared_task
def sync_discord_events():
    """Reconciliation task: ensure Discord matches the DB for all active events.

    Runs every 5 minutes via celery beat. All reads via internal HTTP API.
    """
    structured_log = get_logger(__name__)

    state = get_sync_discord_state()
    if not state:
        structured_log.error(
            "sync_discord_state_fetch_failed",
            system="events",
            subsystem="discord",
        )
        return "Failed: could not fetch sync state"

    existing_logs = {tuple(x) for x in state.existing_logs}
    events_with_signup_post = set(state.events_with_signup)
    events_with_scheduled = set(state.events_with_scheduled)
    events_with_recent_attempt = set(state.events_with_recent_attempt)

    signup_posts_created = 0
    notices_created = 0
    discord_events_created = 0

    structured_log.info(
        "sync_discord_events_start",
        system="events",
        subsystem="discord",
        active_events=len(state.active_events),
        events_with_signup_post=len(events_with_signup_post),
        events_with_scheduled=len(events_with_scheduled),
        events_with_recent_attempt=len(events_with_recent_attempt),
    )

    for event in state.active_events:
        pk = event["pk"]

        # 1. Signup post — only when signups are actually open
        has_signup = (
            pk in events_with_signup_post or ("event_announcement", pk) in existing_logs
        )
        signup_eligible = (
            event["state"] == "signups_open"
            and event["discord_announcement"]
            and event["discord_announcement_channel_id"]
            and not has_signup
        )
        if signup_eligible:
            structured_log.info(
                "sync_signup_post_attempt",
                system="events",
                subsystem="discord",
                event_id=pk,
                channel_id=str(event.get("discord_announcement_channel_id") or ""),
            )
            try:
                send_event_announcement(pk)
                signup_posts_created += 1
                structured_log.info(
                    "sync_signup_post_created",
                    system="events",
                    subsystem="discord",
                    event_id=pk,
                )
            except Exception as e:
                structured_log.exception(
                    "sync_signup_post_failed",
                    system="events",
                    subsystem="discord",
                    event_id=pk,
                    error=str(e),
                )

        # 2. Discord scheduled event
        has_scheduled = (
            pk in events_with_scheduled
            or ("create_discord_event", pk) in existing_logs
            or pk in events_with_recent_attempt
        )
        sched_eligible = (
            event["discord_create_event"]
            and event["organization__discord_server_id"]
            and not has_scheduled
        )
        if sched_eligible:
            structured_log.info(
                "sync_scheduled_event_attempt",
                system="events",
                subsystem="discord",
                event_id=pk,
                guild_id=str(event.get("organization__discord_server_id") or ""),
            )
            try:
                create_discord_scheduled_event(pk)
                discord_events_created += 1
                structured_log.info(
                    "sync_scheduled_event_created",
                    system="events",
                    subsystem="discord",
                    event_id=pk,
                )
            except Exception as e:
                # create_discord_scheduled_event now raises with a Discord
                # error string (PR #222). The structlog event captures it so
                # operators can grep `sync_scheduled_event_failed` in Grafana
                # to find every silent 403/400 without DB diving.
                structured_log.exception(
                    "sync_scheduled_event_failed",
                    system="events",
                    subsystem="discord",
                    event_id=pk,
                    error=str(e),
                )

    structured_log.info(
        "sync_discord_events_complete",
        system="events",
        subsystem="discord",
        active_events=len(state.active_events),
        signup_posts_created=signup_posts_created,
        notices_created=notices_created,
        scheduled_events_created=discord_events_created,
    )
    return (
        f"Scanned {len(state.active_events)} events: "
        f"{signup_posts_created} signup posts, "
        f"{discord_events_created} scheduled events created"
    )


@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_event_announcement(event_id, interaction_id=None):
    """Create event signup post + announcement.

    1. Signup post: full embed + buttons in the signups channel (forum thread
       or regular message). This is where users sign up. Updated on changes.
    2. Announcement: lightweight message in the announcement channel linking
       to the signup post. Posted once, not updated.

    If no signups channel is configured, the signup post goes to the
    announcement channel instead (no separate announcement needed).

    All DB writes go through the internal HTTP API — no direct ORM access.
    """
    return _run_with_bookends(
        "send_event_announcement",
        event_id,
        interaction_id,
        lambda: _send_event_announcement_impl(event_id),
    )


def _send_event_announcement_impl(event_id):
    event = get_event_for_task(event_id)
    if not event:
        return f"Failed: event {event_id} not found"
    if event.state != "signups_open":
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
        logger.error(
            "discord_event_get_or_create_failed",
            system="events",
            subsystem="tasks",
            event_id=event.pk,
        )
        return "Failed: could not get/create DiscordEvent"
    discord_event_pk = de_resp.json().get("id")

    # Step 1: Create the signup post
    signup_post_result = None
    signup_message_link = None

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
                event.pk,
                discord_event_pk,
                event.discord_post_signups_channel_id,
                signup_post_result,
            )
            signup_message_link = _build_signup_message_link(
                guild_id, event.discord_post_signups_channel_id, signup_post_result
            )

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
            _update_signup_msg(
                event.pk,
                discord_event_pk,
                event.discord_announcement_channel_id,
                fallback_result,
            )

        return f"Announced event {event.pk}"

    # Step 2: Post lightweight announcement linking to the signup post
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
            message_last_updated=datetime.now(tz.utc).isoformat(),
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


@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_attendance_reminder(event_id):
    """Post the attendance-confirmation embed to the announcement channel.

    Idempotency is provided by sync_send_embed_with_components's internal
    claim/finalize lease pattern (one HTTP send per (source, source_id)).
    """
    from app.internal_client import (
        create_event_log,
        get_event_for_task,
        get_or_create_discord_event,
    )
    from discordbot.utils import sync_send_embed_with_components

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"
    if not event.discord_confirm_attendance:
        return f"Attendance reminder disabled for event {event_id}"

    result = build_attendance_reminder_embed(event)
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source="attendance_reminder",
        source_id=event.pk,
    )
    if response is None:
        return f"Attendance reminder for event {event_id}: lease held by another worker"

    # Activity Log entry — links the DiscordMessageLog row to the DiscordEvent
    guild_id = getattr(event.organization, "discord_server_id", None)
    if guild_id:
        de_resp = get_or_create_discord_event(event_id=event.pk, guild_id=guild_id)
        if de_resp and de_resp.ok:
            create_event_log(
                discord_event_id=de_resp.json().get("id"),
                action="attendance_reminder",
                target_type="DiscordMessageLog",
                message_id=response.get("id"),
                message_log_id=response.get("_message_log_id"),
                success=True,
            )

    return f"Sent attendance reminder for event {event_id}"


@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_profile_reminder(event_id):
    """Post the profile-completion reminder embed to the announcement channel.

    Idempotency via sync_send_embed_with_components's lease pattern.
    """
    from app.internal_client import (
        create_event_log,
        get_event_for_task,
        get_or_create_discord_event,
    )
    from discordbot.utils import sync_send_embed_with_components

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"
    if not event.discord_profile_reminder:
        return f"Profile reminder disabled for event {event_id}"

    result = build_profile_reminder_embed(event)
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source="profile_reminder",
        source_id=event.pk,
    )
    if response is None:
        return f"Profile reminder for event {event_id}: lease held by another worker"

    guild_id = getattr(event.organization, "discord_server_id", None)
    if guild_id:
        de_resp = get_or_create_discord_event(event_id=event.pk, guild_id=guild_id)
        if de_resp and de_resp.ok:
            create_event_log(
                discord_event_id=de_resp.json().get("id"),
                action="profile_reminder",
                target_type="DiscordMessageLog",
                message_id=response.get("id"),
                message_log_id=response.get("_message_log_id"),
                success=True,
            )

    return f"Sent profile reminder for event {event_id}"


@shared_task
def send_signup_update(event_id, interaction_id=None):
    """Edit the original announcement embed with updated signup lists.

    Tries the new DiscordEvent.signup_message first, falls back to
    DiscordMessageLog for pre-migration events.
    """
    return _run_with_bookends(
        "send_signup_update",
        event_id,
        interaction_id,
        lambda: _send_signup_update_impl(event_id, interaction_id),
    )


def _resolve_signup_edit_channel(discord_state, fields: dict) -> str | None:
    """Pick the Discord channel ID to PATCH for a signup-embed edit.

    Forum posts live inside an auto-created thread whose ID Discord treats
    as the "channel" for that message; text posts live directly in their
    channel. Driven explicitly by ``signup_channel_type`` so the worker
    doesn't have to infer from null-vs-set thread_id.

    ``fields`` is the bookend context dict (already carries event_id, task,
    system/subsystem) — pass it through so warnings correlate with the
    surrounding task spans.
    """
    channel_type = discord_state.signup_channel_type
    if channel_type == "forum":
        if not discord_state.signup_thread_id:
            log.warning(
                "forum_post_missing_thread_id",
                signup_message_id=discord_state.signup_message_id,
                signup_channel_id=discord_state.signup_channel_id,
                **fields,
            )
            return discord_state.signup_channel_id
        return discord_state.signup_thread_id
    if channel_type == "text":
        return discord_state.signup_channel_id
    log.warning(
        "legacy_channel_type",
        signup_message_id=discord_state.signup_message_id,
        has_thread_id=bool(discord_state.signup_thread_id),
        **fields,
    )
    return discord_state.signup_thread_id or discord_state.signup_channel_id


def _send_signup_update_impl(event_id, interaction_id):
    fields = _celery_bookend_fields("send_signup_update", event_id, interaction_id)

    event = get_event_for_task(event_id)
    if not event:
        log.warning("signup_update_event_not_found", **fields)
        return f"Failed: event {event_id} not found"

    # Edit-routing recap (matches DiscordEventStateSchema docstring):
    # - channel_type="text"  -> PATCH /channels/{channel_id}/messages/{message_id}
    # - channel_type="forum" -> PATCH /channels/{thread_id}/messages/{message_id}
    # - channel_type=None    -> legacy row; fall back to thread_id or channel_id
    #   and log so we can backfill via a migration.
    edit_channel_id = None
    message_id = None
    signup_msg = None
    discord_event = None

    discord_state = get_discord_event_state(event_id)
    if (
        discord_state
        and discord_state.signup_posted
        and discord_state.signup_message_id
    ):
        message_id = discord_state.signup_message_id
        edit_channel_id = _resolve_signup_edit_channel(discord_state, fields)

    # Fall back to DiscordMessageLog for pre-migration events
    if not message_id:
        logs = search_message_logs(
            source="event_announcement",
            source_id=event.pk,
            success="true",
            limit=1,
        )
        log_entry = logs[0] if logs else None

        if not log_entry or not log_entry.discord_message_id:
            logger.info(
                "signup_update_no_announcement",
                system="events",
                subsystem="tasks",
                event_id=event.pk,
            )
            return "Skipped: no announcement message"

        message_id = log_entry.discord_message_id
        edit_channel_id = log_entry.channel_id
        response_data = log_entry.response_data or {}
        if response_data.get("id") and response_data.get("message"):
            edit_channel_id = response_data.get("id")

    result = build_announcement_v2(event)

    # Edit the message. sync_edit_message raises MessageDeletedError on the
    # specific "the post is gone" case (Discord 404 + code 10008) and returns
    # None for other transient failures. Treat the typed exception as a
    # signal to clear dedup state so the next sync recreates the post.
    edit_response = None
    try:
        edit_response = sync_edit_message(
            channel_id=edit_channel_id,
            message_id=message_id,
            embed=result["embeds"],
            components=result["components"],
        )
    except MessageDeletedError:
        clear_event_signup_state(event_id=event.pk)
        log.warning(
            "signup_message_orphaned_recovered",
            channel_id=str(edit_channel_id),
            message_id=str(message_id),
            reason="discord_404_unknown_message",
            **fields,
        )
        return f"Recovered: cleared dedup for event {event.pk} (orphaned message)"

    # Update tracking via internal API
    if signup_msg:
        create_or_update_signup_message(
            event_id=event.pk,
            channel_id=signup_msg.channel_id,
            message_last_updated=datetime.now(tz.utc).isoformat(),
        )

        if discord_event:
            create_event_log(
                discord_event_id=discord_event.pk,
                action="edit_signup_post",
                target_type="DiscordEventMsgSignup",
                message_id=message_id,
                success=edit_response is not None,
            )

    return f"Updated announcement for event {event.pk}"


@shared_task
def send_new_event_notification(event_id, interaction_id=None):
    """Notify Discord channel about a new event from a repeater."""
    return _run_with_bookends(
        "send_new_event_notification",
        event_id,
        interaction_id,
        lambda: _send_new_event_notification_impl(event_id),
    )


def _send_new_event_notification_impl(event_id: int) -> str:
    event = get_event_for_task(event_id)
    if not event:
        return f"Failed: event {event_id} not found"
    if not event.discord_announcement or not event.discord_announcement_channel_id:
        return "Skipped: announcements disabled"

    embed = build_new_event_embed(event)
    # Lease-wrapped send: claims (new_event, event_id) before the HTTP POST, so a
    # retry or double dispatch can't double-post the embed.
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=embed,
        source="new_event",
        source_id=event.pk,
    )
    if response is None:
        logger.info(
            "new_event_notification_not_sent",
            system="events",
            subsystem="tasks",
            event_id=event_id,
            reason="lease_held_by_another_worker",
        )
        return (
            f"New event notification for event {event_id}: lease held by another worker"
        )
    return f"Notified new event {event.pk}"


@shared_task
def create_discord_scheduled_event(event_id, interaction_id=None):
    """Create a Discord scheduled event via the API.

    Stores the scheduled_event_id on the DiscordEvent model and creates
    audit log entries — all via internal HTTP API (no direct DB writes).
    """
    return _run_with_bookends(
        "create_discord_scheduled_event",
        event_id,
        interaction_id,
        lambda: _create_discord_scheduled_event_impl(event_id),
    )


def _create_discord_scheduled_event_impl(event_id):
    event = get_event_for_task(event_id)
    if not event:
        return f"Failed: event {event_id} not found"
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
        logger.error(
            "discord_event_get_or_create_failed",
            system="events",
            subsystem="tasks",
            event_id=event.pk,
        )
        return "Failed: could not get/create DiscordEvent"
    discord_event_pk = de_resp.json().get("id")

    try:
        response = req.post(url, json=payload, headers=_get_headers())
        data = response.json()
        success = response.status_code in (200, 201)

        # Extract the Discord-side error message from the response body
        # (`{"message": "Missing Permissions", "code": 50013}` etc.) so the
        # audit log surfaces it without anyone having to dig through
        # response_data JSON. Default to the raw status when Discord
        # didn't send a structured body.
        error_message = ""
        if not success:
            if isinstance(data, dict) and data.get("message"):
                error_message = (
                    f"{data['message']} (code {data.get('code', '?')}, "
                    f"HTTP {response.status_code})"
                )
            else:
                error_message = f"HTTP {response.status_code}"

        # Legacy log via internal API
        create_message_log(
            channel_id=guild_id,
            embed_data=payload,
            source="create_discord_event",
            source_id=event.pk,
            discord_message_id=data.get("id") if isinstance(data, dict) else None,
            status_code=response.status_code,
            response_data=data,
            success=success,
        )

        # Store scheduled event ID via internal API
        if success and isinstance(data, dict) and data.get("id"):
            update_discord_event(discord_event_pk, scheduled_event_id=data["id"])

        # Audit log via internal API
        create_event_log(
            discord_event_id=discord_event_pk,
            action="create_scheduled_event",
            target_type="DiscordEvent",
            status_code=response.status_code,
            response_data=data,
            success=success,
            error_message=error_message,
        )

        if not success:
            # Raise so the caller (sync_discord_events) logs an accurate
            # "Sync: failed Discord scheduled event ..." line instead of
            # "Sync: created ..." — the silent-success bug that caused 20+
            # invisible 403 Missing-Permissions failures on prod (0.9.49).
            logger.error(
                "discord_scheduled_event_create_failed",
                system="events",
                subsystem="tasks",
                event_id=event.pk,
                reason=error_message,
            )
            raise RuntimeError(
                f"Discord scheduled-event create failed for event {event.pk}: "
                f"{error_message}"
            )

        return f"Created Discord event for event {event.pk}"
    except RuntimeError:
        # Pass through — already logged + DiscordEventLog written above.
        # Without this filter, the broader except below would double-log and
        # turn the RuntimeError into a "Failed: ..." return string, swallowing
        # the signal the caller (sync_discord_events) relies on.
        raise
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
            "discord_scheduled_event_create_error",
            system="events",
            subsystem="tasks",
            event_id=event.pk,
            error=str(e),
        )
        return f"Failed: {e}"


@shared_task
def delete_discord_scheduled_event(guild_id: str, scheduled_event_id: str) -> str:
    """Delete a live Discord guild scheduled event.

    Idempotent: a 404 (already gone) counts as success. Nothing else in the app
    removes scheduled events, so this must run whenever an Event or its series is
    deleted — otherwise the event is orphaned on the guild and sync_discord_events
    keeps it alive as a "ghost".
    """
    if not guild_id or not scheduled_event_id:
        return "Skipped: missing guild_id or scheduled_event_id"
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events/{scheduled_event_id}"
    try:
        response = req.delete(url, headers=_get_headers())
        if response.status_code not in (204, 404):
            logger.error(
                "discord_scheduled_event_delete_failed",
                system="events",
                subsystem="tasks",
                guild_id=guild_id,
                scheduled_event_id=scheduled_event_id,
                status_code=response.status_code,
            )
        return (
            f"Deleted Discord scheduled event {scheduled_event_id} "
            f"(HTTP {response.status_code})"
        )
    except Exception as e:
        logger.exception(
            "discord_scheduled_event_delete_error",
            system="events",
            subsystem="tasks",
            guild_id=guild_id,
            scheduled_event_id=scheduled_event_id,
            error=str(e),
        )
        return f"Failed: {e}"


@shared_task
def sync_discord_event_signups(event_id, interaction_id=None):
    """Sync signup count to Discord scheduled event description."""
    return _run_with_bookends(
        "sync_discord_event_signups",
        event_id,
        interaction_id,
        lambda: _sync_discord_event_signups_impl(event_id),
    )


def _sync_discord_event_signups_impl(event_id):
    event = get_event_for_task(event_id)
    if not event:
        return f"Failed: event {event_id} not found"
    if not event.discord_sync_signups:
        return "Skipped: sync disabled"
    creation_log = get_first_message_log("create_discord_event", event.pk)
    if not creation_log or not creation_log.discord_message_id:
        return "Skipped: no Discord event found"

    guild_id = event.organization.discord_server_id
    discord_event_id = creation_log.discord_message_id
    active, confirmed = event.signup_count, event.confirmed_count
    payload = {
        "description": (
            f"{event.description or ''}\n\n"
            f"Signups: {active}/{event.max_players or '∞'} | Confirmed: {confirmed}"
        ),
    }
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events/{discord_event_id}"
    try:
        response = req.patch(url, json=payload, headers=_get_headers())
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
        logger.exception(
            "discord_signups_sync_error",
            system="events",
            subsystem="tasks",
            event_id=event.pk,
            error=str(e),
        )
        return f"Failed: {e}"


@shared_task
def mark_interested_discord_event(event_id, user_id, interaction_id=None):
    """Mark a user as 'interested' on the Discord scheduled event."""
    return _run_with_bookends(
        "mark_interested_discord_event",
        event_id,
        interaction_id,
        lambda: _mark_interested_discord_event_impl(event_id, user_id),
        user_id=user_id,
    )


def _mark_interested_discord_event_impl(event_id, user_id):
    event = get_event_for_task(event_id)
    if not event:
        return f"Failed: event {event_id} not found"
    if not event.discord_mark_interested:
        return "Skipped: mark_interested disabled"

    user_resp = _api_get(f"/users/{user_id}/")
    if not user_resp or not user_resp.ok:
        return f"Skipped: user {user_id} not found"
    user_data = user_resp.json()
    discord_id = user_data.get("discordId")
    if not discord_id:
        return "Skipped: user has no discordId"

    creation_log = get_first_message_log("create_discord_event", event.pk)
    if not creation_log or not creation_log.discord_message_id:
        return "Skipped: no Discord event found"

    guild_id = event.organization.discord_server_id
    discord_event_id = creation_log.discord_message_id
    url = (
        f"{DISCORD_API_BASE}/guilds/{guild_id}/scheduled-events"
        f"/{discord_event_id}/users/{discord_id}"
    )
    try:
        response = req.put(url, headers=_get_headers())
        return f"Marked user {user_id} interested: {response.status_code}"
    except Exception as e:
        logger.exception(
            "discord_mark_interested_error",
            system="events",
            subsystem="tasks",
            event_id=event.pk,
            user_id=user_id,
            error=str(e),
        )
        return f"Failed: {e}"


@shared_task
def fire_event_reminder(event_id, reminder_type, fired_by_user_id=None):
    """Manually fire a specific reminder for a specific event.

    Bypasses time threshold checks but respects idempotency via message log.
    Called from the admin "Fire" button, not from celery beat.
    """
    from app.internal_client import (
        create_event_log,
        get_or_create_discord_event,
    )
    from discordbot.utils import sync_send_embed_with_components
    from events.discord import (
        build_profile_reminder_embed,
    )

    REMINDER_MAP = {
        "signup_reminder": ("signup_reminder", build_signup_reminder_embed),
        "confirm_attendance": ("attendance_reminder", build_attendance_reminder_embed),
        "profile_reminder": ("profile_reminder", build_profile_reminder_embed),
    }

    if reminder_type not in REMINDER_MAP:
        return f"Unknown reminder type: {reminder_type}"

    source, builder = REMINDER_MAP[reminder_type]

    # Idempotency check
    if check_message_log_exists(source, event_id):
        return f"Already fired: {reminder_type} for event {event_id}"

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"

    if not event.discord_announcement_channel_id:
        return f"No announcement channel configured for event {event_id}"

    result = builder(event)
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source=source,
        source_id=event.pk,
        fired_by_user_id=fired_by_user_id,
    )

    # Log to DiscordEventLog so it shows in the Activity Log tab
    guild_id = event.organization.discord_server_id
    if guild_id:
        de_resp = get_or_create_discord_event(event_id=event.pk, guild_id=guild_id)
        if de_resp and de_resp.ok:
            discord_event_pk = de_resp.json().get("id")
            msg_id = response.get("id") if response else None
            msg_log_id = response.get("_message_log_id") if response else None
            create_event_log(
                discord_event_id=discord_event_pk,
                action=source,
                target_type="DiscordMessageLog",
                message_id=msg_id,
                message_log_id=msg_log_id,
                success=bool(response),
            )

    return f"Fired {reminder_type} for event {event_id}"


@shared_task(acks_late=True, reject_on_worker_lost=True)
def check_event_reminders():
    """Beat-scheduled every 30s. Delegates to the registry-driven fire path.

    All reminder dispatch logic now lives in events.scheduling.fire — the
    polling task is a thin wrapper so beat re-uses its existing schedule
    name and cadence.

    Idempotency:
        DiscordMessageLog IS cached by cacheops (60-min TTL, invalidated
        on insert). The check_message_log_exists short-circuit in
        fire_due_reminders is a load-shedder — most polls hit it and skip
        dispatch entirely. The actual correctness primitive is the partial
        unique index on (source, source_id) WHERE success IS NOT FALSE,
        which raises IntegrityError if two workers race past the cached
        exists() check. Stale leases (NULL >5min, False >1hr) are reaped
        by sweep_stale_discord_leases.
    """
    from events.scheduling.fire import fire_due_reminders

    return fire_due_reminders()


@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_subscriber_notifications(event_id):
    """Send signup reminder DMs to repeater subscribers who haven't signed up.

    Wraps the entire subscriber-DM loop in a lease so concurrent dispatches
    cannot iterate the subscriber set twice. The lease row uses channel_id="dm"
    as a sentinel (DMs aren't per-channel) and the common signup-reminder
    embed as embed_data — the partial unique constraint keys on
    (source="signup_reminder", source_id=event_id) only.

    Filters out subscribers who already have an EventSignup for this event.
    Uses create-first pattern for crash safety:
    1. Create DiscordEventDM record (delivered=False)
    2. Send DM
    3. Update record with delivery status

    Rate-limited at 1 DM/second to respect Discord limits.
    """

    from app.internal_client import (
        get_discord_event_state,
        get_event_for_task,
    )

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"

    if not event.event_repeater_id:
        return "No repeater"

    # Check Discord event exists
    discord_state = get_discord_event_state(event_id)
    if not discord_state or not discord_state.has_discord_event:
        return "No Discord event"
    discord_event_pk = discord_state.discord_event_pk

    # Build embed up front (used both as the lease payload AND each subscriber DM)
    dm_data = build_subscriber_dm_embed(event)
    embed = dm_data["embed"]
    components = dm_data.get("components")

    # Claim the lease BEFORE iterating subscribers. Concurrent dispatches
    # of this task hit the partial unique constraint and return None — exit
    # cleanly so we don't double-DM the entire subscriber set.
    log_pk = claim_discord_message_log(
        source="signup_reminder",
        source_id=event_id,
        channel_id="dm",
        embed_data=embed,
    )
    if log_pk is None:
        logger.info(
            "signup_reminder_lease_held",
            system="events",
            subsystem="tasks",
            event_id=event_id,
            reason="lease_held_by_another_worker",
        )
        return f"Signup reminder for event {event_id}: lease held by another worker"

    # Get user PKs who already signed up — skip them

    all_signups = get_event_signups(event_id)
    signed_up_user_pks = {s.user for s in all_signups if s.status != "cancelled"}

    subscribers = get_repeater_subscribers(event.event_repeater_id)

    sent = 0
    skipped = 0
    failed = 0

    try:
        for sub in subscribers:
            # Skip subscribers who already signed up
            if sub.user_pk in signed_up_user_pks:
                skipped += 1
                continue

            # Create DM record via internal API (crash safety + idempotency)
            from discordbot.models import DMType

            dm_pk = None
            if sub.org_user_pk:
                dm_resp = create_event_dm(
                    discord_event=discord_event_pk,
                    org_user=sub.org_user_pk,
                    dm_type=DMType.SIGNUP_REMINDER,
                    delivered=False,
                )
                if not dm_resp or not dm_resp.ok:
                    # Likely already exists (idempotency) or error
                    skipped += 1
                    continue
                dm_pk = dm_resp.json().get("id")

            # Send DM
            result = sync_send_dm(sub.discord_id, embed=embed, components=components)

            # Update delivery status via internal API
            if result:
                if dm_pk:
                    update_event_dm(
                        dm_pk,
                        message_id=result.get("id", ""),
                        sent_at=datetime.now(tz.utc).isoformat(),
                        delivered=True,
                    )
                sent += 1
            else:
                failed += 1
    except Exception as exc:
        # Finalize as failure so the sweeper ages this out and admins can
        # investigate via the row's response_data
        finalize_discord_message_log(
            log_pk,
            success=False,
            response_data={
                "error": str(exc),
                "sent": sent,
                "skipped": skipped,
                "failed": failed,
            },
        )
        raise

    # success=True only if at least one DM was actually delivered;
    # all-failed marks success=False so the sweeper can age it out and
    # the next poll can retry.
    finalize_discord_message_log(
        log_pk,
        success=sent > 0,
        response_data={
            "type": "signup_reminder_batch",
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        },
    )

    logger.info(
        "signup_reminder_dms_sent",
        system="events",
        subsystem="tasks",
        event_id=event_id,
        sent=sent,
        skipped=skipped,
        failed=failed,
    )
    return f"Sent {sent} DMs, skipped {skipped}, failed {failed} for event {event_id}"
