"""GET /api/tournaments/{pk}/viewer/ reports what the requesting user may do."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, League, Tournament
from org.models import Organization


class TournamentViewerTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Viewer Org")
        self.league = League.objects.create(
            organization=self.org, name="Viewer League", steam_league_id=94001
        )
        self.tournament = Tournament.objects.create(
            name="Viewer Cup", date_played=timezone.now(), league=self.league
        )
        self.url = f"/api/tournaments/{self.tournament.pk}/viewer/"

    def _user(self, username: str, **extra: bool) -> CustomUser:
        return CustomUser.objects.create_user(username=username, password="x", **extra)

    def _can_edit(self, user: CustomUser | None) -> bool:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["can_edit_tournament"]

    def test_league_staff_can_edit(self) -> None:
        staff = self._user("viewer_league_staff")
        self.league.staff.add(staff)
        self.assertTrue(self._can_edit(staff))

    def test_org_staff_can_edit(self) -> None:
        staff = self._user("viewer_org_staff")
        self.org.staff.add(staff)
        self.assertTrue(self._can_edit(staff))

    def test_site_staff_can_edit(self) -> None:
        self.assertTrue(self._can_edit(self._user("viewer_site", is_staff=True)))

    def test_player_cannot_edit(self) -> None:
        player = self._user("viewer_player")
        self.tournament.users.add(player)
        self.assertFalse(self._can_edit(player))

    def test_anonymous_cannot_edit(self) -> None:
        self.assertFalse(self._can_edit(None))

    def test_unknown_tournament_is_404(self) -> None:
        response = APIClient().get("/api/tournaments/999999/viewer/")
        self.assertEqual(response.status_code, 404)
