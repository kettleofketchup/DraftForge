from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordMessageLog,
    DMType,
)
from events.constants import EventState, SignupStatus
from events.models import Event, EventRepeater, EventSignup, RepeaterSubscription
from league.models import League
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache


class StaffOnlyReadFixture(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="sor_owner", password="x")
        self.org_admin = CustomUser.objects.create_user(
            username="sor_admin", password="x"
        )
        self.org_staff = CustomUser.objects.create_user(
            username="sor_staff", password="x"
        )
        self.league_staff = CustomUser.objects.create_user(
            username="sor_league_staff", password="x"
        )
        self.member = CustomUser.objects.create_user(
            username="sor_member", password="x", discordId="5550001"
        )
        self.signed_up = CustomUser.objects.create_user(
            username="sor_signed_up", password="x", discordId="5550002"
        )
        self.org = Organization.objects.create(name="SOR Org", owner=self.owner)
        self.org.admins.add(self.org_admin)
        self.org.staff.add(self.org_staff)
        self.league = League.objects.create(
            name="SOR League", organization=self.org, steam_league_id=55501
        )
        self.league.staff.add(self.league_staff)
        self.member_org_user = OrgUser.objects.create(
            user=self.member, organization=self.org
        )
        signed_up_org_user = OrgUser.objects.create(
            user=self.signed_up, organization=self.org
        )
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            tournament_league=self.league,
            name="SOR Series",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        self.event = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            tournament_league=self.league,
            name="SOR Event",
            state=EventState.SIGNUPS_OPEN,
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
            discord_announcement=True,
            discord_announcement_channel_id="123",
        )
        EventSignup.objects.create(
            event=self.event, user=self.signed_up, status=SignupStatus.RSVP
        )
        RepeaterSubscription.objects.create(
            event_repeater=self.repeater, user=self.member
        )
        discord_event = DiscordEvent.objects.create(event=self.event, guild_id="g1")
        message_log = DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={},
            success=True,
            source="event_announcement",
            source_id=self.event.pk,
            fired_by=self.org_staff,
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="rsvp",
            discord_user_id=self.signed_up.discordId,
            message_log=message_log,
        )
        DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=signed_up_org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )

    def _get(self, path: str, viewer: CustomUser | None) -> tuple[int, object]:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        response = client.get(path)
        return response.status_code, response.json() if response.content else None

    def assert_denied(self, path: str) -> None:
        for viewer in (None, self.member, self.signed_up):
            with self.subTest(viewer=getattr(viewer, "username", "anonymous")):
                code, _ = self._get(path, viewer)
                self.assertEqual(code, 403)

    def staff_viewers(self) -> tuple[CustomUser, ...]:
        return (self.owner, self.org_admin, self.org_staff, self.league_staff)


class EventDiscordStatePermissionTest(StaffOnlyReadFixture):
    def path(self) -> str:
        return f"/api/events/{self.event.pk}/discord/"

    def test_non_staff_are_denied(self) -> None:
        self.assert_denied(self.path())

    def test_staff_see_logs_and_dms(self) -> None:
        for viewer in self.staff_viewers():
            with self.subTest(viewer=viewer.username):
                code, data = self._get(self.path(), viewer)
                self.assertEqual(code, 200, data)
                self.assertEqual(len(data["logs"]), 1)
                self.assertEqual(len(data["dms"]), 1)

    def test_non_staff_cannot_probe_for_missing_discord_state(self) -> None:
        self.event.discord_event.delete()
        code, _ = self._get(self.path(), self.member)
        self.assertEqual(code, 403)

    def test_cached_staff_response_is_not_served_to_non_staff(self) -> None:
        code, _ = self._get(self.path(), self.org_staff)
        self.assertEqual(code, 200)
        self.assert_denied(self.path())


class EventTaskSchedulePermissionTest(StaffOnlyReadFixture):
    def path(self) -> str:
        return f"/api/events/{self.event.pk}/task-schedule/"

    def test_non_staff_are_denied(self) -> None:
        self.assert_denied(self.path())

    def test_staff_see_schedule(self) -> None:
        for viewer in self.staff_viewers():
            with self.subTest(viewer=viewer.username):
                code, tasks = self._get(self.path(), viewer)
                self.assertEqual(code, 200, tasks)
                fired = [t for t in tasks if t["fired_by"]]
                self.assertEqual(fired[0]["fired_by"]["pk"], self.org_staff.pk)


class RepeaterSubscribersPermissionTest(StaffOnlyReadFixture):
    def path(self) -> str:
        return f"/api/events/repeaters/{self.repeater.pk}/subscribers/"

    def test_non_staff_are_denied(self) -> None:
        self.assert_denied(self.path())

    def test_staff_see_subscribers(self) -> None:
        for viewer in self.staff_viewers():
            with self.subTest(viewer=viewer.username):
                code, rows = self._get(self.path(), viewer)
                self.assertEqual(code, 200, rows)
                self.assertEqual([r["username"] for r in rows], ["sor_member"])
