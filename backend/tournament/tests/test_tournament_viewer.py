"""GET /api/tournaments/{pk}/viewer/ reports what the requesting user may do."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event
from events.services import create_tournament_for_event
from league.models import League
from org.models import Organization
from tournament.models import Tournament


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


class LeaguelessEventTournamentViewerTests(TestCase):
    """A tournament spawned by an event without a league belongs to the event's org."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Event Org")
        self.owner = CustomUser.objects.create_user(username="ev_owner", password="x")
        event = Event.objects.create(
            name="League-less Night",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.owner,
            tournament_name="League-less Cup",
        )
        self.tournament = create_tournament_for_event(event)
        assert self.tournament.league_id is None

    def _can_edit(self, user: CustomUser) -> bool:
        client = APIClient()
        client.force_authenticate(user)
        response = client.get(f"/api/tournaments/{self.tournament.pk}/viewer/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["can_edit_tournament"]

    def _user(self, username: str) -> CustomUser:
        return CustomUser.objects.create_user(username=username, password="x")

    def test_event_org_staff_can_edit(self) -> None:
        staff = self._user("ev_staff")
        self.org.staff.add(staff)
        self.assertTrue(self._can_edit(staff))

    def test_event_org_admin_can_edit(self) -> None:
        admin = self._user("ev_admin")
        self.org.admins.add(admin)
        self.assertTrue(self._can_edit(admin))

    def test_staff_of_another_org_cannot_edit(self) -> None:
        other = Organization.objects.create(name="Other Org")
        staff = self._user("ev_other_staff")
        other.staff.add(staff)
        self.assertFalse(self._can_edit(staff))

    def test_player_cannot_edit(self) -> None:
        self.assertFalse(self._can_edit(self._user("ev_player")))
