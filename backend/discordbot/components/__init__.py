"""discord.py persistent Views, Buttons, and Modals for event interactions.

Split into a package: ``base`` (game-agnostic), ``dota``/``deadlock``/``default``
(per-game providers + views), ``registry`` (provider lookup). This module
re-exports the public View classes and patchable bindings for back-compat with
``from discordbot.components import X``.

Business logic lives in events/discord (handle_signup_button, etc.).
"""

from discordbot.components.base import (
    SCREENSHOT_EXAMPLE_URLS,
    DeclineButton,
    EventSignupView,
    GameComponentProvider,
    NotifyButton,
    ScreenshotUploadButton,
    ScreenshotUploadModal,
    ScreenshotUploadPromptView,
    SignupButton,
    TentativeButton,
    build_friend_id_input,
    respond_to_signup_user,
    send_modal_v2,
    signup_button,
)
from discordbot.components.deadlock import DeadlockComponents, DeadlockSignupModal
from discordbot.components.default import DefaultComponents, DefaultSignupModal
from discordbot.components.dota import (
    DOTA_MEDALS,
    DOTA_POSITIONS,
    DOTA_STARS,
    BattleCupTierSelect,
    DotaComponents,
    DotaSignupModal,
    MedalSelect,
    PositionConfirmButton,
    PositionSelectView,
    RankDetailsView,
    RankStatusSelect,
    RankStatusSelectView,
    StarSelect,
    save_positions,
    set_position,
)
from discordbot.components.registry import (
    COMPONENT_PROVIDERS,
    get_component_provider,
    iter_component_providers,
)

__all__ = [
    # game-agnostic views / buttons
    "EventSignupView",
    "SignupButton",
    "NotifyButton",
    "TentativeButton",
    "DeclineButton",
    "ScreenshotUploadPromptView",
    "ScreenshotUploadButton",
    "ScreenshotUploadModal",
    "SCREENSHOT_EXAMPLE_URLS",
    "send_modal_v2",
    "build_friend_id_input",
    # Dota views
    "PositionSelectView",
    "PositionConfirmButton",
    "RankDetailsView",
    "MedalSelect",
    "StarSelect",
    "BattleCupTierSelect",
    "RankStatusSelect",
    "RankStatusSelectView",
    "DotaSignupModal",
    "DOTA_POSITIONS",
    "DOTA_MEDALS",
    "DOTA_STARS",
    # Deadlock / default modals
    "DeadlockSignupModal",
    "DefaultSignupModal",
    # providers + registry
    "GameComponentProvider",
    "DotaComponents",
    "DeadlockComponents",
    "DefaultComponents",
    "COMPONENT_PROVIDERS",
    "get_component_provider",
    "iter_component_providers",
    # patchable module-level bindings (defining modules: base, dota)
    "signup_button",
    "respond_to_signup_user",
    "save_positions",
    "set_position",
]
