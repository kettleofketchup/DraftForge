"""Component provider registry (UI layer).

The "Adding a game type" checklist lives in one place: the module docstring of
``events/discord/providers/registry.py``. Step 5 of it registers the game's
``<Game>Components`` in ``COMPONENT_PROVIDERS`` below.
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


def get_component_provider(game_type: GameType | int) -> GameComponentProvider:
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
