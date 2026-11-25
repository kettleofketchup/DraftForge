from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from app.tests.test_bracket_placement import SingleEliminationBracket
from lobby.tests.helpers import lobby_settings, make_game
from steam.functions.game_linking import _link_game_to_match
from steam.models import Match
from tournament.models import Game, Team


class UnlinkGameMatchStatusTest(SingleEliminationBracket):
    def link(self, game: Game, winner: Team, match_id: int) -> None:
        match = Match.objects.create(
            match_id=match_id,
            radiant_win=True,
            duration=1800,
            start_time=1700000000,
            game_mode=2,
            lobby_type=1,
        )
        with (
            mock.patch(
                "steam.functions.game_linking._determine_winner_from_match",
                return_value=winner,
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            _link_game_to_match(game, match)

    def test_unlinking_the_match_resets_status_to_pending(self) -> None:
        self.link(self.semi1, self.teams[0], 8430009211)
        self.semi1.refresh_from_db()
        self.assertEqual(self.semi1.status, "completed")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"/api/steam/games/{self.semi1.pk}/unlink-match/"
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.semi1.refresh_from_db()
        self.assertEqual(self.semi1.status, "pending")
        self.assertIn(
            self.semi1.status,
            {c[0] for c in Game._meta.get_field("status").choices},
        )
        self.assertIsNone(self.semi1.gameid)
        self.assertIsNone(self.semi1.winning_team)


@lobby_settings
@mock.patch("lobby.tasks.close_dota_lobby.delay")
@mock.patch("lobby.tasks.create_dota_lobby.delay")
class UnlinkGameMatchLobbyTest(TestCase):
    def test_unlink_in_auto_lobby_mode_queues_a_lobby(
        self, create_delay: mock.MagicMock, close_delay: mock.MagicMock
    ) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            game = make_game()
        Game.objects.filter(pk=game.pk).update(
            status="completed", winning_team=game.radiant_team, gameid=8430009212
        )
        create_delay.reset_mock()
        client = APIClient()
        client.force_authenticate(
            user=CustomUser.objects.create_superuser(
                username="unlink-admin", password="x", email="unlink@test.com"
            )
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = client.delete(f"/api/steam/games/{game.pk}/unlink-match/")

        self.assertEqual(response.status_code, 200, response.content)
        create_delay.assert_called_once_with(game.pk, trigger="auto")
