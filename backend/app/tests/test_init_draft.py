"""Draft init and restart reset teams in place without destroying them."""

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    Draft,
    Game,
    League,
    Organization,
    Team,
    Tournament,
)
from app.services.team_references import all_reference_keys, team_references
from league.models import LeagueUser
from org.models import OrgUser
from user.tests.test_cacheops_integration import _redis_reachable


class TeamResetFixture:
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Reset Org")
        self.league = League.objects.create(
            organization=self.org, name="Reset League", steam_league_id=91001
        )
        self.tournament = Tournament.objects.create(
            name="Reset Cup", date_played=timezone.now(), league=self.league
        )
        self.x = self.make_user("reset_x")
        self.y = self.make_user("reset_y")
        self.z = self.make_user("reset_z")
        self.tournament.users.add(self.x, self.y, self.z)
        self.team = Team.objects.create(
            tournament=self.tournament, name="Resetters", draft_order=3
        )

    def make_user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="test")
        OrgUser.objects.create(user=user, organization=self.org, mmr=3000)
        return user

    def corrupt_captain(self) -> None:
        self.team.members.set([self.x, self.y])
        self.team.captain = self.z
        self.team.save()

    def member_pks(self, team: Team) -> list[int]:
        return list(Team.objects.get(pk=team.pk).members.values_list("pk", flat=True))


class TeamResetTests(TeamResetFixture, TestCase):
    def test_reset_captain_not_member_keeps_team_and_game(self) -> None:
        self.corrupt_captain()
        game = Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        removed = self.team.reset_to_captain()

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        self.assertEqual(self.member_pks(self.team), [self.z.pk])
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertEqual({u.pk for u in removed}, {self.x.pk, self.y.pk})

    def test_reset_clears_draft_state(self) -> None:
        self.team.members.set([self.x, self.y])
        self.team.captain = self.x
        self.team.deputy_captain = self.y
        self.team.dropin_members.add(self.z)
        self.team.left_members.add(self.y)
        captain_lu = LeagueUser.objects.get(user=self.x, league=self.league)
        other_lu = LeagueUser.objects.get(user=self.y, league=self.league)
        self.team.league_users.set([captain_lu, other_lu])
        self.team.current_points = 9
        self.team.placement = 2
        self.team.draft_reserve_ms = 1234
        self.team.draft_is_ready = True
        self.team.draft_is_connected = True
        self.team.draft_has_connected = True
        self.team.save()

        self.team.reset_to_captain()

        team = Team.objects.get(pk=self.team.pk)
        self.assertEqual(list(team.members.values_list("pk", flat=True)), [self.x.pk])
        self.assertEqual(team.dropin_members.count(), 0)
        self.assertEqual(team.left_members.count(), 0)
        self.assertEqual(
            list(team.league_users.values_list("pk", flat=True)), [captain_lu.pk]
        )
        self.assertIsNone(team.deputy_captain)
        self.assertIsNone(team.draft_reserve_ms)
        self.assertFalse(team.draft_is_ready)
        self.assertFalse(team.draft_is_connected)
        self.assertFalse(team.draft_has_connected)
        self.assertEqual(team.current_points, 0)
        self.assertIsNone(team.placement)
        self.assertEqual(team.name, "Resetters")
        self.assertEqual(team.draft_order, 3)

    def test_dropin_and_left_clear_does_not_delete_team(self) -> None:
        self.team.members.set([self.x])
        self.team.captain = self.x
        self.team.save()
        self.team.dropin_members.add(self.y)
        self.team.left_members.add(self.z)

        self.team.dropin_members.clear()
        self.team.left_members.clear()

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_rebuild_teams_clear_only_with_non_member_captain(self) -> None:
        self.corrupt_captain()
        game = Game.objects.create(tournament=self.tournament, dire_team=self.team)
        draft = Draft.objects.create(tournament=self.tournament)

        draft.rebuild_teams(clear_only=True)

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        self.assertEqual(self.member_pks(self.team), [self.z.pk])
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())

    def test_team_references_relation_names(self) -> None:
        expected = {
            "app.Game.radiant_team",
            "app.Game.dire_team",
            "app.Game.winning_team",
            "app.DraftTeam.tournament_team",
            "app.Tournament.winning_team",
            "bracket.BracketSlot.participant",
            "lobby.GameLobby.radiant_team",
            "lobby.GameLobby.dire_team",
            "lobby.GameLobby.provisional_winner_team",
        }
        keys = all_reference_keys()
        self.assertTrue(expected <= set(keys), expected - set(keys))
        self.assertFalse([k for k in keys if "_members." in k or "_league_users" in k])

    def test_team_references_counts_only_nonzero(self) -> None:
        self.team.members.set([self.x])
        self.team.captain = self.x
        self.team.save()
        other = Team.objects.create(tournament=self.tournament, name="Other")
        Game.objects.create(
            tournament=self.tournament, radiant_team=self.team, dire_team=other
        )
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        refs = team_references(Team.objects.filter(pk=self.team.pk))

        self.assertEqual(refs, {"app.Game.radiant_team": 2})
        self.assertEqual(team_references(Team.objects.none()), {})


class TeamResetCacheTests(TeamResetFixture, TransactionTestCase):
    def test_reset_visible_through_cache(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        self.team.members.set([self.x, self.y])
        self.team.captain = self.x
        self.team.save()
        warm = Team.objects.cache().get(pk=self.team.pk)
        self.assertEqual(
            sorted(warm.members.cache().values_list("pk", flat=True)),
            sorted([self.x.pk, self.y.pk]),
        )

        self.team.reset_to_captain()

        cached = Team.objects.cache().get(pk=self.team.pk)
        self.assertEqual(
            list(cached.members.cache().values_list("pk", flat=True)), [self.x.pk]
        )
