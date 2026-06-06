"""Game-type -> signup-handler registry (the ORM-logic side of the split).

Adding a game type (mirror of the spec's extension checklist):

1. ``discordbot/components/<game>.py`` — ``<Game>Components`` (build_signup_modal,
   ``bare_select_ids``, operation methods + any follow-up View classes).
2. ``events/discord/providers/<game>.py`` — ``<Game>Handler`` (profile_complete,
   prefill, modal_config, apply_modal_submit; rank-flow methods only if needed).
3. ``events/schemas.py`` — ``<Game>ModalConfig(SignupModalConfig)`` with
   ``kind: Literal["<game>"]``, AND add it to the ``ModalConfig`` discriminated
   union alias. (Skipping the union edit is silent — the config routes to base
   and loses its fields. The parametrized round-trip test catches it.)
4. ``app/models.py`` ``GameType`` — add the member, AND sync
   ``frontend/app/components/game/constants.ts`` per the enum's own docstring.
5. Register in ``discordbot/components/registry.py`` (``COMPONENT_PROVIDERS``).
6. Register in this module's ``SIGNUP_HANDLERS``.
   (Steps 5+6 are guarded by the keyset-equality test — miss one and it goes red.)
7. ``discordbot/custom_ids.py`` — only if the game has unique interaction flows
   needing new codecs (a text-field game like Deadlock needs none).
"""

from __future__ import annotations

from app.models import GameType
from telemetry.logging import get_logger

from events.discord.providers.base import DefaultHandler, GameSignupHandler
from events.discord.providers.deadlock import DeadlockHandler
from events.discord.providers.dota import DotaHandler

log = get_logger(__name__)

SIGNUP_HANDLERS: dict[GameType, GameSignupHandler] = {
    GameType.DOTA2: DotaHandler(),
    GameType.DEADLOCK: DeadlockHandler(),
}

_DEFAULT = DefaultHandler()


def get_signup_handler(game_type) -> GameSignupHandler:
    """Resolve the handler for a game type, falling back to DefaultHandler."""
    handler = SIGNUP_HANDLERS.get(game_type)
    if handler is None:
        log.error(
            "provider_fallback",
            system="discord",
            subsystem="interaction",
            tags=["events", "signup"],
            tags_csv="events,signup",
            layer="handlers",
            game_type=game_type,
        )
        return _DEFAULT
    return handler
