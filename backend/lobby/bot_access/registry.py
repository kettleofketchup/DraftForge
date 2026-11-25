"""Game-type -> bot access provider registry.

Adding a game (see also ``events/discord/providers/registry.py``):

1. Implement a ``BotAccessProvider`` in ``lobby/bot_access/<game>.py`` and
   register it in ``BOT_ACCESS_PROVIDERS``. With ``full_roster=False``,
   return only the bots that hold the league and set ``roster="holders"``.
2. Extend ``BotIdentity.kind`` values and ``PlatformLink.kind`` in
   ``lobby/bot_access/schemas.py`` if the game identifies bots or links
   leagues differently, then regenerate the Zod schemas.
3. Add a frontend copy component under
   ``frontend/app/features/bot-access/providers/`` keyed on the new
   ``provider`` value.
4. Teach ``league_game_type`` the league's game once leagues carry one.
5. Add provider tests alongside ``lobby/tests/test_bot_access.py``.
"""

from __future__ import annotations

from common.game import GameType
from league.models import League
from lobby.bot_access.base import BotAccessProvider, UnsupportedBotAccess
from lobby.bot_access.dota import DotaBotAccess
from telemetry.logging import get_logger

log = get_logger(__name__)

BOT_ACCESS_PROVIDERS: dict[GameType, BotAccessProvider] = {
    GameType.DOTA2: DotaBotAccess()
}

_UNSUPPORTED = UnsupportedBotAccess()


def get_bot_access(game_type: GameType | int) -> BotAccessProvider:
    provider = BOT_ACCESS_PROVIDERS.get(game_type)
    if provider is None:
        log.info(
            "bot_access_provider_fallback",
            system="lobby",
            subsystem="bot_access",
            game_type=game_type,
        )
        return _UNSUPPORTED
    return provider


def league_game_type(league: League) -> GameType:
    return GameType.DOTA2
