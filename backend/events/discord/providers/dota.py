"""Dota 2 signup handler: profile gating, modal config, modal submit, rank flow.

``DotaHandler`` carries the four common operations plus the eight Dota-only
rank-flow operations the thin dispatcher in ``handlers.py`` delegates to.

CACHE GUARDRAIL (#268): ``set_position`` writes ``PlayerDotaProfile`` (a
CACHEOPS model) outside ``transaction.atomic``, so it must call
``invalidate_obj(profile)`` directly. Do not drop or convert it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError as DjangoValidationError
from structlog.contextvars import bind_contextvars

from app.cache_utils import invalidate_obj
from events.discord._shared import (
    _direct_signup,
    _get_org_user,
    _log_interaction,
    _log_signup,
)
from events.models import Event
from events.schemas import (
    DotaModalConfig,
    SignupInputPatch,
    dota_require_screenshot,
)
from org.models_profiles import PlayerDotaProfile
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser
    from org.models import OrgUser

# events.services is imported function-local (see _shared.py) to avoid the
# events.services -> events.discord(__init__) -> handlers import cycle.

log = get_logger(__name__)


def _check_dota_profile_complete(org_user: OrgUser, event: Event | None = None) -> bool:
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


def _rank_followup_message(rank_status: str) -> str:
    """Build the ephemeral follow-up message for Dota rank details."""
    if rank_status == "active":
        return "Almost there! Select your current medal:"
    elif rank_status == "previous":
        return "Almost there! Click below to enter your previous rank details:"
    else:
        return "Almost there! Click below to enter your Battle Cup info:"


class DotaHandler:
    """Dota 2 signup logic + rank-flow operations."""

    # ---- Common operations -------------------------------------------------

    def profile_complete(self, org_user: OrgUser, event: Event) -> bool:
        return _check_dota_profile_complete(org_user, event=event)

    def prefill(self, org_user: OrgUser) -> dict:
        return {
            "unverified_friend_id": getattr(
                getattr(org_user, "dota_profile", None), "unverified_friend_id", ""
            )
            or "",
        }

    def modal_config(self, event: Event) -> DotaModalConfig:
        return DotaModalConfig(
            require_steam_id=event.require_steam_id,
            require_rank_screenshot=event.discord_require_rank_screenshot,
            require_battlecup_screenshot=event.discord_require_battlecup_screenshot,
            min_mmr=event.min_mmr,
            allow_active_mmr=event.allow_active_mmr,
            allow_previous_rank=event.allow_previous_rank,
            allow_battlecup_rating=event.allow_battlecup_rating,
        )

    def apply_modal_submit(
        self, event: Event, org_user: OrgUser, user: CustomUser, values: dict
    ) -> dict:
        from events.services import apply_signup_input

        friend_id = values.get("unverified_friend_id", "").strip()

        # NOTE: positions are collected in the follow-up PositionConfirmButton
        # flow, not in this modal.
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

    # ---- Rank-flow operations ---------------------------------------------

    def rank_status_select(
        self, event: Event, discord_user_id: str, rank_status: str
    ) -> None:
        """Save the rank status from the select menu to the Dota profile."""
        from events.services import apply_signup_input

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

    def rank_medal_select(self, event: Event, discord_user_id: str, medal: str) -> dict:
        """Handle active rank medal selection. Saves medal and signs up."""
        from events.services import apply_signup_input

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
            _log_interaction(event.pk, "awaiting_rank_screenshot", discord_user_id)
            return {
                "action": "needs_screenshot",
                "screenshot_type": "rank",
            }

        try:
            result = _direct_signup(event, user)
            _log_signup(event.pk, f"signup_ranked:{medal}", discord_user_id)
            return result
        except ValueError as e:
            log.warning(
                "signup_rejected",
                system="discord",
                subsystem="interaction",
                reason=str(e),
            )
            _log_signup(
                event.pk,
                "signup_failed",
                discord_user_id,
                success=False,
                error_message=str(e),
            )
            return {"action": "error", "message": str(e)}

    def previous_rank_submit(
        self, event: Event, discord_user_id: str, medal: str, date_text: str
    ) -> dict:
        """Handle previous rank modal submission. Saves rank info and signs up."""
        from events.services import apply_signup_input

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
            _log_interaction(event.pk, "awaiting_rank_screenshot", discord_user_id)
            return {
                "action": "needs_screenshot",
                "screenshot_type": "rank",
            }

        try:
            return _direct_signup(event, user)
        except ValueError as e:
            log.warning(
                "signup_rejected",
                system="discord",
                subsystem="interaction",
                reason=str(e),
            )
            return {"action": "error", "message": str(e)}

    def battle_cup_submit(self, event: Event, discord_user_id: str, tier: str) -> dict:
        """Handle battle cup modal submission. Saves tier and signs up."""
        from events.services import apply_signup_input

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
        if (
            event.discord_require_battlecup_screenshot
            and not profile.battlecup_screenshot
        ):
            _log_interaction(event.pk, "awaiting_battlecup_screenshot", discord_user_id)
            return {
                "action": "needs_screenshot",
                "screenshot_type": "battlecup",
            }

        try:
            result = _direct_signup(event, user)
            _log_signup(event.pk, f"signup_battlecup:T{tier}", discord_user_id)
            return result
        except ValueError as e:
            log.warning(
                "signup_rejected",
                system="discord",
                subsystem="interaction",
                reason=str(e),
            )
            _log_signup(
                event.pk,
                "signup_failed",
                discord_user_id,
                success=False,
                error_message=str(e),
            )
            return {"action": "error", "message": str(e)}

    def screenshot_upload(
        self,
        event: Event,
        discord_user_id: str,
        screenshot_type: str,
        attachment_url: str,
    ) -> dict:
        """Validate and save screenshot URL to PlayerDotaProfile, then sign up."""
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
            event.pk, f"screenshot_uploaded:{screenshot_type}", discord_user_id
        )

        # Complete the signup now that screenshot is provided
        _, user = _get_org_user(event, discord_user_id)
        if not user:
            return {"success": True, "signed_up": False, "message": "Screenshot saved."}

        try:
            result = _direct_signup(event, user)
            _log_signup(
                event.pk, f"signup_after_screenshot:{screenshot_type}", discord_user_id
            )
            return {
                "success": True,
                "signed_up": True,
                "message": f"Screenshot saved! You're signed up. Status: **{result['status']}**",
            }
        except ValueError as e:
            log.warning(
                "signup_rejected",
                system="discord",
                subsystem="interaction",
                reason=str(e),
            )
            return {
                "success": True,
                "signed_up": False,
                "message": f"Screenshot saved. {str(e)}",
            }

    def save_positions(
        self, event: Event, discord_user_id: str, positions: list[int]
    ) -> dict[str, str]:
        """Save positions for the user's signup on this event.

        Used by the PositionConfirmButton flow. Invalidation happens via
        events.services (apply_signup_input -> invalidate_after_commit), so this
        path does NOT call invalidate_obj directly.
        """
        org_user, _ = _get_org_user(event, discord_user_id)
        if org_user is not None:
            bind_contextvars(org_user_id=org_user.pk)
        if not org_user:
            return {"action": "error", "message": "Could not find your account."}

        from events.services import apply_signup_input

        try:
            apply_signup_input(
                org_user=org_user,
                event=event,
                patch=SignupInputPatch(positions=positions),
            )
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            log.warning(
                "signup_rejected", system="discord", subsystem="interaction", reason=msg
            )
            return {"action": "error", "message": msg}

        return {"action": "positions_saved"}

    def set_position(
        self, event: Event, discord_user_id: str, position: int
    ) -> dict[str, str]:
        """Set a single position flag (pos_N=True) on the user's PlayerDotaProfile.

        Used by the legacy per-click position dropdown (``pos_select_*``). Only
        sets the chosen flag True — doesn't reset others. CACHE GUARDRAIL (#268):
        the save is outside transaction.atomic, so invalidate_obj is called
        directly.
        """
        if position not in (1, 2, 3, 4, 5):
            return {"action": "error", "message": "Position must be 1-5."}

        org_user, _ = _get_org_user(event, discord_user_id)
        if org_user is None:
            return {"action": "error", "message": "Could not find your account."}
        bind_contextvars(org_user_id=org_user.pk)

        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
        setattr(profile, f"pos_{position}", True)
        profile.save(update_fields=[f"pos_{position}"])
        invalidate_obj(profile)
        return {"action": "position_set"}

    def get_rank_flow_state(
        self, event: Event, discord_user_id: str
    ) -> dict[str, object]:
        """Read the state the pos_confirm flow needs to render the next view.

        Returns dict with rank_status / require_screenshot / min_mmr, or
        error/message on lookup failure. Dead-but-retained (no live bot-side
        caller; the pos_confirm flow reads state off the View).
        """
        org_user, _ = _get_org_user(event, discord_user_id)
        if org_user is None:
            return {"error": "no_org_user", "message": "Could not find your account."}
        bind_contextvars(org_user_id=org_user.pk)

        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
        rank_status = profile.rank_status or "never"
        require_screenshot = dota_require_screenshot(
            rank_status,
            DotaModalConfig(
                require_rank_screenshot=event.discord_require_rank_screenshot,
                require_battlecup_screenshot=event.discord_require_battlecup_screenshot,
            ),
        )
        return {
            "rank_status": rank_status,
            "require_screenshot": require_screenshot,
            "min_mmr": event.min_mmr,
        }
