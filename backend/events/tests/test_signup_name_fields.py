from datetime import timedelta

from django.db import connection, reset_queries
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from events.constants import SignupStatus
from events.models import Event, EventSignup
from events.services import create_tournament_for_event
from org.models import OrgUser
from tests.cache import flush_run_cache


class SignupNameFieldsTest(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="snf_owner", password="x")
        self.org = Organization.objects.create(
            name="SNF Org", owner=self.owner, members_private=True
        )
        self._seq = 0

    def _event(self, *, tournament: bool) -> Event:
        self._seq += 1
        event = Event.objects.create(
            organization=self.org,
            name=f"SNF Event {self._seq}",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
        )
        if tournament:
            create_tournament_for_event(event)
        return event

    def _signup(self, event: Event, name: str) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=name, password="x", discordNickname=f"{name}_global"
        )
        OrgUser.objects.update_or_create(
            user=user,
            organization=self.org,
            defaults={"guild_nickname": f"{name}_server", "mmr": 4000},
        )
        EventSignup.objects.create(event=event, user=user, status=SignupStatus.RSVP)
        return user

    def _list(self, event: Event, viewer: CustomUser | None) -> tuple[list[dict], int]:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"/api/events/signups/?event={event.pk}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        return rows, len(ctx.captured_queries)

    def test_member_viewer_sees_server_nickname(self) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                event = self._event(tournament=tournament)
                self._signup(event, f"snf_seen_{tournament}")
                rows, _ = self._list(event, self.owner)
                data = rows[0]["user_data"]
                self.assertEqual(data["guildNickname"], f"snf_seen_{tournament}_server")
                self.assertEqual(
                    data["discordNickname"], f"snf_seen_{tournament}_global"
                )

    def test_anonymous_viewer_of_private_org_gets_no_server_nickname_or_mmr(
        self,
    ) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                event = self._event(tournament=tournament)
                self._signup(event, f"snf_hidden_{tournament}")
                rows, _ = self._list(event, None)
                data = rows[0]["user_data"]
                self.assertIsNone(data.get("guildNickname"))
                self.assertNotIn("mmr", data)
                self.assertNotIn("league_mmr", data)
                self.assertEqual(
                    data["discordNickname"], f"snf_hidden_{tournament}_global"
                )

    def test_query_count_does_not_grow_with_signups(self) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                small = self._event(tournament=tournament)
                large = self._event(tournament=tournament)
                self._signup(small, f"snf_q1_{tournament}")
                for i in range(5):
                    self._signup(large, f"snf_q5_{tournament}_{i}")
                _, one = self._list(small, self.owner)
                _, five = self._list(large, self.owner)
                self.assertEqual(one, five)
