from datetime import timedelta

from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event, EventRepeater, RepeaterSubscription
from org.models import Organization
from user.tests.test_cacheops_integration import _redis_reachable


class RepeaterCacheTest(TransactionTestCase):
    """Real commits so cacheops caches the series payloads and evicts on change."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        owner = CustomUser.objects.create_user(username="rpc_owner")
        self.org = Organization.objects.create(name="RPC Org", owner=owner)
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="RPC Series",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        self.subscriber = CustomUser.objects.create_user(username="rpc_subscriber")
        self.stranger = CustomUser.objects.create_user(username="rpc_stranger")
        self.detail_url = f"/api/events/repeaters/{self.repeater.pk}/"
        self.list_url = f"/api/events/repeaters/?organization={self.org.pk}"

    def _get(self, url: str, user: CustomUser | None = None) -> dict | list:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        response = client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _detail(self, user: CustomUser | None = None) -> dict:
        return self._get(self.detail_url, user)

    def _listed(self, user: CustomUser | None = None) -> dict:
        (row,) = self._get(self.list_url, user)
        return row

    def test_is_subscribed_is_not_shared_between_users(self) -> None:
        RepeaterSubscription.objects.create(
            event_repeater=self.repeater, user=self.subscriber
        )
        self.assertTrue(self._detail(self.subscriber)["is_subscribed"])
        self.assertFalse(self._detail(self.stranger)["is_subscribed"])
        self.assertFalse(self._detail()["is_subscribed"])
        self.assertTrue(self._detail(self.subscriber)["is_subscribed"])

    def test_list_is_subscribed_is_per_user(self) -> None:
        RepeaterSubscription.objects.create(
            event_repeater=self.repeater, user=self.subscriber
        )
        self.assertTrue(self._listed(self.subscriber)["is_subscribed"])
        self.assertFalse(self._listed(self.stranger)["is_subscribed"])
        self.assertFalse(self._listed()["is_subscribed"])
        self.assertTrue(self._listed(self.subscriber)["is_subscribed"])

    def test_subscriber_count_follows_new_subscription(self) -> None:
        self.assertEqual(self._detail()["subscriber_count"], 0)
        self.assertEqual(self._listed()["subscriber_count"], 0)
        RepeaterSubscription.objects.create(
            event_repeater=self.repeater, user=self.subscriber
        )
        self.assertEqual(self._detail()["subscriber_count"], 1)
        self.assertEqual(self._listed()["subscriber_count"], 1)

    def test_organization_name_follows_org_rename(self) -> None:
        self.assertEqual(self._detail()["organization_name"], "RPC Org")
        self.assertEqual(self._listed()["organization_name"], "RPC Org")
        self.org.name = "RPC Renamed"
        self.org.save()
        self.assertEqual(self._detail()["organization_name"], "RPC Renamed")
        self.assertEqual(self._listed()["organization_name"], "RPC Renamed")

    def test_next_event_date_follows_new_event(self) -> None:
        self.assertIsNone(self._detail()["next_event_date"])
        self.assertIsNone(self._listed()["next_event_date"])
        Event.objects.create(
            organization=self.org,
            name="RPC Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            event_repeater=self.repeater,
        )
        self.assertIsNotNone(self._detail()["next_event_date"])
        self.assertIsNotNone(self._listed()["next_event_date"])
