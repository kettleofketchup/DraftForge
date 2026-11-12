from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import DotaLobbyLaunch, DotaLobbyMode, GameMode, GameType
from lobby import services, states
from lobby.models import GameLobby
from lobby.tests.helpers import (
    LOBBY_SETTINGS,
    lobby_settings,
    make_game,
    make_team,
    make_tournament,
    make_user,
)


@lobby_settings
class EligibilityTests(TestCase):
    def setUp(self):
        self.game = make_game()

    def _code(self, **kwargs):
        self.game.refresh_from_db()
        return services.lobby_eligibility(self.game, **kwargs).code

    def test_eligible(self):
        self.assertTrue(services.lobby_eligibility(self.game).ok)

    @override_settings(DOTA_LOBBY_ENABLED=False)
    def test_disabled(self):
        self.assertEqual(self._code(), "lobby_disabled")

    def test_mode_off(self):
        self.game.tournament.dota_lobby_mode = DotaLobbyMode.OFF
        self.game.tournament.save()
        self.assertEqual(self._code(), "lobby_mode_off")
        self.assertEqual(self._code(trigger="manual"), "lobby_mode_off")

    def test_manual_mode_blocks_auto_only(self):
        self.game.tournament.dota_lobby_mode = DotaLobbyMode.MANUAL
        self.game.tournament.save()
        self.assertEqual(self._code(), "lobby_mode_manual")
        self.assertEqual(self._code(trigger="manual"), "")

    def test_custom_game_mode_refused(self):
        self.game.tournament.game_mode = GameMode.CUSTOM
        self.game.tournament.save()
        self.assertEqual(self._code(trigger="manual"), "unsupported_game_mode")

    def test_deadlock_refused(self):
        self.game.tournament.game_type = GameType.DEADLOCK
        self.game.tournament.save()
        self.assertEqual(self._code(), "unsupported_game_type")

    def test_auto_needs_tournament_in_progress(self):
        self.game.tournament.state = "future"
        self.game.tournament.save()
        self.assertEqual(self._code(), "tournament_not_in_progress")
        self.assertEqual(self._code(trigger="manual"), "")

    def test_game_not_pending(self):
        self.game.status = "live"
        self.game.save()
        self.assertEqual(self._code(), "game_not_pending")

    def test_teams_missing(self):
        self.game.dire_team = None
        self.game.save()
        self.assertEqual(self._code(), "teams_missing")

    def test_active_lobby(self):
        GameLobby.objects.create(game=self.game, external_ref=f"game:{self.game.pk}")
        self.assertEqual(self._code(), "active_lobby_exists")

    def test_auto_does_not_recreate_ended_lobby(self):
        GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            state=states.TIMED_OUT,
            radiant_team=self.game.radiant_team,
            dire_team=self.game.dire_team,
        )
        self.assertEqual(self._code(), "lobby_already_requested")
        self.assertEqual(self._code(trigger="manual"), "")

    def test_auto_recreates_after_team_change(self):
        GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            state=states.CLOSED,
            state_reason=services.TEAMS_CHANGED,
        )
        self.assertEqual(self._code(), "")

    def _ended_lobby(self, state, **fields):
        return GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            state=state,
            radiant_team=self.game.radiant_team,
            dire_team=self.game.dire_team,
            **fields,
        )

    def test_no_retry_after_a_played_match(self):
        self._ended_lobby(states.FINISHED, provisional_scored=True)
        self.assertEqual(self._code(trigger="manual"), "lobby_match_played")
        self.assertEqual(self._code(), "lobby_match_played")

    def test_no_retry_after_a_finished_lobby_without_a_result_event(self):
        # No match was seen starting, so nothing says it was abandoned.
        self._ended_lobby(states.FINISHED)
        self.assertEqual(self._code(trigger="manual"), "lobby_match_played")

    def test_retry_after_a_started_match_finished_without_a_result(self):
        # release_game puts this game back to pending as abandoned, so
        # organizers (and auto mode) must be able to request a new lobby.
        lobby = self._ended_lobby(
            states.FINISHED, match_id=7001, match_started_at=timezone.now()
        )
        self.assertTrue(services.match_abandoned(lobby))
        self.assertFalse(services.match_played(lobby))
        self.assertEqual(self._code(trigger="manual"), "")

    def test_replay_lets_organizers_host_a_played_match_again(self):
        self._ended_lobby(states.FINISHED, provisional_scored=True)
        self.assertEqual(self._code(trigger="manual", replay=True), "")
        # Auto mode never replays a played match on its own.
        self.assertEqual(self._code(replay=True), "lobby_match_played")

    def test_retry_after_a_match_that_ended_unscored(self):
        self._ended_lobby(states.FINISHED, provisional_scored=False)
        self.assertEqual(self._code(trigger="manual"), "")

    def test_retry_after_lobbies_that_ended_without_a_match(self):
        for state in (states.FAILED, states.TIMED_OUT, states.CLOSED, states.ERROR):
            with self.subTest(state=state):
                GameLobby.objects.filter(game=self.game).delete()
                self._ended_lobby(state)
                self.assertEqual(self._code(trigger="manual"), "")

    def test_played_match_of_other_teams_does_not_block(self):
        self._ended_lobby(states.FINISHED, provisional_scored=True)
        self.game.dire_team = make_team(self.game.tournament, "Replacement")
        self.game.save()
        self.assertEqual(self._code(trigger="manual"), "")

    def test_missing_steam_ids_block_auto_but_manual_may_skip(self):
        no_steam = make_user(steam=False)
        self.game.dire_team.members.add(no_steam)
        eligibility = services.lobby_eligibility(self.game)
        self.assertEqual(eligibility.code, "missing_steam_ids")
        self.assertEqual(eligibility.details, {"user_ids": [no_steam.pk]})
        self.assertEqual(self._code(trigger="manual"), "missing_steam_ids")
        self.assertEqual(self._code(trigger="manual", allow_missing=True), "")
        self.assertEqual(self._code(allow_missing=True), "missing_steam_ids")

    def test_team_too_large(self):
        self.game.radiant_team.members.add(make_user())
        self.assertEqual(self._code(), "team_too_large")

    def test_auto_eligible_games(self):
        other = make_game(make_tournament(dota_lobby_mode=DotaLobbyMode.MANUAL))
        self.assertEqual(services.auto_eligible_games(), [self.game])
        self.assertNotIn(other, services.auto_eligible_games())


@lobby_settings
class BuildRequestTests(TestCase):
    def setUp(self):
        self.tournament = make_tournament(
            dota_lobby_launch=DotaLobbyLaunch.AUTO,
            dota_lobby_region="us_east",
            lobby_steam_league_id=17929,
        )
        self.game = make_game(self.tournament)
        self.claim = services.claim_lobby(self.game.pk)
        self.row = self.claim.game_lobby

    def test_body(self):
        body = self.row.request
        game, radiant, dire = self.game, self.game.radiant_team, self.game.dire_team
        self.assertEqual(body["external_ref"], f"game:{game.pk}")
        self.assertEqual(body["name"], "Spring Cup R2: Ravens vs Owls")
        self.assertEqual(body["game_mode"], "cm")
        self.assertEqual(body["launch"], "auto")
        self.assertEqual(body["region"], "us_east")
        self.assertEqual(body["league_id"], 17929)
        self.assertEqual(body["tv_delay_seconds"], 120)
        self.assertTrue(body["kick_strangers"])
        self.assertEqual(body["teams"]["radiant"]["team_ref"], f"team-{radiant.pk}")
        self.assertEqual(body["teams"]["dire"]["team_ref"], f"team-{dire.pk}")
        players = body["teams"]["radiant"]["players"]
        self.assertEqual(len(players), 5)
        captains = [p for p in players if p.get("captain")]
        self.assertEqual(
            captains,
            [{"account_id": radiant.captain.steam_account_id, "captain": True}],
        )
        self.assertEqual(
            body["metadata"],
            {
                "draftforge_game_id": str(game.pk),
                "tournament_id": str(self.tournament.pk),
                "round": "2",
                "game_lobby_id": str(self.row.pk),
            },
        )
        self.assertNotIn("password", body)
        self.assertEqual(
            (self.row.radiant_team_id, self.row.dire_team_id), (radiant.pk, dire.pk)
        )

    def test_create_body_adds_the_lobby_password(self):
        body = services.create_body(self.row)
        self.assertEqual(body["password"], self.row.password)
        self.assertEqual(
            self.row.password, self.row.game.tournament.dota_lobby_password
        )
        self.assertEqual(
            {k: v for k, v in body.items() if k != "password"}, self.row.request
        )

    def test_claim_is_idempotent(self):
        again = services.claim_lobby(self.game.pk)
        self.assertFalse(again.created)
        self.assertEqual(again.game_lobby, self.row)
        self.assertEqual(GameLobby.objects.filter(game=self.game).count(), 1)

    def test_long_names_truncated(self):
        tournament = make_tournament(name="T" * 60)
        game = make_game(tournament, radiant_team=make_team(tournament, "R" * 80))
        row = services.claim_lobby(game.pk).game_lobby
        self.assertEqual(len(row.request["name"]), 64)
        self.assertEqual(len(row.request["teams"]["radiant"]["name"]), 64)

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_REGION": "eu_west"})
    def test_default_region_and_league_from_league(self):
        tournament = make_tournament()
        game = make_game(tournament)
        row = services.claim_lobby(game.pk).game_lobby
        self.assertEqual(row.request["region"], "eu_west")
        self.assertNotIn("league_id", row.request)

    def test_game_mode_map(self):
        for mode, wire in (
            (GameMode.NORMAL, "ap"),
            (GameMode.TURBO, "turbo"),
            (GameMode.CAPTAINS_MODE, "cm"),
        ):
            with self.subTest(mode=mode):
                game = make_game(make_tournament(game_mode=mode))
                row = services.claim_lobby(game.pk).game_lobby
                self.assertEqual(row.request["game_mode"], wire)

    def test_manual_allow_missing_leaves_players_out(self):
        tournament = make_tournament(dota_lobby_mode=DotaLobbyMode.MANUAL)
        game = make_game(tournament)
        game.dire_team.members.add(make_user(steam=False))
        refused = services.claim_lobby(game.pk, trigger="manual")
        self.assertIsNone(refused.game_lobby)
        self.assertEqual(refused.eligibility.code, "missing_steam_ids")
        row = services.claim_lobby(
            game.pk, trigger="manual", allow_missing=True
        ).game_lobby
        self.assertEqual(len(row.request["teams"]["dire"]["players"]), 5)
        self.assertEqual(row.trigger, "manual")
