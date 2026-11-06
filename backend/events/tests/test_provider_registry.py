"""Guard tests for the #268 game-type provider registries.

SimpleTestCase (no DB): stub events + patched _load_event. Catches the
two silent-drift failure modes the refactor is designed to prevent —
registry keyset drift and a missed ModalConfig union registration — plus
the rank-flow isinstance guard and the loud fallback.
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase
from structlog.testing import capture_logs

from app.models import GameType
from discordbot.components.registry import COMPONENT_PROVIDERS, get_component_provider
from events.discord import handlers
from events.discord.providers.base import DefaultHandler
from events.discord.providers.registry import SIGNUP_HANDLERS
from events.schemas import (
    DeadlockModalConfig,
    DotaModalConfig,
    RankFlowStateResponse,
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


_ACTION_ERROR = {"action": "error", "message": "Not applicable."}


class RankFlowGuardTest(SimpleTestCase):
    def _call(
        self, fn: Callable[..., Any], **kwargs: Any
    ) -> tuple[Any, list[dict[str, Any]]]:
        with (
            patch.object(
                handlers, "_load_event", return_value=_stub_event(GameType.DEADLOCK)
            ),
            capture_logs() as logs,
        ):
            result = fn(event_id=1, discord_user_id="1", **kwargs)
        return result, logs

    def _assert_logged(self, logs: list[dict[str, Any]], handler: str) -> None:
        hits = [e for e in logs if e["event"] == "handler_not_applicable"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["system"], "discord")
        self.assertEqual(hits[0]["subsystem"], "interaction")
        self.assertEqual(hits[0]["handler"], handler)
        self.assertEqual(hits[0]["event_id"], 1)
        self.assertEqual(hits[0]["game_type"], GameType.DEADLOCK)
        self.assertEqual(hits[0]["log_level"], "warning")

    def test_rank_status_select_returns_none(self) -> None:
        result, logs = self._call(handlers.handle_rank_status_select, rank_status="x")
        self.assertIsNone(result)
        self._assert_logged(logs, "rank_status_select")

    def test_action_endpoints_return_action_error(self) -> None:
        cases: list[tuple[Callable[..., Any], str, dict[str, Any]]] = [
            (
                handlers.handle_rank_medal_select,
                "rank_medal_select",
                {"medal": "Crusader 3"},
            ),
            (
                handlers.handle_previous_rank_submit,
                "previous_rank_submit",
                {"medal": "m", "date_text": "d"},
            ),
            (handlers.handle_battle_cup_submit, "battle_cup_submit", {"tier": "1"}),
            (handlers.handle_set_position, "set_position", {"position": 1}),
            (handlers.handle_save_positions, "save_positions", {"positions": [1]}),
        ]
        for fn, name, kwargs in cases:
            with self.subTest(handler=name):
                result, logs = self._call(fn, **kwargs)
                self.assertEqual(result, _ACTION_ERROR)
                self._assert_logged(logs, name)

    def test_screenshot_upload_uses_success_contract(self) -> None:
        result, logs = self._call(
            handlers.handle_screenshot_upload,
            screenshot_type="rank",
            attachment_url="u",
        )
        self.assertEqual(result, {"success": False, "message": "Not applicable."})
        self._assert_logged(logs, "screenshot_upload")

    def test_get_rank_flow_state_uses_error_contract(self) -> None:
        result, logs = self._call(handlers.handle_get_rank_flow_state)
        self.assertEqual(
            result, {"error": "not_applicable", "message": "Not applicable."}
        )
        self.assertTrue(RankFlowStateResponse.model_validate(result).error)
        self._assert_logged(logs, "get_rank_flow_state")

    def test_each_call_returns_a_fresh_object(self) -> None:
        first, _ = self._call(handlers.handle_rank_medal_select, medal="Crusader 3")
        second, _ = self._call(handlers.handle_rank_medal_select, medal="Crusader 3")
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
