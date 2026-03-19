"""
Interactive component handlers for Discord buttons and modals.

Called by discord.py View/Modal callbacks (discordbot/components.py).
These are synchronous functions — the caller wraps them with sync_to_async.
Return dicts with 'action' key so the caller knows how to respond.
"""

import logging

from events.models import Event, EventSignup, EventState, SignupStatus

logger = logging.getLogger(__name__)


def _check_dota_profile_complete(org_user):
    """Check if OrgUser has a complete Dota 2 profile."""
    try:
        profile = org_user.dota_profile
        has_positions = any(
            [profile.pos_1, profile.pos_2, profile.pos_3, profile.pos_4, profile.pos_5]
        )
        has_rank = (
            (profile.rank_status == "active" and profile.rank_medal)
            or (profile.rank_status == "previous" and profile.rank_medal)
            or (profile.rank_status == "never" and profile.battle_cup_tier is not None)
        )
        return has_positions and has_rank
    except Exception:
        return False


def _check_deadlock_profile_complete(org_user):
    """Check if OrgUser has a complete Deadlock profile."""
    try:
        profile = org_user.deadlock_profile
        return bool(profile.rank)
    except Exception:
        return False


def _get_org_user(event, discord_user_id):
    """Look up OrgUser for the event's org + Discord user. Returns (org_user, user) or (None, None)."""
    from app.models import CustomUser
    from org.models import OrgUser

    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return None, None

    org_user, _ = OrgUser.objects.get_or_create(
        user=user,
        organization=event.organization,
    )
    return org_user, user


def handle_signup_button(event_id, discord_user_id):
    """Handle Sign Up button click. Returns action dict."""
    from app.models import GameType

    try:
        event = Event.objects.select_related("organization", "event_repeater").get(
            pk=event_id
        )
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    if event.state != EventState.SIGNUPS_OPEN:
        return {"action": "error", "message": "Event is not accepting signups."}

    org_user, user = _get_org_user(event, discord_user_id)
    if not org_user:
        return {
            "action": "error",
            "message": "Your Discord account isn't linked to DraftForge. Please link it on the website first.",
        }

    # Check if already signed up
    existing = (
        EventSignup.objects.filter(event=event, user=user)
        .exclude(status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED])
        .first()
    )
    if existing:
        return {
            "action": "error",
            "message": f"You're already signed up (status: {existing.status}).",
        }

    # Check profile completeness (profiles are on OrgUser, not CustomUser)
    if event.game_type == GameType.DOTA2:
        profile_complete = _check_dota_profile_complete(org_user)
    elif event.game_type == GameType.DEADLOCK:
        profile_complete = _check_deadlock_profile_complete(org_user)
    else:
        profile_complete = True

    if profile_complete:
        # Direct signup — no modal needed
        from events.services import process_rsvp

        try:
            signup = process_rsvp(event, user)
            return {"action": "signed_up", "status": signup.status}
        except ValueError as e:
            return {"action": "error", "message": str(e)}

    # Needs modal — return prefill data
    return {
        "action": "needs_modal",
        "game_type": event.game_type,
        "prefill": {
            "unverified_steam_id": getattr(
                getattr(org_user, "dota_profile", None), "unverified_steam_id", ""
            )
            or getattr(
                getattr(org_user, "deadlock_profile", None), "unverified_steam_id", ""
            )
            or "",
        },
    }


def handle_signup_modal_submit(event_id, discord_user_id, game_type, values):
    """Handle modal form submission. Saves profile data to OrgUser, may need follow-up."""
    from cacheops import invalidate_obj

    from app.models import GameType
    from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if not org_user:
        return {"action": "error", "message": "User not found."}

    steam_id = values.get("unverified_steam_id", "").strip()

    if game_type == GameType.DOTA2:
        # Save Dota profile on OrgUser
        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
        if steam_id:
            profile.unverified_steam_id = steam_id
        positions = values.get("positions", [])
        profile.pos_1 = "1" in positions
        profile.pos_2 = "2" in positions
        profile.pos_3 = "3" in positions
        profile.pos_4 = "4" in positions
        profile.pos_5 = "5" in positions
        rank_status = values.get("rank_status", "never")
        if rank_status not in ("active", "previous", "never"):
            rank_status = "never"
        profile.rank_status = rank_status
        profile.save()
        invalidate_obj(profile)

        # Need follow-up for rank details
        return {
            "action": "needs_rank_details",
            "message": _rank_followup_message(profile.rank_status),
        }

    elif game_type == GameType.DEADLOCK:
        # Save Deadlock profile and sign up directly
        profile, _ = PlayerDeadlockProfile.objects.get_or_create(org_user=org_user)
        if steam_id:
            profile.unverified_steam_id = steam_id
        profile.rank = values.get("deadlock_rank", "")
        profile.save()
        invalidate_obj(profile)

        from events.services import process_rsvp

        try:
            signup = process_rsvp(event, user)
            return {"action": "signed_up", "status": signup.status}
        except ValueError as e:
            return {"action": "error", "message": str(e)}

    return {"action": "error", "message": "Unknown game type."}


def _rank_followup_message(rank_status):
    """Build the ephemeral follow-up message for Dota rank details."""
    if rank_status == "active":
        return "Almost there! Select your current medal:"
    elif rank_status == "previous":
        return "Almost there! Click below to enter your previous rank details:"
    else:
        return "Almost there! Click below to enter your Battle Cup info:"


def handle_rank_medal_select(event_id, discord_user_id, medal):
    """Handle active rank medal selection. Saves medal and signs up."""
    from cacheops import invalidate_obj

    from events.services import process_rsvp
    from org.models_profiles import PlayerDotaProfile

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    profile.rank_medal = medal
    profile.save(update_fields=["rank_medal"])
    invalidate_obj(profile)

    try:
        signup = process_rsvp(event, user)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        return {"action": "error", "message": str(e)}


def handle_previous_rank_submit(event_id, discord_user_id, medal, date_text):
    """Handle previous rank modal submission. Saves rank info and signs up."""
    from cacheops import invalidate_obj

    from events.services import process_rsvp
    from org.models_profiles import PlayerDotaProfile

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    profile.rank_medal = medal
    profile.save(update_fields=["rank_medal"])
    invalidate_obj(profile)

    try:
        signup = process_rsvp(event, user)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        return {"action": "error", "message": str(e)}


def handle_battle_cup_submit(event_id, discord_user_id, tier):
    """Handle battle cup modal submission. Saves tier and signs up."""
    from cacheops import invalidate_obj

    from events.services import process_rsvp
    from org.models_profiles import PlayerDotaProfile

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    try:
        profile.battle_cup_tier = int(tier.strip())
    except (ValueError, TypeError):
        return {"action": "error", "message": "Invalid tier. Must be a number."}
    profile.save(update_fields=["battle_cup_tier"])
    invalidate_obj(profile)

    try:
        signup = process_rsvp(event, user)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        return {"action": "error", "message": str(e)}


def handle_notify_button(event_id, discord_user_id):
    """Handle Notify Me button click. Toggles RepeaterSubscription."""
    from cacheops import invalidate_obj

    from app.models import CustomUser
    from events.models import RepeaterSubscription

    try:
        event = Event.objects.select_related("event_repeater").get(pk=event_id)
    except Event.DoesNotExist:
        return {"subscribed": False}

    if not event.event_repeater:
        return {"subscribed": False}

    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return {"subscribed": False}

    sub, created = RepeaterSubscription.objects.get_or_create(
        event_repeater=event.event_repeater,
        user=user,
    )
    if not created:
        sub.delete()
    invalidate_obj(event.event_repeater)  # Invalidate subscriber count cache
    return {"subscribed": created}


def handle_decline_button(event_id, discord_user_id):
    """Handle Decline button click. Cancels signup if exists, or no-ops."""
    from app.models import CustomUser
    from events.services import cancel_signup

    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return {"action": "error", "message": "Your Discord account isn't linked."}

    try:
        signup = EventSignup.objects.get(event=event, user=user)
        if signup.status in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            return {"action": "already_declined", "message": "You've already declined."}
        cancel_signup(signup)
        return {"action": "declined", "message": "You've declined the event."}
    except EventSignup.DoesNotExist:
        return {"action": "not_signed_up", "message": "You weren't signed up."}


def handle_tentative_button(event_id, discord_user_id):
    """Handle Tentative button click. Creates a TENTATIVE signup (doesn't take a spot)."""
    from app.models import CustomUser

    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    if event.state != EventState.SIGNUPS_OPEN:
        return {"action": "error", "message": "Event is not accepting signups."}

    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return {"action": "error", "message": "Your Discord account isn't linked."}

    # Check for existing signup
    existing = EventSignup.objects.filter(event=event, user=user).first()
    if existing:
        if existing.status == SignupStatus.TENTATIVE:
            return {
                "action": "already_tentative",
                "message": "You're already marked as tentative.",
            }
        if existing.status not in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            return {
                "action": "error",
                "message": f"You're already signed up (status: {existing.status}).",
            }
        # Allow re-tentative after cancel/reject
        existing.delete()

    EventSignup.objects.create(
        event=event,
        user=user,
        status=SignupStatus.TENTATIVE,
    )
    logger.info(
        "Discord tentative: user=%s event=%s",
        user.pk,
        event.pk,
    )
    return {"action": "tentative", "message": "Marked as tentative."}
