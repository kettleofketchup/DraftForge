"""Guard tests for the #268 game-type provider registries.

SimpleTestCase (no DB): stub events + patched _load_event. Catches the
two silent-drift failure modes the refactor is designed to prevent —
registry keyset drift and a missed ModalConfig union registration — plus
the rank-flow isinstance guard and the loud fallback.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from app.models import GameType
from discordbot.components.registry import COMPONENT_PROVIDERS, get_component_provider
from events.discord.providers.base import DefaultHandler
from events.discord.providers.registry import SIGNUP_HANDLERS, get_signup_handler
from events.schemas import (
    DeadlockModalConfig,
    DotaModalConfig,
    SignupActionResponse,
)


def _stub_event(game_type):
    return SimpleNamespace(
        game_type=game_type,
        require_steam_id=True,
        discord_require_rank_screenshot=True,
        discord_require_battlecup_screenshot=False,
        min_mmr=3000,
        allow_active_mmr=True,
        allow_previous_rank=True,
        allow_battlecup_rating=True,
    )


class RegistryKeysetTest(SimpleTestCase):
    def test_component_and_handler_registries_cover_same_game_types(self):
        # Drift guard: a game added to one layer but not the other would
        # silently fall back to default in that layer.
        self.assertEqual(set(COMPONENT_PROVIDERS), set(SIGNUP_HANDLERS))

    def test_unregistered_handler_falls_back_with_loud_log(self):
        from events.discord.providers import registry

        with patch.object(registry, "log") as mock_log:
            handler = registry.get_signup_handler(9999)
        self.assertIsInstance(handler, DefaultHandler)
        mock_log.error.assert_called_once()
        self.assertEqual(mock_log.error.call_args.args[0], "provider_fallback")

    def test_unregistered_component_provider_falls_back(self):
        self.assertEqual(
            type(get_component_provider(9999)).__name__, "DefaultComponents"
        )


class ModalConfigTypeTest(SimpleTestCase):
    def test_dota_handler_returns_dota_config_that_round_trips(self):
        cfg = SIGNUP_HANDLERS[GameType.DOTA2].modal_config(_stub_event(GameType.DOTA2))
        self.assertIsInstance(cfg, DotaModalConfig)
        resp = SignupActionResponse(
            action="needs_modal", game_type=int(GameType.DOTA2), modal_config=cfg
        )
        rt = SignupActionResponse.model_validate(resp.model_dump()).modal_config
        self.assertIsInstance(rt, DotaModalConfig)
        self.assertEqual(rt.min_mmr, 3000)

    def test_deadlock_handler_returns_deadlock_config(self):
        cfg = SIGNUP_HANDLERS[GameType.DEADLOCK].modal_config(
            _stub_event(GameType.DEADLOCK)
        )
        self.assertIsInstance(cfg, DeadlockModalConfig)


class RankFlowGuardTest(SimpleTestCase):
    def test_rank_flow_on_non_dota_returns_not_applicable(self):
        from events.discord import handlers

        with patch.object(
            handlers, "_load_event", return_value=_stub_event(GameType.DEADLOCK)
        ):
            result = handlers.handle_rank_medal_select(
                event_id=1, discord_user_id="1", medal="Crusader 3"
            )
        self.assertEqual(result["action"], "error")
        self.assertEqual(result["message"], "Not applicable.")
