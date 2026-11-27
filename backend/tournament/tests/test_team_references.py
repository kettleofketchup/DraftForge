"""Count rows outside a team that point at it."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from bracket.models import BracketSlot, TournamentBracket
from draft.models import Draft, DraftOptions, DraftRound, DraftTeam, HeroDraft
from league.models import League
from org.models import Organization
from tests.populate.utils import ensure_org_user
from tournament.models import Game, Team, TeamLog, Tournament
from tournament.models.team_log import TeamLogAction, TeamLogVia
from tournament.services.team_references import (
    _usage_sort_key,
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
            "tournament.Game.radiant_team",
            "tournament.Game.dire_team",
            "tournament.Game.winning_team",
            "draft.DraftTeam.tournament_team",
            "tournament.Tournament.winning_team",
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

        self.assertEqual(refs, {"tournament.Game.radiant_team": 2})
        self.assertEqual(team_references(Team.objects.none()), {})

    def test_teamlog_not_a_reference_key(self) -> None:
        keys = all_reference_keys()
        self.assertTrue(keys)
        self.assertFalse([k for k in keys if k.lower().endswith("teamlog.team")])

    def test_herodraft_chat_not_a_reference_key(self) -> None:
        keys = all_reference_keys()
        self.assertNotIn("draft.HeroDraftChatMessage.team", keys)
        self.assertNotIn("draft.HeroDraftChatMembership.team", keys)

    def test_draft_round_drafting_team_not_a_reference_key(self) -> None:
        self.assertNotIn("draft.DraftRound.drafting_team", all_reference_keys())
        draft = Draft.objects.create(tournament=self.tournament)
        DraftRound.objects.create(
            draft=draft, captain=self.x, drafting_team=self.team, pick_number=1
        )

        self.assertEqual(team_references(Team.objects.filter(pk=self.team.pk)), {})


class DraftRestartWithLinkedRoundsTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Restart Org")
        self.league = League.objects.create(
            organization=self.org, name="Restart League", steam_league_id=91003
        )
        self.tournament = Tournament.objects.create(
            name="Restart Cup", date_played=timezone.now(), league=self.league
        )
        DraftOptions.ensure_for(self.tournament, timer_enabled=False)
        self.admin = CustomUser.objects.create_user(
            username="restart_admin", password="test", is_staff=True, is_superuser=True
        )
        self.teams: list[Team] = []
        for order, name in enumerate(("a", "b"), start=1):
            captain = self.make_user(f"restart_cap_{name}", 3000 + order)
            player = self.make_user(f"restart_p_{name}", 2000 + order)
            self.tournament.users.add(captain, player)
            team = Team.objects.create(
                tournament=self.tournament,
                name=f"Restart {name}",
                captain=captain,
                draft_order=order,
            )
            team.members.add(captain)
            self.teams.append(team)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def make_user(self, username: str, mmr: int) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="test")
        ensure_org_user(user, self.org, mmr=mmr)
        return user

    def init_draft(self) -> object:
        return self.client.post(
            "/api/tournaments/init-draft",
            {"tournament_pk": self.tournament.pk},
            format="json",
        )

    def test_restart_with_linked_rounds_not_blocked(self) -> None:
        self.assertEqual(self.init_draft().status_code, 201)
        draft = Draft.objects.nocache().get(tournament=self.tournament)
        for team in self.teams:
            DraftRound.objects.filter(draft=draft, captain=team.captain).update(
                drafting_team=team
            )
        self.assertTrue(
            DraftRound.objects.nocache()
            .filter(draft=draft, drafting_team__isnull=False)
            .exists()
        )

        resp = self.init_draft()

        self.assertEqual(resp.status_code, 201, getattr(resp, "data", None))
        team_by_captain = {t.captain_id: t.pk for t in self.teams}
        rebuilt = list(DraftRound.objects.nocache().filter(draft=draft))
        self.assertTrue(rebuilt)
        for rnd in rebuilt:
            self.assertEqual(rnd.drafting_team_id, team_by_captain[rnd.captain_id])


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
            [("tournament.Game", 1), ("bracket.BracketSlot", 1)],
        )
        self.assertEqual([t["name"] for t in usage[0]["teams"]], ["Resetters", "Other"])
        self.assertEqual([t["name"] for t in usage[1]["teams"]], ["Other"])

    def test_usage_ordered_by_display_label_not_app_label(self) -> None:
        other = Team.objects.create(tournament=self.tournament, name="Other")
        game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team, dire_team=other
        )
        self.tournament.winning_team = self.team
        self.tournament.save()
        bracket = TournamentBracket.objects.create(tournament=self.tournament)
        BracketSlot.objects.create(
            bracket=bracket, max_rounds=1, game=game, participant=other
        )
        hero_draft = HeroDraft.objects.create(game=game)
        DraftTeam.objects.create(draft=hero_draft, tournament_team=self.team)
        DraftTeam.objects.create(draft=hero_draft, tournament_team=other)

        usage = team_usage(Team.objects.filter(pk__in=[self.team.pk, other.pk]))

        self.assertEqual(
            [u["label"] for u in usage],
            ["game", "tournament result", "bracket slot", "HeroDraft"],
        )

    def test_unlisted_labels_sort_after_listed_ones(self) -> None:
        rows = [
            {"label": "zebra"},
            {"label": "Apple"},
            {"label": "HeroDraft"},
            {"label": "game"},
        ]
        self.assertEqual(
            [r["label"] for r in sorted(rows, key=_usage_sort_key)],
            ["game", "HeroDraft", "Apple", "zebra"],
        )

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
