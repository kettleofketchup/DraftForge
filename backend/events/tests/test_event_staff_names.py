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
from events.models import Event, EventRepeater, RepeaterSubscription
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache


class EventNameFixture(TestCase):
    private = False

    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="esn_owner", password="x")
        self.org = Organization.objects.create(
            name=f"ESN Org {self.private}",
            owner=self.owner,
            members_private=self.private,
        )
        self.host = CustomUser.objects.create_user(
            username="esn_host",
            password="x",
            discordNickname="Gwaihir",
            discordId="5550001",
        )
        self.host.nickname = "HostSite"
        self.helper = CustomUser.objects.create_user(
            username="esn_helper", password="x", discordNickname=None
        )
        self.host_org_user = OrgUser.objects.create(
            user=self.host, organization=self.org, guild_nickname="DragonClaw"
        )
        OrgUser.objects.create(
            user=self.helper, organization=self.org, guild_nickname="HelperNick"
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="ESN Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
            host=self.host,
        )
        self.event.helpers.add(self.helper)

    def _get(self, path: str, viewer: CustomUser | None = None) -> dict | list:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        response = client.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class PublicOrgStaffNamesTest(EventNameFixture):
    def test_host_and_helpers_carry_discord_names(self) -> None:
        for viewer in (None, self.owner):
            data = self._get(f"/api/events/{self.event.pk}/", viewer)
            host = data["host"]
            self.assertEqual(host["nickname"], "HostSite")
            self.assertEqual(host["discordNickname"], "Gwaihir")
            self.assertEqual(host["guildNickname"], "DragonClaw")
            helper = data["helpers"][0]
            self.assertIsNone(helper["nickname"])
            self.assertIsNone(helper["discordNickname"])
            self.assertEqual(helper["guildNickname"], "HelperNick")

    def test_repeater_subscribers_carry_global_name(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="ESN Series",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        RepeaterSubscription.objects.create(event_repeater=repeater, user=self.host)
        rows = self._get(
            f"/api/events/repeaters/{repeater.pk}/subscribers/", self.owner
        )
        self.assertEqual(rows[0]["nickname"], "HostSite")
        self.assertEqual(rows[0]["discordNickname"], "Gwaihir")

    def test_task_schedule_fired_by_carries_global_name(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(
            discord_announcement=True, discord_announcement_channel_id="1"
        )
        DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={},
            success=True,
            source="event_announcement",
            source_id=self.event.pk,
            fired_by=self.host,
        )
        tasks = self._get(f"/api/events/{self.event.pk}/task-schedule/", self.owner)
        fired = [t["fired_by"] for t in tasks if t.get("fired_by")]
        self.assertTrue(fired)
        self.assertEqual(fired[0]["nickname"], "HostSite")
        self.assertEqual(fired[0]["discordNickname"], "Gwaihir")

    def _discord_state(self) -> dict:
        discord_event = DiscordEvent.objects.create(event=self.event, guild_id="g1")
        message_log = DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={},
            success=True,
            source="event_announcement",
            source_id=self.event.pk,
            fired_by=self.host,
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="rsvp",
            discord_user_id=self.host.discordId,
            message_log=message_log,
        )
        DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=self.host_org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        return self._get(f"/api/events/{self.event.pk}/discord/", self.owner)

    def test_discord_state_rows_carry_discord_names(self) -> None:
        data = self._discord_state()
        log = data["logs"][0]
        self.assertEqual(log["nickname"], "HostSite")
        self.assertEqual(log["discordNickname"], "Gwaihir")
        inline = log["message_log"]
        self.assertEqual(inline["fired_by_nickname"], "HostSite")
        self.assertEqual(inline["fired_by_discordNickname"], "Gwaihir")
        dm = data["dms"][0]
        self.assertEqual(dm["nickname"], "HostSite")
        self.assertEqual(dm["discordNickname"], "Gwaihir")
        self.assertEqual(dm["guildNickname"], "DragonClaw")


class PrivateOrgStaffNamesTest(PublicOrgStaffNamesTest):
    private = True

    def test_host_and_helpers_carry_discord_names(self) -> None:
        for viewer in (None, self.owner):
            data = self._get(f"/api/events/{self.event.pk}/", viewer)
            self.assertEqual(data["host"]["nickname"], "HostSite")
            self.assertEqual(data["host"]["discordNickname"], "Gwaihir")
            self.assertIsNone(data["host"]["guildNickname"])
            self.assertIsNone(data["helpers"][0]["guildNickname"])

    def test_discord_state_rows_carry_discord_names(self) -> None:
        data = self._discord_state()
        dm = data["dms"][0]
        self.assertEqual(dm["discordNickname"], "Gwaihir")
        self.assertIsNone(dm["guildNickname"])
