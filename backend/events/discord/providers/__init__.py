"""Per-game-type Discord signup handler providers.

See ``registry.py`` for the registry + the "Adding a game type" checklist.
"""

from events.discord.providers.base import DefaultHandler, GameSignupHandler
from events.discord.providers.deadlock import (
    DeadlockHandler,
    _check_deadlock_profile_complete,
)
from events.discord.providers.dota import DotaHandler, _check_dota_profile_complete
from events.discord.providers.registry import (
    SIGNUP_HANDLERS,
    get_signup_handler,
)

__all__ = [
    "DefaultHandler",
    "GameSignupHandler",
    "DotaHandler",
    "DeadlockHandler",
    "SIGNUP_HANDLERS",
    "get_signup_handler",
    "_check_dota_profile_complete",
    "_check_deadlock_profile_complete",
]
