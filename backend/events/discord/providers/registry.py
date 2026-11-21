"""Game-type -> signup-handler registry (the ORM-logic side of the split).

Adding a game type (canonical checklist; other modules link here):

1. ``discordbot/components/<game>.py`` — ``<Game>Components`` (build_signup_modal,
   ``bare_select_ids``, operation methods + any follow-up View classes).
2. ``events/discord/providers/<game>.py`` — ``<Game>Handler`` (profile_complete,
   prefill, modal_config, apply_modal_submit; rank-flow methods only if needed).
3. ``events/schemas.py`` — ``<Game>ModalConfig(SignupModalConfig)`` with
   ``kind: Literal["<game>"]``, AND add it to the ``ModalConfig`` discriminated
   union alias. (Skipping the union edit is silent — the config routes to base
   and loses its fields. The parametrized round-trip test catches it.)
4. ``common/game.py`` ``GameType`` (re-exported by ``app.models``) — add the
   member, AND sync ``frontend/app/components/game/constants.ts`` per the enum's
   own docstring. Commit the state-only ``AlterField`` migrations Django emits
   for the ``choices=GameType.choices`` fields (``Tournament.game_type``,
   ``Event.game_type``, ``OrgEventDefaults.game_type``): the release recipe runs
   ``makemigrations`` on the prod host and would otherwise create an untracked
   migration there. ``OrgUserGameMmr.game_type`` has no choices, so org MMR
   needs no migration.
5. Register in ``discordbot/components/registry.py`` (``COMPONENT_PROVIDERS``).
6. Register in this module's ``SIGNUP_HANDLERS``.
   (Steps 5+6 are guarded by the keyset-equality test — miss one and it goes red.)
7. ``discordbot/custom_ids.py`` — only if the game has unique interaction flows
   needing new codecs (a text-field game like Deadlock needs none).
8. The game's signup modal must send its own ``GameType`` member as
   ``game_type`` to ``signup_modal_submit``. ``handle_signup_modal_submit``
   rejects a modal built for another game; ``None`` is reserved for the
   fallback modal and is rejected for any game registered above.
9. ``events/eligibility/checks/requirements.py`` ``REQUIREMENT_CHECKS`` — add an
   entry (a no-op ``GameRequirements`` like Deadlock's is enough). The lookup is
   unguarded: a missing entry raises ``KeyError`` in eligibility evaluation,
   which every org MMR write reaches through ``refresh_unmet_requirements``.
10. Optional: an ``org/mmr.py`` ``MMR_BOUNDS`` entry when the game's org MMR
    range differs from ``DEFAULT_MMR_BOUNDS``.
11. Frontend ``constants.ts`` — required: ``GAME_TYPE``, ``GAME_LABEL``,
    ``GAME_SHORT_LABEL``, ``GAME_SLUG`` (total ``Record`` types fail typecheck
    until filled; ``GAME_TYPES`` is derived). Optional: ``GAME_MMR_HOTKEY`` and
    ``GAME_MMR_BOUNDS`` (must mirror backend ``MMR_BOUNDS``; the sync test
    enforces it).
12. Org MMR then needs nothing else: edit schema, test ids, hotkeys, card
    tiles, PlayerModal, CSV game select, serializer ``game_mmrs`` and the user
    cache all iterate ``GameType`` / ``GAME_TYPES``. Without a ``suggest_mmr``
    range or rank-signals card the game gets no suggested MMR on approval.
"""

from __future__ import annotations

from app.models import GameType
from events.discord.providers.base import DefaultHandler, GameSignupHandler
from events.discord.providers.deadlock import DeadlockHandler
from events.discord.providers.dota import DotaHandler
from telemetry.logging import get_logger

log = get_logger(__name__)

SIGNUP_HANDLERS: dict[GameType, GameSignupHandler] = {
    GameType.DOTA2: DotaHandler(),
    GameType.DEADLOCK: DeadlockHandler(),
}

_DEFAULT = DefaultHandler()


def get_signup_handler(game_type: GameType | int) -> GameSignupHandler:
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
