"""An EventTeam stays on the event it was created for (#571)."""

from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from events.models import EventTeam
from events.tests.base import EventTestCase


class EventTeamEventLockTests(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        other_owner = CustomUser.objects.create_user(
            username="other_org_owner", password="testpass"
        )
        self.other_org = Organization.objects.create(
            name="Other Org", owner=other_owner
        )
        self.other_event = self.make_event(organization=self.other_org)
        self.team = EventTeam.objects.create(
            event=self.event, name="Locked", captain=self.admin
        )

    def test_patch_event_to_another_org_rejected(self) -> None:
        response = self.client.patch(
            f"/api/events/teams/{self.team.pk}/",
            {"event": self.other_event.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["event"]], ["Event cannot be changed."]
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.event_id, self.event.pk)

    def test_patch_same_event_and_name_accepted(self) -> None:
        response = self.client.patch(
            f"/api/events/teams/{self.team.pk}/",
            {"event": self.event.pk, "name": "Renamed"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Renamed")
