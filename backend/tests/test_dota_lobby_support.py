"""The dota_lobby E2E test data and the test endpoints that serve it.

Guards what the 18-dota-lobby Playwright specs rely on: the populated data
(tests.populate.dota_lobby), the reset between spec files, and the endpoints
in tests.test_dota_lobby, including the simulator proxy.
"""

from __future__ import annotations

from unittest import mock

import requests
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from app.models import DotaLobbyMode, Game, Team, Tournament
from events.models import Event, EventRepeater, EventSignup
from lobby import services, states
from lobby.models import GameLobby
from lobby.passwords import PasswordMode
from tests import test_dota_lobby as views
from tests.data.dota_lobby import (
    LOBBY_FIXED_PASSWORD,
    LOBBY_LIFECYCLE_TOURNAMENT_NAME,
    LOBBY_RANDOM_EVENT_NAME,
    LOBBY_REGISTERED_USER,
    LOBBY_ROSTERED_USER,
    LOBBY_SERIES_NAME,
    LOBBY_STEAM_LEAGUE_ID,
)
from tests.dota_lobby_sim import SimResponse
from tests.populate.dota_lobby import (
    dota_lobby_test_data,
    populate_dota_lobby_data,
    reset_dota_lobby_data,
)

SIM_ENV = {
    "DOTA_LOBBY_URL": "http://dota-lobby:8080",
    "DOTA_LOBBY_API_KEY": "sim-key",
}
factory = APIRequestFactory()


def _test_env():
    return mock.patch.object(views, "isTestEnvironment", return_value=True)


class DotaLobbyPopulateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        populate_dota_lobby_data(force=True)
        cls.data = dota_lobby_test_data()

    def test_series_event_and_tournament_use_the_fixed_password(self):
        series = EventRepeater.objects.get(name=LOBBY_SERIES_NAME)
        event = Event.objects.get(pk=self.data["series_event"]["pk"])
        self.assertEqual(series.dota_lobby_password_mode, PasswordMode.FIXED)
        self.assertEqual(event.event_repeater_id, series.pk)
        self.assertFalse(event.is_off_schedule)
        self.assertEqual(event.state, "upcoming")
        self.assertEqual(event.dota_lobby_password, LOBBY_FIXED_PASSWORD)
        self.assertEqual(event.tournament.dota_lobby_password, LOBBY_FIXED_PASSWORD)
        self.assertEqual(event.tournament.dota_lobby_mode, DotaLobbyMode.MANUAL)

    def test_random_event_has_its_own_password(self):
        event = Event.objects.get(name=LOBBY_RANDOM_EVENT_NAME)
        self.assertEqual(event.dota_lobby_password_mode, PasswordMode.RANDOM)
        self.assertTrue(event.dota_lobby_password)
        self.assertNotEqual(event.dota_lobby_password, LOBBY_FIXED_PASSWORD)
        self.assertEqual(
            event.tournament.dota_lobby_password, event.dota_lobby_password
        )

    @override_settings(DOTA_LOBBY_ENABLED=True)
    def test_first_round_games_can_get_a_manual_lobby(self):
        tournaments = [
            self.data["series_event"]["tournament"],
            self.data["random_event"]["tournament"],
            self.data["lifecycle_tournament"],
        ]
        games = [g for t in tournaments for g in t["games"] if g["round"] == 1]
        self.assertEqual(len(games), 4)
        for entry in games:
            game = Game.objects.get(pk=entry["pk"])
            eligibility = services.lobby_eligibility(
                game, trigger=GameLobby.Trigger.MANUAL
            )
            self.assertTrue(eligibility.ok, (game.tournament.name, eligibility))
            # Manual mode: nothing creates a lobby by itself.
            self.assertFalse(services.lobby_eligibility(game).ok)
            self.assertEqual(
                services._league_id(game), LOBBY_STEAM_LEAGUE_ID, game.tournament.name
            )

    def test_roles(self):
        tournament = Tournament.objects.get(
            pk=self.data["series_event"]["tournament"]["pk"]
        )
        rostered = Team.objects.get(
            tournament=tournament, captain_id=LOBBY_ROSTERED_USER.pk
        )
        self.assertEqual(rostered.name, "Lobby Gamma")
        self.assertTrue(
            EventSignup.objects.filter(
                event_id=self.data["series_event"]["pk"],
                user_id=LOBBY_REGISTERED_USER.pk,
                status="approved",
            ).exists()
        )
        self.assertFalse(
            Team.objects.filter(members__pk=LOBBY_REGISTERED_USER.pk).exists()
        )

    def test_populate_is_repeatable(self):
        populate_dota_lobby_data(force=True)
        self.assertEqual(
            Tournament.objects.filter(name=LOBBY_LIFECYCLE_TOURNAMENT_NAME).count(), 1
        )
        self.assertEqual(
            EventRepeater.objects.filter(name=LOBBY_SERIES_NAME).count(), 1
        )


class DotaLobbyResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        populate_dota_lobby_data(force=True)

    def setUp(self):
        self.data = dota_lobby_test_data()
        self.game = Game.objects.get(
            pk=self.data["lifecycle_tournament"]["games"][0]["pk"]
        )

    @mock.patch("tests.populate.dota_lobby.simulator_request")
    @mock.patch("tests.populate.dota_lobby.DotaLobbyClient")
    def test_reset_ends_lobbies_and_restores_games_and_passwords(self, client_cls, sim):
        # A match an earlier spec played: it would block the next create.
        played = GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            lobby_id="lob_0",
            state=states.FINISHED,
            provisional_scored=True,
        )
        GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            lobby_id="lob_1",
            state=states.IN_GAME,
            close_pending=True,
        )
        Game.objects.filter(pk=self.game.pk).update(status="live")
        series = EventRepeater.objects.get(name=LOBBY_SERIES_NAME)
        series.dota_lobby_password = "changed-by-a-spec"
        series.save()
        random_event = Event.objects.get(name=LOBBY_RANDOM_EVENT_NAME)
        old_random = random_event.dota_lobby_password

        data = reset_dota_lobby_data()

        client_cls.return_value.close_lobby.assert_called_once_with("lob_1")
        self.assertFalse(GameLobby.objects.filter(pk=played.pk).exists())
        sim.assert_called_once()
        row = GameLobby.objects.get(lobby_id="lob_1")
        self.assertTrue(row.ended)
        self.assertEqual(row.state, states.CLOSED)
        self.assertFalse(row.close_pending)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "pending")
        with override_settings(DOTA_LOBBY_ENABLED=True):
            self.assertTrue(
                services.lobby_eligibility(
                    self.game, trigger=GameLobby.Trigger.MANUAL
                ).ok
            )
        series_event = Event.objects.get(pk=data["series_event"]["pk"])
        self.assertEqual(series_event.dota_lobby_password, LOBBY_FIXED_PASSWORD)
        self.assertEqual(
            series_event.tournament.dota_lobby_password, LOBBY_FIXED_PASSWORD
        )
        random_event.refresh_from_db()
        self.assertNotEqual(random_event.dota_lobby_password, old_random)
        self.assertEqual(
            random_event.tournament.dota_lobby_password,
            random_event.dota_lobby_password,
        )

    @mock.patch("tests.populate.dota_lobby.simulator_request")
    @mock.patch("tests.populate.dota_lobby.DotaLobbyClient")
    def test_reset_without_open_lobbies_never_calls_dota_lobby(self, client_cls, sim):
        reset_dota_lobby_data()
        client_cls.assert_not_called()


class DotaLobbyEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        populate_dota_lobby_data(force=True)

    def _with_session(self, request):
        SessionMiddleware(lambda r: None).process_request(request)
        return request

    def test_login_by_role(self):
        request = self._with_session(
            factory.post("/api/tests/login-dota-lobby/rostered/")
        )
        with _test_env():
            resp = views.login_dota_lobby(request, role="rostered")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["user"]["pk"], LOBBY_ROSTERED_USER.pk)

        request = self._with_session(
            factory.post("/api/tests/login-dota-lobby/nobody/")
        )
        with _test_env():
            resp = views.login_dota_lobby(request, role="nobody")
        self.assertEqual(resp.status_code, 400)

    def test_endpoints_are_hidden_outside_tests(self):
        with mock.patch.object(views, "isTestEnvironment", return_value=False):
            resp = views.dota_lobby_data(factory.get("/api/tests/dota-lobby/data/"))
            self.assertEqual(resp.status_code, 404)
            resp = views.dota_lobby_sim_proxy(
                factory.get("/api/tests/dota-lobby-sim/lobbies"), path="lobbies"
            )
            self.assertEqual(resp.status_code, 404)

    def test_game_lobby_lookup(self):
        game = Game.objects.filter(
            tournament__name=LOBBY_LIFECYCLE_TOURNAMENT_NAME
        ).first()
        with _test_env():
            resp = views.dota_lobby_game_lobby(factory.get("/x/"), game_pk=game.pk)
        self.assertEqual(resp.data, {"lobby": None})
        GameLobby.objects.create(
            game=game,
            external_ref=f"game:{game.pk}",
            lobby_id="lob_9",
            state=states.WAITING,
            password="pw",
        )
        with _test_env():
            resp = views.dota_lobby_game_lobby(factory.get("/x/"), game_pk=game.pk)
        self.assertEqual(resp.data["lobby"]["lobby_id"], "lob_9")
        self.assertEqual(resp.data["lobby"]["password"], "pw")


@mock.patch.dict("os.environ", SIM_ENV)
class DotaLobbySimulatorProxyTests(TestCase):
    @mock.patch("tests.dota_lobby_sim.requests.request")
    def test_forwards_method_path_body_and_key(self, request):
        request.return_value = mock.Mock(
            status_code=409, json=lambda: {"code": "seat_taken"}
        )
        with _test_env():
            resp = views.dota_lobby_sim_proxy(
                factory.post(
                    "/api/tests/dota-lobby-sim/lobbies/lob_1/players/5/seat",
                    {"team": "radiant"},
                    format="json",
                ),
                path="lobbies/lob_1/players/5/seat",
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data, {"code": "seat_taken"})
        args, kwargs = request.call_args
        self.assertEqual(
            args, ("POST", "http://dota-lobby:8080/v1/sim/lobbies/lob_1/players/5/seat")
        )
        self.assertEqual(kwargs["json"], {"team": "radiant"})
        self.assertEqual(kwargs["headers"]["X-API-Key"], "sim-key")
        self.assertFalse(kwargs["allow_redirects"])

    @mock.patch("tests.dota_lobby_sim.requests.request")
    def test_rejects_paths_outside_the_control_api(self, request):
        for path in ("../lobbies", "lobbies/../../v1/lobbies", "lobbies?x=1", ""):
            with _test_env():
                resp = views.dota_lobby_sim_proxy(factory.get("/x/"), path=path)
            self.assertEqual(resp.status_code, 400, path)
        request.assert_not_called()

    @mock.patch(
        "tests.dota_lobby_sim.requests.request",
        side_effect=requests.ConnectionError("refused"),
    )
    def test_unreachable_simulator_is_503(self, _request):
        with _test_env():
            resp = views.dota_lobby_sim_proxy(factory.get("/x/"), path="settings")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.data["code"], "simulator_unavailable")

    def test_status_reports_the_test_league(self):
        answers = {
            "/readyz": SimResponse(200, {"status": "ready"}),
            "/health": SimResponse(200, {"simulation": True}),
            "/v1/leagues": SimResponse(
                200,
                {
                    "leagues": [
                        {
                            "league_id": LOBBY_STEAM_LEAGUE_ID,
                            "holders": [{"verified": True}],
                        },
                        {"league_id": 1, "holders": [{"verified": False}]},
                    ]
                },
            ),
        }
        with (
            _test_env(),
            mock.patch.object(
                views, "simulator_request", side_effect=lambda m, p, **k: answers[p]
            ),
        ):
            resp = views.dota_lobby_simulator(factory.get("/x/"))
        self.assertTrue(resp.data["available"])
        self.assertEqual(resp.data["verified_leagues"], [LOBBY_STEAM_LEAGUE_ID])

        answers["/health"] = SimResponse(200, {"simulation": False})
        with (
            _test_env(),
            mock.patch.object(
                views, "simulator_request", side_effect=lambda m, p, **k: answers[p]
            ),
        ):
            resp = views.dota_lobby_simulator(factory.get("/x/"))
        self.assertFalse(resp.data["available"])

    def test_status_without_a_url_is_503(self):
        with mock.patch.dict("os.environ", {"DOTA_LOBBY_URL": ""}), _test_env():
            resp = views.dota_lobby_simulator(factory.get("/x/"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.data["code"], "not_configured")
