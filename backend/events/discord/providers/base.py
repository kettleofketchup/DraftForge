"""Game-type signup handler protocol + default (game-agnostic) implementation.

Each concrete handler (``DotaHandler``, ``DeadlockHandler``) provides the four
common operations the shared dispatcher in ``handlers.py`` calls. ``DotaHandler``
additionally owns the Dota-only rank-flow methods. The dispatcher resolves the
handler from ``event.game_type`` (server truth) via ``registry.get_signup_handler``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from events.models import Event
from events.schemas import SignupModalConfig

if TYPE_CHECKING:
    from app.models import CustomUser
    from org.models import OrgUser


@runtime_checkable
class GameSignupHandler(Protocol):
    """The four common signup operations every game type implements."""

    def profile_complete(self, org_user: OrgUser, event: Event) -> bool:
        """True when the user can sign up directly (no modal needed)."""

    def prefill(self, org_user: OrgUser) -> dict:
        """Prefill values for the signup modal (e.g. known friend id)."""

    def modal_config(self, event: Event) -> SignupModalConfig:
        """The typed per-game modal config carried in the needs_modal response."""

    def apply_modal_submit(
        self, event: Event, org_user: OrgUser, user: CustomUser, values: dict
    ) -> dict:
        """Persist the modal submission; return the next-step action dict."""


class DefaultHandler:
    """Safe defaults for an unregistered game type: no profile gating, no modal."""

    def profile_complete(self, org_user: OrgUser, event: Event) -> bool:
        return True

    def prefill(self, org_user: OrgUser) -> dict:
        return {}

    def modal_config(self, event: Event) -> SignupModalConfig:
        return SignupModalConfig(require_steam_id=event.require_steam_id)

    def apply_modal_submit(
        self, event: Event, org_user: OrgUser, user: CustomUser, values: dict
    ) -> dict:
        return {"action": "error", "message": "Unknown game type."}
