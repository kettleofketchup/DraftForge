"""
Interactive component handlers for Discord buttons and modals.

Called by discord.py View/Modal callbacks (discordbot/components.py).
These are synchronous functions — the caller wraps them with sync_to_async.
Return dicts with 'action' key so the caller knows how to respond.
"""

from structlog.contextvars import bind_contextvars

from discordbot.models import DiscordEventLog
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from telemetry.logging import get_logger

log = get_logger(__name__)


def _log_interaction(
    event_id,
    action,
    discord_user_id="",
    discord_username="",
    success=True,
    error_message="",
):
    """Log a Discord interaction (best-effort; surface failures via structlog)."""
    try:
        DiscordEventLog.log_interaction(
            event_id, action, discord_user_id, discord_username, success, error_message
        )
    except Exception as e:
        log.error(
            "discord_event_log_write_failed",
            kind="interaction",
            action=action,
            event_id=event_id,
            error=str(e),
            exc_info=True,
        )


def _log_signup(
    event_id,
    action,
    discord_user_id="",
    discord_username="",
    success=True,
    error_message="",
):
    """Log a signup action (best-effort; surface failures via structlog)."""
    try:
        DiscordEventLog.log_signup(
            event_id, action, discord_user_id, discord_username, success, error_message
        )
    except Exception as e:
        log.error(
            "discord_event_log_write_failed",
            kind="signup",
            action=action,
            event_id=event_id,
            error=str(e),
            exc_info=True,
        )


def _check_dota_profile_complete(org_user, event=None):
    """Check if OrgUser has a complete Dota 2 profile for the given event."""
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
        # If event requires min_mmr, profile must have a numeric MMR
        if event and event.min_mmr and not profile.mmr:
            return False
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


def _get_org_user(event, discord_user_id, discord_username=None):
    """Look up or create OrgUser for the event's org + Discord user.

    If no CustomUser exists with this Discord ID, a "phantom" placeholder is
    auto-created using the Discord username. A button click only carries a
    Discord ID — it can't run the OAuth pipeline — so the phantom holds the
    signup until the person logs in, at which point the social-auth pipeline
    reclaims this exact row by discordId (see app/pipelines.py). The phantom is
    a normal, immediately-loginable account — no restrictions.

    Returns (org_user, user) or (None, None).
    """
    from django.db import IntegrityError, transaction

    from app.models import CustomUser, PositionsModel
    from events.services import resolve_or_create_org_user

    discord_id_str = str(discord_user_id)

    # 1) Primary: an account already linked to this Discord ID.
    user = CustomUser.objects.filter(discordId=discord_id_str).first()

    # 2) Discord usernames are globally unique, so an existing *unclaimed*
    #    account with this username is the same person. Claim it for this
    #    Discord ID instead of creating a duplicate (and instead of mangling
    #    the username, which would later collide when the OAuth login writes
    #    the real handle back in save_discord).
    if user is None and discord_username:
        candidate = CustomUser.objects.filter(username=discord_username).first()
        if candidate is not None and not candidate.discordId:
            candidate.discordId = discord_id_str
            try:
                with transaction.atomic():
                    candidate.save(update_fields=["discordId"])
                user = candidate
            except IntegrityError:
                # A concurrent click/login claimed this discordId first —
                # adopt that row instead of propagating a 500.
                user = CustomUser.objects.filter(discordId=discord_id_str).first()

    # 3) Otherwise create a fresh account keyed by the unique Discord handle.
    if user is None:
        username = discord_username or f"discord_{discord_id_str}"
        positions = PositionsModel.objects.create()
        new_user = CustomUser(
            username=username,
            discordId=discord_id_str,
            nickname=discord_username or username,
            positions=positions,
        )
        try:
            with transaction.atomic():
                new_user.save()
            user = new_user
        except IntegrityError:
            # Lost a race (a concurrent click or login created the row first),
            # rather than crash on the unique discordId/username constraint.
            positions.delete()
            user = CustomUser.objects.filter(discordId=discord_id_str).first()
            if user is None:
                # Handle is held by a different Discord identity (stale rename):
                # fall back to an id-based username, which is always unique.
                fallback_positions = PositionsModel.objects.create()
                user = CustomUser.objects.create(
                    username=f"discord_{discord_id_str}",
                    discordId=discord_id_str,
                    nickname=discord_username or f"discord_{discord_id_str}",
                    positions=fallback_positions,
                )

    org_user = resolve_or_create_org_user(user, event.organization)
    return org_user, user


def handle_signup_button(event_id, discord_user_id, discord_username=None):
    """Handle Sign Up button click. Returns action dict."""
    log.info("handler_invoked", handler="signup_button")
    from app.models import GameType

    try:
        event = Event.objects.select_related("organization", "event_repeater").get(
            pk=event_id
        )
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    if event.state != EventState.SIGNUPS_OPEN:
        return {"action": "error", "message": "Event is not accepting signups."}

    org_user, user = _get_org_user(
        event, discord_user_id, discord_username=discord_username
    )
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {
            "action": "error",
            "message": "Could not create your account. Please try again.",
        }

    # Check if already signed up (tentative can upgrade to full signup)
    existing = (
        EventSignup.objects.filter(event=event, user=user)
        .exclude(
            status__in=[
                SignupStatus.CANCELLED,
                SignupStatus.REJECTED,
                SignupStatus.TENTATIVE,
            ]
        )
        .first()
    )
    if existing:
        return {
            "action": "error",
            "message": f"You're already signed up (status: {existing.status}).",
        }

    # Check profile completeness (profiles are on OrgUser, not CustomUser)
    if event.game_type == GameType.DOTA2:
        profile_complete = _check_dota_profile_complete(org_user, event=event)
    elif event.game_type == GameType.DEADLOCK:
        profile_complete = _check_deadlock_profile_complete(org_user)
    else:
        profile_complete = True

    if profile_complete:
        # Direct signup — no modal needed
        from events.services import process_rsvp

        try:
            signup = process_rsvp(event, user)
            log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
            _log_signup(event_id, "signup_direct", discord_user_id, discord_username)
            # notify_signup_changed is dispatched by _create_signup's on_commit hook
            # (services.py:246) — do NOT call directly or the embed updates twice.
            return {"action": "signed_up", "status": signup.status}
        except ValueError as e:
            log.warning("signup_rejected", reason=str(e))
            _log_signup(
                event_id,
                "signup_failed",
                discord_user_id,
                discord_username,
                success=False,
                error_message=str(e),
            )
            return {"action": "error", "message": str(e)}

    _log_interaction(event_id, "signup_modal_opened", discord_user_id, discord_username)
    # Needs modal — return prefill data + event config flags
    return {
        "action": "needs_modal",
        "game_type": event.game_type,
        "prefill": {
            "unverified_friend_id": getattr(
                getattr(org_user, "dota_profile", None), "unverified_friend_id", ""
            )
            or getattr(
                getattr(org_user, "deadlock_profile", None), "unverified_friend_id", ""
            )
            or "",
        },
        "require_steam_id": event.require_steam_id,
        "require_rank_screenshot": event.discord_require_rank_screenshot,
        "require_battlecup_screenshot": event.discord_require_battlecup_screenshot,
        "min_mmr": event.min_mmr,
        "allow_active_mmr": event.allow_active_mmr,
        "allow_previous_rank": event.allow_previous_rank,
        "allow_battlecup_rating": event.allow_battlecup_rating,
    }


def handle_signup_modal_submit(event_id, discord_user_id, game_type, values):
    """Handle modal form submission. Saves profile data to OrgUser, may need follow-up."""
    log.info("handler_invoked", handler="signup_modal_submit")
    from app.cache_utils import invalidate_obj

    from app.models import GameType
    from org.models_profiles import PlayerDeadlockProfile

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"action": "error", "message": "User not found."}

    friend_id = values.get("unverified_friend_id", "").strip()

    if game_type == GameType.DOTA2:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from events.schemas import SignupInputPatch
        from events.services import apply_signup_input

        # NOTE: positions are collected in the follow-up PositionConfirmButton
        # flow, not in this modal. Task 22 handles the positions write.
        rank_status = values.get("rank_status") or None
        # Coerce legacy non-canonical values to "never" (matches prior behavior).
        if rank_status and rank_status not in ("active", "previous", "never"):
            rank_status = "never"

        patch_kwargs = {}
        if friend_id:
            patch_kwargs["unverified_friend_id"] = friend_id
        if rank_status:
            patch_kwargs["rank_status"] = rank_status

        try:
            apply_signup_input(
                org_user=org_user,
                event=event,
                patch=SignupInputPatch(**patch_kwargs),
            )
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return {"action": "error", "message": msg}

        if rank_status:
            return {
                "action": "needs_rank_details",
                "message": _rank_followup_message(rank_status),
            }

        # Rank status not yet selected — will be set via select
        return {"action": "needs_rank_status"}

    elif game_type == GameType.DEADLOCK:
        # Save Deadlock profile and sign up directly
        profile, _ = PlayerDeadlockProfile.objects.get_or_create(org_user=org_user)
        if friend_id:
            profile.unverified_friend_id = friend_id
        profile.rank = values.get("deadlock_rank", "")
        profile.save()
        invalidate_obj(profile)

        from events.services import process_rsvp

        try:
            signup = process_rsvp(event, user)
            log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
            return {"action": "signed_up", "status": signup.status}
        except ValueError as e:
            log.warning("signup_rejected", reason=str(e))
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


def handle_rank_status_select(event_id, discord_user_id, rank_status):
    """Save the rank status from the select menu to the Dota profile."""
    log.info("handler_invoked", handler="rank_status_select")
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return

    org_user, _ = _get_org_user(event, discord_user_id)
    if not org_user:
        return

    try:
        apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(rank_status=rank_status),
        )
    except DjangoValidationError:
        # Fail silently per existing behavior (function returns None either way).
        pass


def handle_rank_medal_select(event_id, discord_user_id, medal):
    """Handle active rank medal selection. Saves medal and signs up."""
    log.info("handler_invoked", handler="rank_medal_select")
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input, process_rsvp

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    try:
        profile = apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(rank_medal=medal),
        )
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return {"action": "error", "message": msg}

    # Check if screenshot required before completing signup
    if event.discord_require_rank_screenshot and not profile.rank_screenshot:
        _log_interaction(event_id, "awaiting_rank_screenshot", discord_user_id)
        return {
            "action": "needs_screenshot",
            "screenshot_type": "rank",
            "medal": medal,
        }

    try:
        signup = process_rsvp(event, user)
        log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
        _log_signup(event_id, f"signup_ranked:{medal}", discord_user_id)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        log.warning("signup_rejected", reason=str(e))
        _log_signup(
            event_id,
            "signup_failed",
            discord_user_id,
            success=False,
            error_message=str(e),
        )
        return {"action": "error", "message": str(e)}


def handle_previous_rank_submit(event_id, discord_user_id, medal, date_text):
    """Handle previous rank modal submission. Saves rank info and signs up."""
    log.info("handler_invoked", handler="previous_rank_submit")
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input, process_rsvp

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    try:
        profile = apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(rank_medal=medal),
        )
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return {"action": "error", "message": msg}

    # Check if screenshot required before completing signup
    if event.discord_require_rank_screenshot and not profile.rank_screenshot:
        _log_interaction(event_id, "awaiting_rank_screenshot", discord_user_id)
        return {
            "action": "needs_screenshot",
            "screenshot_type": "rank",
            "medal": medal,
        }

    try:
        signup = process_rsvp(event, user)
        log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        log.warning("signup_rejected", reason=str(e))
        return {"action": "error", "message": str(e)}


def handle_battle_cup_submit(event_id, discord_user_id, tier):
    """Handle battle cup modal submission. Saves tier and signs up."""
    log.info("handler_invoked", handler="battle_cup_submit")
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input, process_rsvp

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"action": "error", "message": "Not found."}

    try:
        tier_int = int(tier.strip())
    except (ValueError, TypeError, AttributeError):
        return {"action": "error", "message": "Invalid tier. Must be a number."}

    try:
        patch = SignupInputPatch(battle_cup_tier=tier_int)
    except Exception:  # pydantic.ValidationError (range 1..8)
        return {"action": "error", "message": "Invalid tier. Must be 1-8."}

    try:
        profile = apply_signup_input(org_user=org_user, event=event, patch=patch)
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return {"action": "error", "message": msg}

    # Check if screenshot required before completing signup
    if event.discord_require_battlecup_screenshot and not profile.battlecup_screenshot:
        _log_interaction(event_id, "awaiting_battlecup_screenshot", discord_user_id)
        return {
            "action": "needs_screenshot",
            "screenshot_type": "battlecup",
            "tier": tier,
        }

    try:
        signup = process_rsvp(event, user)
        log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
        _log_signup(event_id, f"signup_battlecup:T{tier}", discord_user_id)
        return {"action": "signed_up", "status": signup.status}
    except ValueError as e:
        log.warning("signup_rejected", reason=str(e))
        _log_signup(
            event_id,
            "signup_failed",
            discord_user_id,
            success=False,
            error_message=str(e),
        )
        return {"action": "error", "message": str(e)}


def handle_screenshot_upload(
    event_id, discord_user_id, screenshot_type, attachment_url
):
    """Validate and save screenshot URL to PlayerDotaProfile."""
    log.info("handler_invoked", handler="screenshot_upload")
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input

    # Validate URL
    if not attachment_url:
        return {"success": False, "message": "No file provided."}

    if screenshot_type == "rank":
        key = "rank_screenshot"
    elif screenshot_type == "battlecup":
        key = "battlecup_screenshot"
    else:
        return {"success": False, "message": "Unknown screenshot type."}

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"success": False, "message": "Event not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"success": False, "message": "User not found."}

    try:
        apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(**{key: attachment_url}),
        )
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return {"success": False, "message": msg}

    _log_interaction(
        event_id, f"screenshot_uploaded:{screenshot_type}", discord_user_id
    )

    # Complete the signup now that screenshot is provided
    from events.services import process_rsvp

    _, user = _get_org_user(event, discord_user_id)
    if not user:
        return {"success": True, "signed_up": False, "message": "Screenshot saved."}

    try:
        signup = process_rsvp(event, user)
        log.info("signup_persisted", signup_id=signup.pk, signup_status=signup.status)
        _log_signup(
            event_id, f"signup_after_screenshot:{screenshot_type}", discord_user_id
        )
        return {
            "success": True,
            "signed_up": True,
            "message": f"Screenshot saved! You're signed up. Status: **{signup.status}**",
        }
    except ValueError as e:
        log.warning("signup_rejected", reason=str(e))
        return {
            "success": True,
            "signed_up": False,
            "message": f"Screenshot saved. {str(e)}",
        }


def handle_notify_button(event_id, discord_user_id):
    """Handle Notify Me button click. Toggles RepeaterSubscription."""
    log.info("handler_invoked", handler="notify_button")
    from app.cache_utils import invalidate_obj

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
    log.info("handler_invoked", handler="decline_button")
    from events.services import cancel_signup

    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not user:
        return {"action": "not_signed_up", "message": "You weren't signed up."}

    try:
        signup = EventSignup.objects.get(event=event, user=user)
        if signup.status in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            return {"action": "already_declined", "message": "You've already declined."}
        cancel_signup(signup)
        _log_signup(event_id, "declined", discord_user_id)
        # notify_signup_changed is dispatched by cancel_signup's on_commit hook
        # (services.py:537) — do NOT call directly.
        return {"action": "declined", "message": "You've declined the event."}
    except EventSignup.DoesNotExist:
        return {"action": "not_signed_up", "message": "You weren't signed up."}


def handle_tentative_button(event_id, discord_user_id, discord_username=None):
    """Handle Tentative button click. Creates a TENTATIVE signup (doesn't take a spot)."""
    log.info("handler_invoked", handler="tentative_button")
    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return {"action": "error", "message": "Event not found."}

    if event.state != EventState.SIGNUPS_OPEN:
        return {"action": "error", "message": "Event is not accepting signups."}

    org_user, user = _get_org_user(
        event, discord_user_id, discord_username=discord_username
    )
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not user:
        return {"action": "error", "message": "Could not create your account."}

    # Check for existing signup
    existing = EventSignup.objects.filter(event=event, user=user).first()
    if existing:
        if existing.status == SignupStatus.TENTATIVE:
            return {
                "action": "already_tentative",
                "message": "You're already marked as tentative.",
            }
        if existing.status not in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            # Switch from active signup to tentative
            from events.services import cancel_signup

            cancel_signup(existing)
        # Remove cancelled/rejected signup to create fresh tentative
        existing.delete()

    EventSignup.objects.create(
        event=event,
        user=user,
        status=SignupStatus.TENTATIVE,
    )
    _log_signup(event_id, "tentative", discord_user_id, discord_username)
    # Trigger embed update
    from events.discord.dispatch import notify_signup_changed

    notify_signup_changed(event)

    log.info("tentative_created", user_id=user.pk, event_id=event.pk)
    return {"action": "tentative", "message": "Marked as tentative."}
