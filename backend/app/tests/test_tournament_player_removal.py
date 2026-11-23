"""Removing a captain from a tournament's players never deletes a played team (#841)."""

from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.services.team_audit import log_snapshot_fields, write_team_log
from league.models import League
from org.models import Organization, OrgUser


class TournamentPlayerRemovalTests(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="pr_owner", password="x")
        self.org = Organization.objects.create(name="Removal Org", owner=self.owner)
        self.league = League.objects.create(
            name="Removal League", organization=self.org, steam_league_id=84101
        )
        self.tournament = Tournament.objects.create(
            name="Removal Cup",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
            state="in_progress",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.url = f"/api/tournaments/{self.tournament.pk}/"

    def _users(self, prefix: str, n: int) -> list[CustomUser]:
        users = [
            CustomUser.objects.create_user(username=f"{prefix}_{i}", password="x")
            for i in range(1, n + 1)
        ]
        self.tournament.users.add(*users)
        return users

    def _team(self, name: str, roster: list[CustomUser], order: int) -> Team:
        team = Team.objects.create(
            tournament=self.tournament,
            name=name,
            captain=roster[0],
            draft_order=order,
        )
        team.members.set(roster)
        return team

    def _remove(self, *users: CustomUser) -> int:
        removed = {u.pk for u in users}
        keep = [
            pk
            for pk in self.tournament.users.values_list("pk", flat=True)
            if pk not in removed
        ]
        response = self.client.patch(self.url, {"user_ids": keep}, format="json")
        return response.status_code

    def test_knocked_out_team_survives_captain_removal(self) -> None:
        roster = self._users("ko", 5)
        team = self._team("Knocked Out", roster, 1)
        team.placement = 3
        team.save(update_fields=["placement"])

        self.assertEqual(self._remove(roster[0]), 200)

        team.refresh_from_db()
        self.assertEqual(team.placement, 3)
        self.assertNotEqual(team.captain_id, roster[0].pk)
        self.assertFalse(self.tournament.users.filter(pk=roster[0].pk).exists())

    def test_team_with_games_survives_and_hands_over_captaincy(self) -> None:
        roster = self._users("gm", 5)
        team = self._team("Bracket Team", roster, 1)
        opponent = self._team("Opponent", self._users("op", 5), 2)
        game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=team,
            dire_team=opponent,
            winning_team=opponent,
        )

        self.assertEqual(self._remove(roster[0]), 200)

        team.refresh_from_db()
        game.refresh_from_db()
        self.assertEqual(game.radiant_team_id, team.pk)
        self.assertIsNotNone(team.captain_id)
        self.assertNotEqual(team.captain_id, roster[0].pk)
        self.assertTrue(
            TeamLog.objects.filter(
                team=team, action=TeamLogAction.SYSTEM_SUCCESSION
            ).exists()
        )

    def test_emptied_team_with_history_goes_through_audited_removal(self) -> None:
        roster = self._users("hs", 1)
        team = self._team("Renamed Team", roster, 1)
        write_team_log(
            team,
            snapshot=log_snapshot_fields(team),
            action=TeamLogAction.RENAME,
            via=TeamLogVia.WEB,
            details={},
        )
        team_pk = team.pk

        self.assertEqual(self._remove(roster[0]), 200)

        logs = TeamLog.objects.filter(team_snapshot_id=team_pk)
        self.assertTrue(logs.filter(action=TeamLogAction.RENAME).exists())
        self.assertTrue(
            logs.filter(
                action=TeamLogAction.TEAM_DELETED, via=TeamLogVia.SYSTEM
            ).exists()
        )

    def test_drafted_team_survives(self) -> None:
        roster = self._users("dr", 3)
        team = self._team("Drafted Team", roster, 1)

        self.assertEqual(self._remove(roster[0]), 200)

        team.refresh_from_db()
        self.assertEqual(team.captain_id, roster[1].pk)
        self.assertEqual(
            set(team.members.values_list("pk", flat=True)),
            {roster[1].pk, roster[2].pk},
        )

    def test_pre_draft_captain_only_team_is_deleted(self) -> None:
        captain = self._users("pd", 1)[0]
        team = self._team("Fresh Team", [captain], 1)

        self.assertEqual(self._remove(captain), 200)

        self.assertFalse(Team.objects.filter(pk=team.pk).exists())
        self.assertFalse(self.tournament.users.filter(pk=captain.pk).exists())

    def test_mixed_removal_deletes_only_pre_draft_teams(self) -> None:
        fresh_captain = self._users("mx_fresh", 1)[0]
        fresh = self._team("Mixed Fresh", [fresh_captain], 1)
        played_roster = self._users("mx_played", 5)
        played = self._team("Mixed Played", played_roster, 2)
        played.placement = 2
        played.save(update_fields=["placement"])

        self.assertEqual(self._remove(fresh_captain, played_roster[0]), 200)

        self.assertFalse(Team.objects.filter(pk=fresh.pk).exists())
        played.refresh_from_db()
        self.assertEqual(played.placement, 2)

    def test_failed_update_rolls_back_team_deletion(self) -> None:
        captain = self._users("rb", 1)[0]
        team = self._team("Rollback Team", [captain], 1)
        newcomer = CustomUser.objects.create_user(username="rb_new", password="x")
        keep = [
            pk
            for pk in self.tournament.users.values_list("pk", flat=True)
            if pk != captain.pk
        ]

        with (
            mock.patch.object(
                OrgUser.objects, "bulk_create", side_effect=RuntimeError("boom")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.client.patch(
                self.url, {"user_ids": [*keep, newcomer.pk]}, format="json"
            )

        self.assertTrue(Team.objects.filter(pk=team.pk).exists())
        self.assertTrue(self.tournament.users.filter(pk=captain.pk).exists())
