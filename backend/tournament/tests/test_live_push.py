"""Tournament writes tell the tournament's open pages to refetch (issue #964)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import path
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import HeroDraft
from draft.services.hero import new_herodraft_for_game
from league.models import League
from org.models import Organization
from steam.models import Match
from tournament import broadcast
from tournament.consumers import TournamentConsumer
from tournament.models import Game, Team, Tournament


class LivePushTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="push_admin", password="x", email="push@test.com"
        )
        self.org = Organization.objects.create(name="Push Org", owner=self.admin)
        self.league = League.objects.create(
            name="Push League", organization=self.org, steam_league_id=96401
        )
        self.tournament = Tournament.objects.create(
            name="Push Cup", date_played=timezone.now(), league=self.league
        )
        self.captains = [
            CustomUser.objects.create_user(username=f"push_cap{i}", password="x")
            for i in range(2)
        ]
        self.player = CustomUser.objects.create_user(username="push_p", password="x")
        self.tournament.users.add(*self.captains, self.player)
        self.teams = []
        for i, captain in enumerate(self.captains):
            team = Team.objects.create(
                tournament=self.tournament, name=f"Push {i}", captain=captain
            )
            team.members.add(captain)
            self.teams.append(team)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.teams[0],
            dire_team=self.teams[1],
            round=1,
            position=0,
            bracket_type="winners",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def sent(
        self, call: Callable[[], Response], *, ok: bool = True
    ) -> list[dict[str, Any]]:
        with mock.patch("tournament.broadcast.send") as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = call()
        self.assertEqual(
            response.status_code < 300, ok, getattr(response, "data", None)
        )
        for args in send.call_args_list:
            self.assertEqual(args.args[0], self.tournament.pk)
        return [args.args[1] for args in send.call_args_list]

    def assert_bracket_update(
        self, messages: list[dict[str, Any]], game_id: int | None
    ) -> None:
        self.assertIn({"type": "bracket.update", "game_id": game_id}, messages)

    def assert_tournament_update(
        self, messages: list[dict[str, Any]], kind: str, team_id: int | None = None
    ) -> None:
        self.assertIn(
            {"type": "tournament.update", "kind": kind, "team_id": team_id}, messages
        )

    def test_save_bracket(self) -> None:
        match = {
            "id": "w-1-0",
            "round": 1,
            "position": 0,
            "bracketType": "winners",
            "eliminationType": "single",
            "radiantTeam": {"pk": self.teams[0].pk},
            "direTeam": {"pk": self.teams[1].pk},
            "status": "pending",
        }
        messages = self.sent(
            lambda: self.client.post(
                f"/api/bracket/tournaments/{self.tournament.pk}/save/",
                {"matches": [match]},
                format="json",
            )
        )
        self.assert_bracket_update(messages, None)

    def test_advance_winner(self) -> None:
        messages = self.sent(
            lambda: self.client.post(
                f"/api/bracket/games/{self.game.pk}/advance-winner/",
                {"winner": "radiant"},
                format="json",
            )
        )
        self.assert_bracket_update(messages, self.game.pk)

    def test_unset_winner(self) -> None:
        self.game.winning_team = self.teams[0]
        self.game.status = "completed"
        self.game.save()
        messages = self.sent(
            lambda: self.client.post(
                f"/api/bracket/games/{self.game.pk}/advance-winner/",
                {"winner": None},
                format="json",
            )
        )
        self.assert_bracket_update(messages, self.game.pk)

    def test_refused_write_sends_nothing(self) -> None:
        messages = self.sent(
            lambda: self.client.post(
                f"/api/bracket/games/{self.game.pk}/advance-winner/",
                {"winner": "bogus"},
                format="json",
            ),
            ok=False,
        )
        self.assertEqual(messages, [])

    def test_set_team_placement(self) -> None:
        team = self.teams[0]
        messages = self.sent(
            lambda: self.client.patch(
                f"/api/bracket/tournaments/{self.tournament.pk}/teams/{team.pk}/placement/",
                {"placement": 3},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "placement", team.pk)

    def test_team_rename(self) -> None:
        team = self.teams[0]
        messages = self.sent(
            lambda: self.client.post(
                f"/api/teams/{team.pk}/rename/",
                {"name": "Renamed", "reason": "tidy"},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "team", team.pk)

    def test_team_standin(self) -> None:
        team = self.teams[0]
        messages = self.sent(
            lambda: self.client.post(
                f"/api/teams/{team.pk}/standins/",
                {"user_id": self.player.pk, "reason": "late"},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "team", team.pk)

    def test_team_legacy_patch(self) -> None:
        team = self.teams[0]
        messages = self.sent(
            lambda: self.client.patch(
                f"/api/teams/{team.pk}/",
                {"draft_order": 4},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "team", team.pk)

    def test_team_legacy_patch_roster(self) -> None:
        team = self.teams[0]
        messages = self.sent(
            lambda: self.client.patch(
                f"/api/teams/{team.pk}/",
                {"member_ids": [self.captains[0].pk, self.player.pk]},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "team", team.pk)

    def test_team_create(self) -> None:
        messages = self.sent(
            lambda: self.client.post(
                "/api/team/register",
                {"name": "Fresh", "tournament_id": self.tournament.pk},
                format="json",
            )
        )
        team = Team.objects.get(name="Fresh")
        self.assert_tournament_update(messages, "team", team.pk)

    def test_create_team_from_captain(self) -> None:
        messages = self.sent(
            lambda: self.client.post(
                "/api/tournaments/create-team-from-captain",
                {"tournament_pk": self.tournament.pk, "user_pk": self.player.pk},
                format="json",
            )
        )
        team = Team.objects.get(tournament=self.tournament, captain=self.player)
        self.assert_tournament_update(messages, "team", team.pk)

    def test_add_member(self) -> None:
        outsider = CustomUser.objects.create_user(username="push_out", password="x")
        messages = self.sent(
            lambda: self.client.post(
                f"/api/tournaments/{self.tournament.pk}/members/",
                {"user_id": outsider.pk},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "members")

    def test_remove_player_via_tournament_patch(self) -> None:
        keep = [u.pk for u in self.captains]
        messages = self.sent(
            lambda: self.client.patch(
                f"/api/tournaments/{self.tournament.pk}/",
                {"user_ids": keep},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "settings")

    def test_csv_import(self) -> None:
        CustomUser.objects.create_user(
            username="push_csv", password="x", steamid=76561198099990001
        )
        messages = self.sent(
            lambda: self.client.post(
                f"/api/tournaments/{self.tournament.pk}/import-csv/",
                {"rows": [{"steam_friend_id": "76561198099990001"}]},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "members")

    def test_tournament_settings(self) -> None:
        messages = self.sent(
            lambda: self.client.patch(
                f"/api/tournaments/{self.tournament.pk}/",
                {"name": "Push Cup II"},
                format="json",
            )
        )
        self.assert_tournament_update(messages, "settings")

    def test_steam_link_and_unlink(self) -> None:
        Match.objects.create(
            match_id=7000096401,
            radiant_win=True,
            duration=2000,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=96401,
        )
        linked = self.sent(
            lambda: self.client.post(
                f"/api/steam/games/{self.game.pk}/link-match/",
                {"match_id": 7000096401},
                format="json",
            )
        )
        self.assert_bracket_update(linked, self.game.pk)
        unlinked = self.sent(
            lambda: self.client.delete(f"/api/steam/games/{self.game.pk}/unlink-match/")
        )
        self.assert_bracket_update(unlinked, self.game.pk)

    def test_herodraft_create(self) -> None:
        messages = self.sent(
            lambda: self.client.post(f"/api/games/{self.game.pk}/create-herodraft/")
        )
        self.assertTrue(HeroDraft.objects.filter(game=self.game).exists())
        self.assert_bracket_update(messages, self.game.pk)

    def test_herodraft_reset(self) -> None:
        draft = new_herodraft_for_game(self.game)
        messages = self.sent(
            lambda: self.client.post(f"/api/herodraft/{draft.pk}/reset/")
        )
        self.assert_bracket_update(messages, self.game.pk)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class TournamentSocketUpdateTests(TransactionTestCase):
    def test_tournament_update_reaches_clients(self) -> None:
        application = URLRouter(
            [path("api/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi())]
        )
        tournament = Tournament.objects.create(
            name="Socket Cup", date_played=timezone.now()
        )

        async def scenario() -> list[dict[str, Any]]:
            comm = WebsocketCommunicator(
                application, f"/api/tournament/{tournament.pk}/"
            )
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.receive_json_from()
            layer = get_channel_layer()
            await layer.group_send(
                f"tournament_{tournament.pk}",
                {"type": "tournament.update", "kind": "team", "team_id": 5},
            )
            await layer.group_send(
                f"tournament_{tournament.pk}",
                {"type": "bracket.update", "game_id": None},
            )
            received = [await comm.receive_json_from() for _ in range(2)]
            await comm.disconnect()
            return received

        self.assertEqual(
            async_to_sync(scenario)(),
            [
                {"type": "tournament_update", "kind": "team", "team_id": 5},
                {"type": "bracket_update", "game_id": None},
            ],
        )

    def test_send_survives_a_failing_layer(self) -> None:
        layer = mock.Mock()
        layer.group_send = mock.AsyncMock(side_effect=RuntimeError("redis down"))
        with mock.patch("tournament.broadcast.get_channel_layer", return_value=layer):
            broadcast.send(1, {"type": "bracket.update", "game_id": None})
        layer.group_send.assert_awaited_once()
