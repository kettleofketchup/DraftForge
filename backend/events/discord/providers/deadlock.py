"""Deadlock signup handler: profile gating, modal config, modal submit.

Deadlock has no rank-flow follow-up: ``apply_modal_submit`` saves the
``PlayerDeadlockProfile`` and signs the user up directly.

CACHE GUARDRAIL (#268): ``apply_modal_submit`` saves ``PlayerDeadlockProfile``
(a CACHEOPS model) outside ``transaction.atomic``, so it must call
``invalidate_obj(profile)`` directly. Do not drop or convert it.
"""

from __future__ import annotations

from app.cache_utils import invalidate_obj

from events.discord._shared import _direct_signup
from events.models import Event
from events.schemas import DeadlockModalConfig
from org.models_profiles import PlayerDeadlockProfile
from telemetry.logging import get_logger

# events.services is imported function-local (via _shared._direct_signup) to
# avoid the events.services -> events.discord(__init__) -> handlers cycle.

log = get_logger(__name__)


def _check_deadlock_profile_complete(org_user) -> bool:
    """Check if OrgUser has a complete Deadlock profile."""
    try:
        profile = org_user.deadlock_profile
        return bool(profile.rank)
    except Exception:
        return False


class DeadlockHandler:
    """Deadlock signup logic (text-field profile, no rank-flow follow-up)."""

    def profile_complete(self, org_user, event: Event) -> bool:
        return _check_deadlock_profile_complete(org_user)

    def prefill(self, org_user) -> dict:
        return {
            "unverified_friend_id": getattr(
                getattr(org_user, "deadlock_profile", None), "unverified_friend_id", ""
            )
            or "",
        }

    def modal_config(self, event: Event) -> DeadlockModalConfig:
        return DeadlockModalConfig(require_steam_id=event.require_steam_id)

    def apply_modal_submit(self, event: Event, org_user, user, values: dict) -> dict:
        friend_id = values.get("unverified_friend_id", "").strip()

        # Save Deadlock profile and sign up directly
        profile, _ = PlayerDeadlockProfile.objects.get_or_create(org_user=org_user)
        if friend_id:
            profile.unverified_friend_id = friend_id
        profile.rank = values.get("deadlock_rank", "")
        profile.save()
        invalidate_obj(profile)

        try:
            return _direct_signup(event, user)
        except ValueError as e:
            log.warning("signup_rejected", system="discord", subsystem="interaction", reason=str(e))
            return {"action": "error", "message": str(e)}
