from datetime import timedelta

from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from discordbot.models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordMessageLog,
    DMType,
)
from events.models import Event
from org.models import OrgUser
from user.models import BaseUserProfile
from user.tests.test_cacheops_integration import _redis_reachable


class EventDetailCacheNamesTest(TransactionTestCase):
    """Real commits so cacheops caches the event detail and evicts on name sync."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        owner = CustomUser.objects.create_user(username="edcn_owner")
        self.org = Organization.objects.create(name="EDCN Org", owner=owner)
        self.host = CustomUser.objects.create_user(
            username="edcn_host", discordNickname="Gwaihir"
        )
        self.org_user = OrgUser.objects.create(
            user=self.host, organization=self.org, guild_nickname="DragonClaw"
        )
        event = Event.objects.create(
            organization=self.org,
            name="EDCN Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            host=self.host,
        )
        self.url = f"/api/events/{event.pk}/"
        self.client = APIClient()

    def _host(self) -> dict:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.json()["host"]

    def test_global_name_change_shows_after_cached_get(self) -> None:
        self.assertEqual(self._host()["discordNickname"], "Gwaihir")
        self.host.discordNickname = "Windlord"
        self.host.save()
        self.assertEqual(self._host()["discordNickname"], "Windlord")

    def test_server_nickname_change_shows_after_cached_get(self) -> None:
        self.assertEqual(self._host()["guildNickname"], "DragonClaw")
        self.org_user.guild_nickname = "Claw"
        self.org_user.save()
        self.assertEqual(self._host()["guildNickname"], "Claw")

    def test_org_going_private_hides_server_nickname(self) -> None:
        self.assertEqual(self._host()["guildNickname"], "DragonClaw")
        self.org.members_private = True
        self.org.save()
        self.assertIsNone(self._host()["guildNickname"])


class EventCacheProfileChangesTest(TransactionTestCase):
    """A profile save must evict the cached event detail and discord state."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        self.owner = CustomUser.objects.create_user(username="ecpc_owner")
        org = Organization.objects.create(name="ECPC Org", owner=self.owner)
        self.host = CustomUser.objects.create_user(
            username="ecpc_host", discordId="5550002"
        )
        self.host.base_profile.nickname = "Thorondor"
        self.host.base_profile.avatar = "oldhash"
        self.host.base_profile.save()
        org_user = OrgUser.objects.create(user=self.host, organization=org)
        self.event = Event.objects.create(
            organization=org,
            name="ECPC Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            host=self.host,
        )
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
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _get(self, path: str) -> dict:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _rename_host(self) -> None:
        profile = BaseUserProfile.objects.get(user=self.host)
        profile.nickname = "Meneldor"
        profile.avatar = "newhash"
        profile.save()

    def test_event_detail_host_follows_profile_change(self) -> None:
        url = f"/api/events/{self.event.pk}/"
        self.assertEqual(self._get(url)["host"]["nickname"], "Thorondor")
        self._rename_host()
        host = self._get(url)["host"]
        self.assertEqual(host["nickname"], "Meneldor")
        self.assertIn("newhash", host["avatarUrl"])

    def test_discord_state_follows_profile_change(self) -> None:
        url = f"/api/events/{self.event.pk}/discord/"
        self.assertEqual(self._get(url)["logs"][0]["nickname"], "Thorondor")
        self._rename_host()
        data = self._get(url)
        log, dm = data["logs"][0], data["dms"][0]
        self.assertEqual(log["nickname"], "Meneldor")
        self.assertEqual(log["avatar"], "newhash")
        self.assertEqual(log["message_log"]["fired_by_nickname"], "Meneldor")
        self.assertEqual(dm["nickname"], "Meneldor")
        self.assertEqual(dm["avatar"], "newhash")
