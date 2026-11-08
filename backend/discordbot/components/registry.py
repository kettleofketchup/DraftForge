"""Component provider registry (UI layer).

Adding a game type (the extension checklist — mirrors
``events/discord/providers/registry.py``):

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
5. Register in this module (``COMPONENT_PROVIDERS``).
6. Register in ``events/discord/providers/registry.py`` (``SIGNUP_HANDLERS``).
   (Steps 5+6 are guarded by the keyset-equality test — miss one and it goes red.)
7. ``discordbot/custom_ids.py`` — only if the game has unique interaction flows
   needing new codecs (a text-field game like Deadlock needs none).
"""

from __future__ import annotations

from app.models import GameType
from discordbot.components.base import GameComponentProvider
from discordbot.components.deadlock import DeadlockComponents
from discordbot.components.default import DefaultComponents
from discordbot.components.dota import DotaComponents
from telemetry.logging import get_logger

log = get_logger(__name__)

COMPONENT_PROVIDERS: dict[GameType, GameComponentProvider] = {
    GameType.DOTA2: DotaComponents(),
    GameType.DEADLOCK: DeadlockComponents(),
}
_DEFAULT = DefaultComponents()


def get_component_provider(game_type: GameType) -> GameComponentProvider:
    provider = COMPONENT_PROVIDERS.get(game_type)
    if provider is None:
        log.error(
            "provider_fallback",
            system="discord",
            subsystem="interaction",
            tags=["events", "signup"],
            tags_csv="events,signup",
            layer="components",
            game_type=game_type,
        )
        return _DEFAULT
    return provider


def iter_component_providers() -> list[GameComponentProvider]:
    return list(COMPONENT_PROVIDERS.values())
