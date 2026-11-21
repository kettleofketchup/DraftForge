from datetime import timedelta

from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event
from org.models import Organization, OrgUser
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
