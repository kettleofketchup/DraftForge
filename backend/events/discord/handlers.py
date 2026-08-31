"""
Thin dispatcher for Discord button and modal handlers.

Called by discord.py View/Modal callbacks (discordbot/components/). These are
synchronous functions — the caller wraps them with sync_to_async. Each public
``handle_*`` keeps its EXACT name and ``/discord/...`` route binding
(internal_signup_views.py); the body loads the event, resolves the per-game
handler via ``get_signup_handler(event.game_type)`` (server truth), and
delegates. Return dicts with an 'action' key so the caller knows how to respond.

Shared helpers live in ``events/discord/_shared.py``; per-game logic lives in
``events/discord/providers/``. The ``events.services -> events.discord(__init__)
-> handlers`` cycle stays broken by keeping every ``from events.services import
...`` import function-local.
"""

from __future__ import annotations

from typing import Any

from structlog.contextvars import bind_contextvars

from events.constants import EventState, SignupStatus
from events.discord._shared import (
    _direct_signup,
    _existing_active_signup,
    _get_org_user,
    _load_event,
    _log_interaction,
    _log_signup,
)

# Re-exported for back-compat: callers/tests import these private helpers from
# events.discord.handlers (and from the package __init__).
from events.discord.providers.deadlock import (  # noqa: F401
    _check_deadlock_profile_complete,
)
from events.discord.providers.dota import (
    DotaHandler,
    _check_dota_profile_complete,  # noqa: F401
)
from events.discord.providers.registry import get_signup_handler
from events.models import EventSignup
from telemetry.logging import get_logger

log = get_logger(__name__)

_NOT_APPLICABLE = {"action": "error", "message": "Not applicable."}


def handle_signup_button(
    event_id: int,
    discord_user_id: str,
    discord_username: str | None = None,
) -> dict[str, Any]:
    """Handle Sign Up button click. Returns action dict."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="signup_button",
    )

    event = _load_event(event_id, select_related=("organization", "event_repeater"))
    if event is None:
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
    existing = _existing_active_signup(event, user)
    if existing:
        return {
            "action": "error",
            "message": f"You're already signed up (status: {existing.status}).",
        }

    handler = get_signup_handler(event.game_type)

    if handler.profile_complete(org_user, event):
        # Direct signup — no modal needed
        try:
            result = _direct_signup(event, user)
            _log_signup(event_id, "signup_direct", discord_user_id, discord_username)
            # notify_signup_changed is dispatched by _create_signup's on_commit
            # hook — do NOT call directly or the embed updates twice.
            return result
        except ValueError as e:
            log.warning(
                "signup_rejected",
                system="discord",
                subsystem="interaction",
                reason=str(e),
            )
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
    # Needs modal — return prefill data + typed per-game modal_config
    return {
        "action": "needs_modal",
        "game_type": event.game_type,
        "prefill": handler.prefill(org_user),
        "modal_config": handler.modal_config(event).model_dump(),
    }


def handle_signup_modal_submit(
    event_id: int,
    discord_user_id: str,
    game_type: int,
    values: dict,
) -> dict[str, Any]:
    """Handle modal form submission. Delegates to the per-game handler.

    ``game_type`` is accepted-but-ignored: dispatch resolves from
    ``event.game_type`` (server truth), removing the modal-open-vs-submit drift
    window.
    """
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="signup_modal_submit",
    )

    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Event not found."}

    org_user, user = _get_org_user(event, discord_user_id)
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not org_user:
        return {"action": "error", "message": "User not found."}

    handler = get_signup_handler(event.game_type)
    return handler.apply_modal_submit(event, org_user, user, values)


def handle_rank_status_select(
    event_id: int,
    discord_user_id: str,
    rank_status: str,
) -> dict[str, Any] | None:
    """Save the rank status from the select menu to the Dota profile."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="rank_status_select",
    )
    event = _load_event(event_id)
    if event is None:
        return
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.rank_status_select(event, discord_user_id, rank_status)


def handle_rank_medal_select(
    event_id: int,
    discord_user_id: str,
    medal: str,
) -> dict[str, Any]:
    """Handle active rank medal selection. Saves medal and signs up."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="rank_medal_select",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.rank_medal_select(event, discord_user_id, medal)


def handle_previous_rank_submit(
    event_id: int,
    discord_user_id: str,
    medal: str,
    date_text: str,
) -> dict[str, Any]:
    """Handle previous rank modal submission. Saves rank info and signs up."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="previous_rank_submit",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.previous_rank_submit(event, discord_user_id, medal, date_text)


def handle_battle_cup_submit(
    event_id: int,
    discord_user_id: str,
    tier: str,
) -> dict[str, Any]:
    """Handle battle cup modal submission. Saves tier and signs up."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="battle_cup_submit",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.battle_cup_submit(event, discord_user_id, tier)


def handle_screenshot_upload(
    event_id: int,
    discord_user_id: str,
    screenshot_type: str,
    attachment_url: str,
) -> dict[str, Any]:
    """Validate and save screenshot URL to PlayerDotaProfile."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="screenshot_upload",
    )
    event = _load_event(event_id)
    if event is None:
        return {"success": False, "message": "Event not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.screenshot_upload(
        event, discord_user_id, screenshot_type, attachment_url
    )


def handle_notify_button(event_id: int, discord_user_id: str) -> dict[str, Any]:
    """Handle Notify Me button click. Toggles RepeaterSubscription.

    Game-agnostic. CACHE GUARDRAIL (#268): the subscriber-count cache on the
    EventRepeater (a CACHEOPS model) is invalidated directly — the toggle is
    outside transaction.atomic.
    """
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="notify_button",
    )
    from app.cache_utils import invalidate_obj
    from app.models import CustomUser
    from events.models import RepeaterSubscription

    event = _load_event(event_id, select_related=("event_repeater",))
    if event is None:
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


def handle_decline_button(event_id: int, discord_user_id: str) -> dict[str, Any]:
    """Handle Decline button click. Cancels signup if exists, or no-ops.

    Game-agnostic.
    """
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="decline_button",
    )
    from events.services import cancel_signup

    event = _load_event(event_id)
    if event is None:
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
        # — do NOT call directly.
        return {"action": "declined", "message": "You've declined the event."}
    except EventSignup.DoesNotExist:
        return {"action": "not_signed_up", "message": "You weren't signed up."}


def handle_tentative_button(
    event_id: int,
    discord_user_id: str,
    discord_username: str | None = None,
) -> dict[str, Any]:
    """Handle Tentative button click. Routes through create_tentative_signup.

    Game-agnostic.
    """
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="tentative_button",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Event not found."}

    org_user, user = _get_org_user(
        event, discord_user_id, discord_username=discord_username
    )
    if org_user is not None:
        bind_contextvars(org_user_id=org_user.pk)
    if user is not None:
        bind_contextvars(user_id=user.pk)
    if not user:
        return {"action": "error", "message": "Could not create your account."}

    from events.services import create_tentative_signup

    try:
        signup = create_tentative_signup(event, user)
    except ValueError as e:
        log.warning(
            "signup_rejected", system="discord", subsystem="interaction", reason=str(e)
        )
        if "already marked as tentative" in str(e).lower():
            return {"action": "already_tentative", "message": str(e)}
        return {"action": "error", "message": str(e)}

    _log_signup(event_id, "tentative", discord_user_id, discord_username)
    log.info(
        "tentative_created",
        system="discord",
        subsystem="interaction",
        user_id=user.pk,
        event_id=event.pk,
        signup_id=signup.pk,
    )
    # notify_signup_changed is dispatched by create_tentative_signup's on_commit
    # hook — do NOT call directly.
    return {"action": "tentative", "message": "Marked as tentative."}


def handle_set_position(
    event_id: int,
    discord_user_id: str,
    position: int,
) -> dict[str, str]:
    """Set a single position flag (pos_N=True) on the user's PlayerDotaProfile."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="set_position",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Event not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.set_position(event, discord_user_id, position)


def handle_get_rank_flow_state(
    event_id: int,
    discord_user_id: str,
) -> dict[str, object]:
    """Read the state the pos_confirm flow needs to render the next view."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="get_rank_flow_state",
    )
    event = _load_event(event_id)
    if event is None:
        return {"error": "event_not_found", "message": "Event not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.get_rank_flow_state(event, discord_user_id)


def handle_save_positions(
    event_id: int,
    discord_user_id: str,
    positions: list[int],
) -> dict[str, str]:
    """Save positions for the user's signup on this event."""
    log.info(
        "handler_invoked",
        system="discord",
        subsystem="interaction",
        handler="save_positions",
    )
    event = _load_event(event_id)
    if event is None:
        return {"action": "error", "message": "Event not found."}
    handler = get_signup_handler(event.game_type)
    if not isinstance(handler, DotaHandler):
        return _NOT_APPLICABLE
    return handler.save_positions(event, discord_user_id, positions)
