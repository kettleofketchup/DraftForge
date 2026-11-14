from datetime import time, timedelta

from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization
from events.constants import RepeatFrequency
from events.models import EventRepeater, OrgEventDefaults
from events.tests.base import EventTestCase

FOREIGN_ID_ERROR = (
    "Steam league ID 5555 belongs to 'Foreign League'. "
    "Only an admin of that league can use it."
)


class EventLobbyConfigValidationTests(EventTestCase):
    def setUp(self) -> None:
        self.org_staff = CustomUser.objects.create_user(
            username="lobby_org_staff", password="x"
        )
        self.org.staff.add(self.org_staff)
        foreign_owner = CustomUser.objects.create_user(
            username="foreign_owner", password="x"
        )
        foreign_org = Organization.objects.create(
            name="Foreign Org", owner=foreign_owner
        )
        League.objects.create(
            name="Foreign League", organization=foreign_org, steam_league_id=5555
        )
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=30),
            created_by=self.admin,
            tournament_league=self.league,
        )
        self.defaults = OrgEventDefaults.objects.create(organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.org_staff)

    def write(self, target: str, data: dict[str, object]) -> Response:
        if target == "event":
            return self.client.patch(
                f"/api/events/{self.event.pk}/", data, format="json"
            )
        if target == "series":
            return self.client.patch(
                f"/api/events/repeaters/{self.repeater.pk}/", data, format="json"
            )
        if target == "defaults":
            return self.client.patch(
                f"/api/events/defaults/{self.defaults.pk}/", data, format="json"
            )
        return self.client.post(
            f"/api/events/repeaters/{self.repeater.pk}/create-event/",
            {"scheduled_at": (tz.now() + timedelta(days=3)).isoformat(), **data},
            format="json",
        )

    TARGETS = ("event", "series", "defaults", "one_off")

    def test_foreign_steam_league_id_refused(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, {"lobby_steam_league_id": 5555})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertEqual(
                    str(resp.data["lobby_steam_league_id"][0]), FOREIGN_ID_ERROR
                )

    def test_non_positive_steam_league_id_refused(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, {"lobby_steam_league_id": 0})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertIn("lobby_steam_league_id", resp.data)

    def test_draft_time_below_one_refused(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, {"captains_draft_time": 0})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertIn("captains_draft_time", resp.data)

    def test_own_league_steam_id_allowed_on_event(self) -> None:
        resp = self.write("event", {"lobby_steam_league_id": 99999})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.event.refresh_from_db()
        self.assertEqual(self.event.lobby_steam_league_id, 99999)

    def test_unowned_steam_id_allowed_on_defaults(self) -> None:
        resp = self.write("defaults", {"lobby_steam_league_id": 123})
        self.assertEqual(resp.status_code, 200, resp.data)
