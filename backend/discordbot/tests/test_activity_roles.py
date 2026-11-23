from datetime import date

from django.test import TestCase

from app.models import CustomUser
from discordbot.activity_roles import draft_role, involves_user
from draft.models import Draft, DraftTeam, HeroDraft
from league.models import League
from org.models import Organization
from tournament.models import Game, Team, Tournament


class DraftRoleTests(TestCase):
    def setUp(self) -> None:
        org = Organization.objects.create(name="Roles Org")
        self.league = League.objects.create(name="Roles League", organization=org)
        self.tournament = Tournament.objects.create(
            name="Roles", date_played=date.today(), league=self.league
        )
        self.captain = CustomUser.objects.create_user(username="r-captain")
        self.player = CustomUser.objects.create_user(username="r-player")
        self.staff = CustomUser.objects.create_user(username="r-staff")
        self.league.staff.add(self.staff)
        self.viewer = CustomUser.objects.create_user(username="r-viewer")
        self.bench_captain = CustomUser.objects.create_user(username="r-bench")

        self.team = Team.objects.create(
            name="A", tournament=self.tournament, captain=self.captain
        )
        self.team.members.add(self.captain, self.player)
        bench = Team.objects.create(
            name="Bench", tournament=self.tournament, captain=self.bench_captain
        )
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        DraftTeam.objects.create(draft=self.hero, tournament_team=self.team)
        self.other_hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        DraftTeam.objects.create(draft=self.other_hero, tournament_team=bench)
        self.team_draft = Draft.objects.create(tournament=self.tournament)

    def test_hero_roles(self) -> None:
        cases = {
            self.captain: "captain",
            self.player: "player",
            self.staff: "staff",
            self.viewer: "spectator",
            self.bench_captain: "spectator",
        }
        for user, role in cases.items():
            with self.subTest(user=user.username):
                self.assertEqual(draft_role(user, "hero", self.hero.pk), role)

    def test_team_roles(self) -> None:
        cases = {
            self.captain: "captain",
            self.bench_captain: "captain",
            self.player: "player",
            self.staff: "staff",
            self.viewer: "spectator",
        }
        for user, role in cases.items():
            with self.subTest(user=user.username):
                self.assertEqual(draft_role(user, "team", self.team_draft.pk), role)

    def test_captain_who_is_staff_is_captain(self) -> None:
        self.league.staff.add(self.captain)
        site_staff = CustomUser.objects.create_user(username="r-site", is_staff=True)
        self.team.members.add(site_staff)
        self.assertEqual(draft_role(self.captain, "hero", self.hero.pk), "captain")
        self.assertEqual(
            draft_role(self.captain, "team", self.team_draft.pk), "captain"
        )
        self.assertEqual(draft_role(site_staff, "hero", self.hero.pk), "player")

    def test_missing_draft_is_spectator(self) -> None:
        self.assertEqual(draft_role(self.captain, "hero", 999_999), "spectator")
        self.assertEqual(draft_role(self.captain, "team", 999_999), "spectator")

    def test_draft_without_tournament(self) -> None:
        loose = HeroDraft.objects.create(game=Game.objects.create(tournament=None))
        DraftTeam.objects.create(draft=loose, tournament_team=self.team)
        self.assertEqual(draft_role(self.player, "hero", loose.pk), "player")
        self.assertEqual(draft_role(self.staff, "hero", loose.pk), "spectator")

    def test_reads_bypass_cacheops(self) -> None:
        self.assertEqual(draft_role(self.viewer, "hero", self.hero.pk), "spectator")
        self.assertEqual(
            draft_role(self.viewer, "team", self.team_draft.pk), "spectator"
        )
        Team.objects.filter(pk=self.team.pk).update(captain=self.viewer)
        self.assertEqual(draft_role(self.viewer, "hero", self.hero.pk), "captain")
        self.assertEqual(draft_role(self.viewer, "team", self.team_draft.pk), "captain")

    def test_involves_user(self) -> None:
        self.assertTrue(involves_user("captain"))
        self.assertTrue(involves_user("player"))
        self.assertFalse(involves_user("staff"))
        self.assertFalse(involves_user("spectator"))
