from unittest import mock

from django.test import TestCase, override_settings

from app.models import DotaLobbyMode, DraftTeam, HeroDraft
from lobby import services, states
from lobby.models import GameLobby
from lobby.tests.helpers import (
    LOBBY_SETTINGS,
    lobby_settings,
    make_game,
    make_team,
    make_tournament,
)


@lobby_settings
@mock.patch("lobby.tasks.close_dota_lobby.delay")
@mock.patch("lobby.tasks.create_dota_lobby.delay")
class GameSignalTests(TestCase):
    def save(self, game):
        with self.captureOnCommitCallbacks(execute=True):
            game.save()

    def test_auto_create_when_eligible(self, create_delay, close_delay):
        with self.captureOnCommitCallbacks(execute=True):
            game = make_game()
        create_delay.assert_called_once_with(game.pk, trigger="auto")

    def test_no_create_when_not_eligible(self, create_delay, close_delay):
        tournament = make_tournament(dota_lobby_mode=DotaLobbyMode.MANUAL)
        with self.captureOnCommitCallbacks(execute=True):
            game = make_game(tournament)
            game.save()
        create_delay.assert_not_called()

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_ENABLED": False})
    def test_nothing_when_disabled(self, create_delay, close_delay):
        with self.captureOnCommitCallbacks(execute=True):
            make_game()
        create_delay.assert_not_called()

    def test_unrelated_save_does_not_requeue(self, create_delay, close_delay):
        game = make_game()
        services.claim_lobby(game.pk)
        create_delay.reset_mock()
        game.position = 3
        self.save(game)
        create_delay.assert_not_called()
        close_delay.assert_not_called()

    def test_team_change_closes_and_recreates(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.WAITING
        row.save()
        create_delay.reset_mock()

        game.dire_team = make_team(game.tournament, "Bats")
        self.save(game)

        row.refresh_from_db()
        self.assertEqual(
            (row.state, row.state_reason), ("closed", services.TEAMS_CHANGED)
        )
        close_delay.assert_called_once_with(row.pk, "lob_1")
        create_delay.assert_called_once_with(game.pk, trigger="auto")

    def test_completed_game_closes_pregame_lobby(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.WAITING
        row.save()
        create_delay.reset_mock()

        # A forfeit decided with advance-winner: same teams, game completed.
        game.winning_team = game.radiant_team
        game.status = "completed"
        self.save(game)

        row.refresh_from_db()
        self.assertEqual(
            (row.state, row.state_reason), ("closed", services.GAME_COMPLETED)
        )
        close_delay.assert_called_once_with(row.pk, "lob_1")
        create_delay.assert_not_called()

    def test_completed_game_keeps_lobby_in_match(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.IN_GAME
        row.save()
        game.winning_team = game.radiant_team
        game.status = "completed"
        self.save(game)
        row.refresh_from_db()
        self.assertEqual((row.state, row.ended), ("in_game", False))
        close_delay.assert_not_called()

    def test_slot_swap_is_not_a_team_change(self, create_delay, close_delay):
        game = make_game()
        services.claim_lobby(game.pk)
        game.radiant_team, game.dire_team = game.dire_team, game.radiant_team
        self.save(game)
        self.assertFalse(GameLobby.objects.get(game=game).ended)
        close_delay.assert_not_called()

    def test_team_removed_closes_without_recreate(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        create_delay.reset_mock()
        game.dire_team = None
        self.save(game)
        row.refresh_from_db()
        self.assertTrue(row.ended)
        close_delay.assert_not_called()  # never accepted: nothing to close
        create_delay.assert_not_called()

    def test_deleted_game_closes_lobby(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.READY
        row.save()
        with self.captureOnCommitCallbacks(execute=True):
            game.delete()
        close_delay.assert_called_once_with(row.pk, "lob_1")
        self.assertFalse(GameLobby.objects.filter(pk=row.pk).exists())

    def test_lobby_in_game_is_left_alone(self, create_delay, close_delay):
        game = make_game()
        row = services.claim_lobby(game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.IN_GAME
        row.save()
        game.dire_team = make_team(game.tournament, "Bats")
        self.save(game)
        row.refresh_from_db()
        self.assertEqual(row.state, "in_game")
        close_delay.assert_not_called()


@lobby_settings
@mock.patch("lobby.tasks.create_dota_lobby.delay")
@mock.patch("lobby.tasks.flip_lobby_sides.delay")
class HeroDraftSignalTests(TestCase):
    def setUp(self):
        self.game = make_game()
        self.row = services.claim_lobby(self.game.pk).game_lobby
        self.row.lobby_id = "lob_1"
        self.row.state = states.WAITING
        self.row.save()
        self.draft = HeroDraft.objects.create(game=self.game)
        DraftTeam.objects.create(
            draft=self.draft, tournament_team=self.game.radiant_team, is_radiant=False
        )
        DraftTeam.objects.create(
            draft=self.draft, tournament_team=self.game.dire_team, is_radiant=True
        )

    def complete(self):
        self.draft.state = "completed"
        with self.captureOnCommitCallbacks(execute=True):
            self.draft.save()

    def test_flip_when_draft_chose_other_side(self, flip_delay, create_delay):
        self.complete()
        flip_delay.assert_called_once_with(
            self.row.pk, "lob_1", f"team-{self.game.dire_team_id}"
        )

    def test_no_flip_when_sides_match(self, flip_delay, create_delay):
        self.draft.draft_teams.update(is_radiant=None)
        self.draft.draft_teams.filter(tournament_team=self.game.radiant_team).update(
            is_radiant=True
        )
        self.complete()
        flip_delay.assert_not_called()

    def test_no_flip_before_lobby_exists_in_game(self, flip_delay, create_delay):
        self.row.state = states.PENDING
        self.row.save()
        self.complete()
        flip_delay.assert_not_called()

    def test_no_flip_until_completed(self, flip_delay, create_delay):
        with self.captureOnCommitCallbacks(execute=True):
            self.draft.save()
        flip_delay.assert_not_called()
