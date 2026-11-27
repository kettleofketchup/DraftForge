"""GET /api/bracket/tournaments/<pk>/ reflects team writes with cacheops on."""

from datetime import date
from typing import Any

from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from tournament.models import Game, Team, Tournament
from user.tests.test_cacheops_integration import _redis_reachable


@override_settings(CACHEOPS_ENABLED=True)
class BracketTeamWriteCacheTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.tournament = Tournament.objects.create(
            name="Bracket Cache", date_played=date.today()
        )
        self.captain = CustomUser.objects.create_user(username="bc_captain")
        self.deputy = CustomUser.objects.create_user(username="bc_deputy")
        self.extra = CustomUser.objects.create_user(username="bc_extra")
        self.team = Team.objects.create(
            name="Before", captain=self.captain, tournament=self.tournament
        )
        self.team.members.add(self.captain, self.deputy)
        self.other = Team.objects.create(name="Other", tournament=self.tournament)
        Game.objects.create(
            tournament=self.tournament,
            round=1,
            position=0,
            bracket_type="winners",
            radiant_team=self.team,
            dire_team=self.other,
        )
        self.client = APIClient()

    def radiant(self) -> dict[str, Any]:
        response = self.client.get(f"/api/bracket/tournaments/{self.tournament.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["matches"][0]["radiant_team"]

    def test_rename_shows_on_next_read(self) -> None:
        self.assertEqual(self.radiant()["name"], "Before")
        self.team.name = "After"
        self.team.save()
        self.assertEqual(self.radiant()["name"], "After")

    def test_captain_and_deputy_change_shows_on_next_read(self) -> None:
        self.assertEqual(self.radiant()["captain"]["pk"], self.captain.pk)
        self.assertIsNone(self.radiant()["deputy_captain"])
        self.team.captain = self.deputy
        self.team.deputy_captain = self.captain
        self.team.save()
        team = self.radiant()
        self.assertEqual(team["captain"]["pk"], self.deputy.pk)
        self.assertEqual(team["deputy_captain"]["pk"], self.captain.pk)

    def test_roster_add_shows_on_next_read(self) -> None:
        before = {m["pk"] for m in self.radiant()["members"]}
        self.assertNotIn(self.extra.pk, before)
        self.team.members.add(self.extra)
        after = {m["pk"] for m in self.radiant()["members"]}
        self.assertIn(self.extra.pk, after)
