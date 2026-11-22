"""Count rows outside a team that point at it."""

from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from bracket.models import BracketSlot, TournamentBracket
from league.models import League
from org.models import Organization
from tournament.services.team_references import (
    all_reference_keys,
    team_references,
    team_usage,
)


class TeamReferencesFixture:
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Reset Org")
        self.league = League.objects.create(
            organization=self.org, name="Reset League", steam_league_id=91001
        )
        self.tournament = Tournament.objects.create(
            name="Reset Cup", date_played=timezone.now(), league=self.league
        )
        self.x = CustomUser.objects.create_user(username="reset_x", password="test")
        self.tournament.users.add(self.x)
        self.team = Team.objects.create(
            tournament=self.tournament, name="Resetters", draft_order=3
        )


class TeamReferencesTests(TeamReferencesFixture, TestCase):
    def test_team_references_relation_names(self) -> None:
        expected = {
            "app.Game.radiant_team",
            "app.Game.dire_team",
            "app.Game.winning_team",
            "draft.DraftTeam.tournament_team",
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

    def test_teamlog_not_a_reference_key(self) -> None:
        self.assertNotIn("app.TeamLog.team", all_reference_keys())

    def test_herodraft_chat_not_a_reference_key(self) -> None:
        keys = all_reference_keys()
        self.assertNotIn("draft.HeroDraftChatMessage.team", keys)
        self.assertNotIn("draft.HeroDraftChatMembership.team", keys)


class TeamUsageTests(TeamReferencesFixture, TestCase):
    def test_distinct_rows_per_model(self) -> None:
        other = Team.objects.create(tournament=self.tournament, name="Other")
        game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team,
            dire_team=other,
            winning_team=self.team,
        )
        bracket = TournamentBracket.objects.create(tournament=self.tournament)
        BracketSlot.objects.create(
            bracket=bracket, max_rounds=1, game=game, participant=other
        )

        usage = team_usage(Team.objects.filter(pk__in=[self.team.pk, other.pk]))

        self.assertEqual(
            [(u["model"], u["count"]) for u in usage],
            [("app.Game", 1), ("bracket.BracketSlot", 1)],
        )
        self.assertEqual([t["name"] for t in usage[0]["teams"]], ["Resetters", "Other"])
        self.assertEqual([t["name"] for t in usage[1]["teams"]], ["Other"])

    def test_empty(self) -> None:
        self.assertEqual(team_usage(Team.objects.none()), [])
        self.assertEqual(team_usage([self.team]), [])

    def test_teamlog_rows_are_not_usage(self) -> None:
        TeamLog.objects.create(
            team=self.team,
            team_snapshot_id=self.team.pk,
            team_name=self.team.name,
            via=TeamLogVia.WEB,
            action=TeamLogAction.RENAME,
        )
        self.assertEqual(team_usage([self.team]), [])
