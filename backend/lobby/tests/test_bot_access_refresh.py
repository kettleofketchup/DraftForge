import json
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings
from structlog.testing import capture_logs

from lobby.bot_access.dota import DotaBotAccess
from lobby.bot_access.schemas import BotAccessSnapshot
from lobby.client import (
    DotaLobbyClient,
    DotaLobbyError,
    DotaLobbyNotConfigured,
    DotaLobbyUnavailable,
)
from lobby.schemas import LeagueRefreshResult
from lobby.tests.test_bot_access import (
    LEAGUE,
    LEAGUE_ID,
    SID1,
    SID2,
    SID3,
    bot,
    bot_leagues,
    holder,
    league,
)


def results(*pairs: tuple[str, str]) -> LeagueRefreshResult:
    return LeagueRefreshResult.model_validate(
        {
            "results": [
                {
                    "bot": name,
                    "status": status,
                    "error": "secret detail" if status == "failed" else None,
                    "leagues": [],
                }
                for name, status in pairs
            ]
        }
    )


@override_settings(DOTA_LOBBY_ENABLED=True)
class DotaBotAccessRefreshTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = MagicMock(spec=DotaLobbyClient)
        self.client.timeout = 15
        self.client.list_bots.return_value = [
            bot("sim_bot_1", steam_id=SID1),
            bot("sim_bot_2", steam_id=SID2),
            bot("sim_bot_3", steam_id=SID3),
        ]
        self.client.get_league.return_value = league([holder("sim_bot_1")])
        self.client.get_bot_leagues.return_value = bot_leagues()
        self.client.refresh_leagues.return_value = results()
        self.factory = MagicMock(return_value=self.client)
        self.provider = DotaBotAccess(client_factory=self.factory, clock=lambda: 0.0)

    def refresh(self) -> BotAccessSnapshot:
        return self.provider.refresh(LEAGUE)

    def test_refresh_ok_merges_rows(self) -> None:
        self.client.refresh_leagues.return_value = results(
            ("sim_bot_1", "ok"), ("SIM_BOT_2", "not_ready")
        )
        with capture_logs() as logs:
            snap = self.refresh()
        self.assertEqual(snap.refresh_outcome, "ok")
        self.assertEqual(snap.service.status, "ok")
        by_position = {row.position: row for row in snap.bots}
        self.assertEqual(by_position[1].refresh, "ok")
        self.assertEqual(by_position[2].refresh, "not_ready")
        self.assertIsNone(by_position[3].refresh)
        self.client.refresh_leagues.assert_called_once_with()
        self.factory.assert_called_once_with()
        refreshed = [e for e in logs if e["event"] == "bot_access_refreshed"]
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["log_level"], "info")
        self.assertEqual(refreshed[0]["system"], "lobby")
        self.assertEqual(refreshed[0]["subsystem"], "bot_access")
        self.assertEqual(refreshed[0]["league_id"], LEAGUE_ID)
        self.assertEqual(refreshed[0]["outcome"], "ok")
        self.assertEqual(
            (refreshed[0]["ok"], refreshed[0]["failed"], refreshed[0]["not_ready"]),
            (1, 0, 1),
        )

    def test_refresh_unknown_status_is_failed(self) -> None:
        self.client.refresh_leagues.return_value = results(
            ("sim_bot_1", "failed"), ("sim_bot_2", "brand_new")
        )
        snap = self.refresh()
        by_position = {row.position: row for row in snap.bots}
        self.assertEqual(by_position[1].refresh, "failed")
        self.assertEqual(by_position[2].refresh, "failed")

    def test_refresh_409_not_supported_rows_present(self) -> None:
        self.client.refresh_leagues.side_effect = DotaLobbyError(
            "invalid_state", status=409
        )
        self.client.get_league.return_value = league()
        snap = self.refresh()
        self.assertEqual(snap.refresh_outcome, "not_supported_upstream")
        self.assertEqual(snap.service.status, "ok")
        self.assertEqual(len(snap.bots), 3)
        self.assertEqual({row.access for row in snap.bots}, {"unknown"})
        self.assertEqual({row.refresh for row in snap.bots}, {None})

    def test_refresh_other_409_unavailable(self) -> None:
        self.client.refresh_leagues.side_effect = DotaLobbyError("conflict", status=409)
        self.assertEqual(self.refresh().refresh_outcome, "unavailable")

    def test_refresh_timeout_timed_out(self) -> None:
        self.client.refresh_leagues.side_effect = DotaLobbyUnavailable("ReadTimeout")
        snap = self.refresh()
        self.assertEqual(snap.refresh_outcome, "timed_out")
        self.assertEqual(snap.service.status, "ok")
        self.assertEqual(len(snap.bots), 3)

    def test_refresh_unreachable_unavailable(self) -> None:
        self.client.refresh_leagues.side_effect = DotaLobbyUnavailable(
            "ConnectionError"
        )
        with capture_logs() as logs:
            snap = self.refresh()
        self.assertEqual(snap.refresh_outcome, "unavailable")
        self.client.list_bots.assert_called_once()
        self.assertEqual(len(snap.bots), 3)
        failed = [e for e in logs if e["event"] == "bot_access_upstream_failed"]
        self.assertEqual([e["action"] for e in failed], ["refresh_leagues"])

    def test_refresh_then_snapshot_unavailable(self) -> None:
        self.client.refresh_leagues.side_effect = DotaLobbyUnavailable(
            "ConnectionError"
        )
        self.client.list_bots.side_effect = DotaLobbyUnavailable("ConnectionError")
        snap = self.refresh()
        self.assertEqual(snap.refresh_outcome, "unavailable")
        self.assertEqual(snap.service.status, "unavailable")
        self.assertEqual(snap.bots, [])

    def test_refresh_error_text_not_returned(self) -> None:
        self.client.refresh_leagues.return_value = results(("sim_bot_1", "failed"))
        with capture_logs() as logs:
            snap = self.refresh()
        dump = json.dumps(snap.model_dump(mode="json"))
        self.assertNotIn("secret detail", dump)
        self.assertNotIn("sim_bot_", dump)
        self.assertNotIn("secret detail", json.dumps(logs, default=str))
        self.assertNotIn("sim_bot_", json.dumps(logs, default=str))

    @override_settings(DOTA_LOBBY_ENABLED=False)
    def test_refresh_disabled(self) -> None:
        snap = self.refresh()
        self.assertEqual(snap.service.status, "disabled")
        self.assertIsNone(snap.refresh_outcome)
        self.assertEqual(snap.bots, [])
        self.factory.assert_not_called()

    def test_refresh_not_configured(self) -> None:
        self.factory.side_effect = DotaLobbyNotConfigured()
        snap = self.refresh()
        self.assertEqual(snap.service.status, "not_configured")
        self.client.refresh_leagues.assert_not_called()

    def test_refresh_invalid_league_not_linked(self) -> None:
        snap = self.provider.refresh("abc")
        self.assertEqual(snap.service.status, "league_not_linked")
        self.factory.assert_not_called()
