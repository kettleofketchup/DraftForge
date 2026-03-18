"""
Event <-> Discord integration layer.

Embed builders (pure functions) and dispatch functions that check config flags
and send Celery tasks for Discord notifications.
"""

import logging

from django.conf import settings

from events.models import EventSignup, SignupStatus

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, "SITE_URL", "")

# Colors
COLOR_ANNOUNCEMENT = 0x5865F2  # Discord blurple
COLOR_SIGNUP = 0x57F287  # Green
COLOR_REMINDER = 0xFEE75C  # Yellow
COLOR_PROFILE = 0xEB459E  # Fuchsia
COLOR_NEW_EVENT = 0x00B0F4  # Cyan


def _discord_timestamp(dt, style="F"):
    """Format a datetime as a Discord timestamp. Style: F=full, R=relative, t=time, d=date."""
    return f"<t:{int(dt.timestamp())}:{style}>"


def _event_url(event):
    return (
        f"{SITE_URL}/org/{event.organization_id}/events/{event.pk}" if SITE_URL else ""
    )


def _signup_counts(event):
    signups = EventSignup.objects.filter(event=event)
    active = signups.exclude(
        status__in=[
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.WAITLISTED,
        ]
    ).count()
    confirmed = signups.filter(status=SignupStatus.CONFIRMED).count()
    return active, confirmed


def build_announcement_embed(event):
    """Build embed for event announcement with signup lists."""
    title = event.discord_event_title or event.name
    desc = event.discord_event_description or event.description or "No description."

    if event.discord_event_info:
        desc += f"\n\n{event.discord_event_info}"

    if url := _event_url(event):
        desc += f"\n\n[View Event]({url})"

    fields = [
        {
            "name": "When",
            "value": _discord_timestamp(event.scheduled_at),
            "inline": True,
        },
        {
            "name": "Max Players",
            "value": str(event.max_players or "Unlimited"),
            "inline": True,
        },
    ]

    # Add signup list fields
    signups = EventSignup.objects.filter(event=event).select_related("user")

    # Left column: confirmed/approved (✅) + pending (⏳)
    active = signups.exclude(
        status__in=[
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.WAITLISTED,
        ]
    )
    if active.exists():
        lines = []
        for s in active[:20]:
            icon = (
                "✅"
                if s.status in (SignupStatus.CONFIRMED, SignupStatus.APPROVED)
                else "⏳"
            )
            name = s.user.nickname or s.user.username or f"User {s.user.pk}"
            lines.append(f"{icon} {name}")
        remaining = active.count() - 20
        if remaining > 0:
            lines.append(f"*and {remaining} more...*")
        count = active.count()
        max_display = str(event.max_players) if event.max_players else "∞"
        fields.append(
            {
                "name": f"Signed Up ({count}/{max_display})",
                "value": "\n".join(lines),
                "inline": True,
            }
        )

    # Right column: waitlisted
    waitlisted = signups.filter(status=SignupStatus.WAITLISTED).order_by(
        "waitlist_position"
    )
    if waitlisted.exists():
        lines = []
        for s in waitlisted[:20]:
            name = s.user.nickname or s.user.username or f"User {s.user.pk}"
            lines.append(name)
        remaining = waitlisted.count() - 20
        if remaining > 0:
            lines.append(f"*and {remaining} more...*")
        fields.append(
            {
                "name": f"Waitlisted ({waitlisted.count()})",
                "value": "\n".join(lines),
                "inline": True,
            }
        )

    return {
        "title": f"📢 {title}",
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "fields": fields,
        "timestamp": event.scheduled_at.isoformat(),
    }


def build_signup_update_embed(event):
    active, confirmed = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
    return {
        "title": f"📋 {event.name} — Signups",
        "description": f"Players: **{active}/{max_display}**",
        "color": COLOR_SIGNUP,
        "fields": [
            {"name": "Signed Up", "value": str(active), "inline": True},
            {"name": "Confirmed", "value": str(confirmed), "inline": True},
        ],
    }


def build_new_event_embed(event):
    desc = f"A new event has been created for **{event.organization.name}**!"
    if url := _event_url(event):
        desc += f"\n\n[Sign Up]({url})"
    return {
        "title": f"🆕 {event.name}",
        "description": desc,
        "color": COLOR_NEW_EVENT,
        "fields": [
            {
                "name": "When",
                "value": _discord_timestamp(event.scheduled_at),
                "inline": True,
            },
        ],
    }


def build_signup_reminder_embed(event):
    active, _ = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
    return {
        "title": f"⏰ {event.name} — Signup Reminder",
        "description": f"Don't forget to sign up! Currently **{active}/{max_display}** players.",
        "color": COLOR_REMINDER,
    }


def build_attendance_reminder_embed(event):
    return {
        "title": f"✋ {event.name} — Confirm Attendance",
        "description": "The event is coming up! Please confirm your attendance.",
        "color": COLOR_REMINDER,
    }


def build_profile_reminder_embed(event):
    requirements = []
    if event.require_steam_id:
        requirements.append("Steam ID")
    if event.require_mmr_verified:
        requirements.append("Verified MMR")
    if event.require_profile_complete:
        requirements.append("Complete profile")
    req_text = ", ".join(requirements) if requirements else "a complete profile"
    return {
        "title": f"👤 {event.name} — Complete Your Profile",
        "description": f"Please make sure you have: {req_text}",
        "color": COLOR_PROFILE,
    }


# ---------------------------------------------------------------------------
# Dispatch functions — check config flags and call .delay()
#
# IMPORTANT: These dispatch functions call .delay() which publishes to Redis
# immediately. When called from inside @transaction.atomic services, the caller
# MUST wrap in transaction.on_commit() to ensure data is committed before the
# Celery worker reads it. See Task 5 for the wiring pattern.
#
# Exception: generate_events_for_repeater() is NOT atomic, so direct calls
# are safe there.
# ---------------------------------------------------------------------------


def notify_event_announced(event):
    """Dispatch announcement task if discord_announcement is enabled."""
    if event.discord_announcement and event.discord_announcement_channel_id:
        from events.tasks import send_event_announcement

        send_event_announcement.delay(event.pk)


def notify_signup_changed(event):
    """Dispatch signup update task if discord_post_signups is enabled."""
    if event.discord_post_signups and event.discord_post_signups_channel_id:
        from events.tasks import send_signup_update

        send_signup_update.delay(event.pk)


def notify_new_event(event):
    """Dispatch new event notification if discord_announcement is enabled."""
    if event.discord_announcement and event.discord_announcement_channel_id:
        from events.tasks import send_new_event_notification

        send_new_event_notification.delay(event.pk)


def notify_create_discord_event(event):
    """Dispatch Discord scheduled event creation if enabled."""
    if event.discord_create_event:
        from events.tasks import create_discord_scheduled_event

        create_discord_scheduled_event.delay(event.pk)


def notify_sync_signups(event):
    """Dispatch Discord event signup sync if enabled."""
    if event.discord_sync_signups:
        from events.tasks import sync_discord_event_signups

        sync_discord_event_signups.delay(event.pk)


def notify_mark_interested(event, user_id):
    """Dispatch Discord 'mark interested' if enabled."""
    if event.discord_mark_interested:
        from events.tasks import mark_interested_discord_event

        mark_interested_discord_event.delay(event.pk, user_id)


# ---------------------------------------------------------------------------
# Reaction → Signup handlers
#
# Called by the Discord bot gateway (bot.py) when users react to event
# announcement messages. These are synchronous functions — the bot calls
# them from async handlers via sync_to_async or database_sync_to_async.
# ---------------------------------------------------------------------------


def handle_reaction_signup(discord_message_id, discord_user_id):
    """Process a ✅ reaction on an event announcement → create EventSignup.

    Returns (success: bool, detail: str) tuple.
    """
    from app.models import CustomUser
    from discordbot.models import DiscordMessageLog
    from events.models import Event
    from events.services import process_rsvp

    # 1. Find the event from the announcement message
    log_entry = DiscordMessageLog.objects.filter(
        discord_message_id=str(discord_message_id),
        source="event_announcement",
        success=True,
    ).first()
    if not log_entry:
        return False, "not_event_message"

    try:
        event = Event.objects.get(pk=log_entry.source_id)
    except Event.DoesNotExist:
        return False, "event_not_found"

    # 2. Find the user by Discord ID
    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return False, "user_not_linked"

    # 3. Process the RSVP
    try:
        signup = process_rsvp(event, user)
        logger.info(
            "Discord reaction signup: user=%s event=%s status=%s",
            user.pk,
            event.pk,
            signup.status,
        )
        return True, signup.status
    except ValueError as e:
        logger.info(
            "Discord reaction signup skipped: user=%s event=%s reason=%s",
            user.pk,
            event.pk,
            str(e),
        )
        return False, str(e)


def handle_reaction_cancel(discord_message_id, discord_user_id):
    """Process a ❌ reaction or ✅ removal on an event announcement → cancel EventSignup.

    Returns (success: bool, detail: str) tuple.
    """
    from app.models import CustomUser
    from discordbot.models import DiscordMessageLog
    from events.models import Event, EventSignup
    from events.services import cancel_signup

    log_entry = DiscordMessageLog.objects.filter(
        discord_message_id=str(discord_message_id),
        source="event_announcement",
        success=True,
    ).first()
    if not log_entry:
        return False, "not_event_message"

    try:
        event = Event.objects.get(pk=log_entry.source_id)
    except Event.DoesNotExist:
        return False, "event_not_found"

    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return False, "user_not_linked"

    try:
        signup = EventSignup.objects.get(event=event, user=user)
        cancel_signup(signup)
        logger.info(
            "Discord reaction cancel: user=%s event=%s",
            user.pk,
            event.pk,
        )
        return True, "cancelled"
    except EventSignup.DoesNotExist:
        return False, "no_signup"
    except ValueError as e:
        return False, str(e)
