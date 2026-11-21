"""Creating a team needs edit access to the tournament it goes into."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League, Team, Tournament
from org.models import Organization

CREATE_URLS = ("/api/teams/", "/api/team/register")


class TeamCreatePermissionTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Create Org")
        self.league = League.objects.create(
            organization=self.org, name="Create League", steam_league_id=93001
        )
        self.tournament = Tournament.objects.create(
            name="Create Cup", date_played=timezone.now(), league=self.league
        )
        other_org = Organization.objects.create(name="Other Org")
        self.other_league = League.objects.create(
            organization=other_org, name="Other League", steam_league_id=93002
        )
        self.player = self._user("create_player")
        self.tournament.users.add(self.player)
        captained = Team.objects.create(
            tournament=self.tournament, name="Captained", captain=self.player
        )
        captained.members.add(self.player)
        self.league_staff = self._user("create_league_staff")
        self.league.staff.add(self.league_staff)
        self.other_league_staff = self._user("create_other_staff")
        self.other_league.staff.add(self.other_league_staff)
        self.site_staff = CustomUser.objects.create_user(
            username="create_site_staff", password="x", is_staff=True
        )

    def _user(self, username: str) -> CustomUser:
        return CustomUser.objects.create_user(username=username, password="x")

    def _post(
        self, url: str, user: CustomUser, *, tournament: Tournament | None = None
    ) -> Response:
        client = APIClient()
        client.force_authenticate(user)
        body: dict[str, object] = {"name": f"New {user.username}"}
        if tournament is not None:
            body["tournament_id"] = tournament.pk
        return client.post(url, body, format="json")

    def _clear(self, user: CustomUser) -> None:
        Team.objects.filter(name=f"New {user.username}").delete()

    def _created(self, user: CustomUser) -> bool:
        return Team.objects.nocache().filter(name=f"New {user.username}").exists()

    def test_player_cannot_create_team(self) -> None:
        for url in CREATE_URLS:
            with self.subTest(url=url):
                self._clear(self.player)
                response = self._post(url, self.player, tournament=self.tournament)
                self.assertEqual(response.status_code, 403, response.data)
                self.assertFalse(self._created(self.player))

    def test_staff_of_another_league_cannot_create_team(self) -> None:
        for url in CREATE_URLS:
            with self.subTest(url=url):
                self._clear(self.other_league_staff)
                response = self._post(
                    url, self.other_league_staff, tournament=self.tournament
                )
                self.assertEqual(response.status_code, 403, response.data)
                self.assertFalse(self._created(self.other_league_staff))

    def test_non_site_staff_cannot_create_team_without_tournament(self) -> None:
        for url in CREATE_URLS:
            with self.subTest(url=url):
                self._clear(self.league_staff)
                response = self._post(url, self.league_staff)
                self.assertEqual(response.status_code, 403, response.data)
                self.assertFalse(self._created(self.league_staff))

    def test_tournament_staff_can_create_team(self) -> None:
        for url in CREATE_URLS:
            with self.subTest(url=url):
                self._clear(self.league_staff)
                response = self._post(
                    url, self.league_staff, tournament=self.tournament
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertTrue(self._created(self.league_staff))

    def test_site_staff_can_create_team(self) -> None:
        for url in CREATE_URLS:
            with self.subTest(url=url):
                self._clear(self.site_staff)
                response = self._post(url, self.site_staff, tournament=self.tournament)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertTrue(self._created(self.site_staff))
