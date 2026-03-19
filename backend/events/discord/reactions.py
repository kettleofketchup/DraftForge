"""
Reaction-based signup handlers.

Called by the Discord bot gateway (bot.py) when users react to event
announcement messages. These are synchronous functions — the bot calls
them from async handlers via sync_to_async or database_sync_to_async.
"""

import logging

logger = logging.getLogger(__name__)


def handle_reaction_signup(discord_message_id, discord_user_id):
    """Process a reaction on an event announcement -> create EventSignup.

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
    """Process a reaction removal on an event announcement -> cancel EventSignup.

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
