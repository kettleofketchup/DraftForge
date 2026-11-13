"""Event end time, read-only host/helpers/state and the event detail cache."""

from datetime import time, timedelta
from typing import Any
from unittest.mock import patch

from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.cache_utils import invalidate_obj
from app.models import CustomUser, Organization, PositionsModel
from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater
from events.serializers import ONE_OFF_OVERRIDE_FIELDS, EventSlimSerializer
from events.services import REPEATER_CREATE_COPY_FIELDS
from events.tests.base import EventTestCase
from user.models import BaseUserProfile
from user.tests.test_cacheops_integration import _redis_reachable


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for inner in value.values():
            found |= _keys(inner)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for inner in value:
            found |= _keys(inner)
        return found
    return set()


class EventEndAndStaffTestBase(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org_staff = CustomUser.objects.create_user(
            username="event_org_staff_only", password="testpass"
        )
        cls.org_staff.positions = PositionsModel.objects.create()
        cls.org_staff.save()
        cls.org.staff.add(cls.org_staff)
        cls.other_org = Organization.objects.create(
            name="Other Event Org", owner=cls.unrelated_user
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = f"/api/events/{self.event.pk}/"

    def _patch(self, body: dict[str, Any]) -> Any:
        self.client.force_authenticate(self.org_staff)
        return self.client.patch(self.url, body, format="json")


class ReadOnlyFieldsTest(EventEndAndStaffTestBase):
    def test_state_host_helpers_marker_not_writable(self) -> None:
        resp = self._patch(
            {
                "state": EventState.COMPLETED,
                "host": self.user.pk,
                "helpers": [self.user.pk],
                "contributions_awarded_at": "2026-01-01T00:00:00Z",
            }
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(self.event.host_id)
        self.assertFalse(self.event.helpers.exists())
        self.assertIsNone(self.event.contributions_awarded_at)

    def test_marker_cannot_be_cleared(self) -> None:
        marker = tz.now() - timedelta(days=1)
        Event.objects.filter(pk=self.event.pk).update(contributions_awarded_at=marker)
        resp = self._patch({"contributions_awarded_at": None})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.contributions_awarded_at, marker)


class EndsAtValidationTest(EventEndAndStaffTestBase):
    def test_ends_before_start_rejected(self) -> None:
        resp = self._patch(
            {"ends_at": (self.event.scheduled_at - timedelta(hours=1)).isoformat()}
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("ends_at", resp.json())

    def test_ends_equal_to_start_rejected(self) -> None:
        resp = self._patch({"ends_at": self.event.scheduled_at.isoformat()})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("ends_at", resp.json())

    def test_patch_only_ends_at_uses_instance_start(self) -> None:
        ends_at = self.event.scheduled_at + timedelta(hours=4)
        resp = self._patch({"ends_at": ends_at.isoformat()})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.ends_at, ends_at)

    def test_patch_both_validates_against_new_start(self) -> None:
        start = self.event.scheduled_at + timedelta(days=1)
        resp = self._patch(
            {
                "scheduled_at": start.isoformat(),
                "ends_at": (start - timedelta(hours=1)).isoformat(),
            }
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("ends_at", resp.json())

    def test_patch_only_start_past_stored_end_rejected(self) -> None:
        ends_at = self.event.scheduled_at + timedelta(hours=2)
        Event.objects.filter(pk=self.event.pk).update(ends_at=ends_at)
        resp = self._patch({"scheduled_at": (ends_at + timedelta(days=7)).isoformat()})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("ends_at", resp.json())
        self.event.refresh_from_db()
        self.assertEqual(self.event.ends_at, ends_at)

    def test_patch_only_start_before_stored_end_accepted(self) -> None:
        ends_at = self.event.scheduled_at + timedelta(hours=4)
        Event.objects.filter(pk=self.event.pk).update(ends_at=ends_at)
        start = self.event.scheduled_at + timedelta(hours=1)
        resp = self._patch({"scheduled_at": start.isoformat()})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduled_at, start)

    def test_patch_new_start_with_null_end_accepted(self) -> None:
        ends_at = self.event.scheduled_at + timedelta(hours=2)
        Event.objects.filter(pk=self.event.pk).update(ends_at=ends_at)
        start = ends_at + timedelta(days=7)
        resp = self._patch({"scheduled_at": start.isoformat(), "ends_at": None})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduled_at, start)
        self.assertIsNone(self.event.ends_at)

    def test_unrelated_patch_not_blocked_by_stored_bad_end(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(
            ends_at=self.event.scheduled_at - timedelta(hours=1)
        )
        resp = self._patch({"name": "Renamed"})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_slim_serializer_exposes_ends_at_read_only(self) -> None:
        self.assertIn("ends_at", EventSlimSerializer.Meta.fields)
        self.assertTrue(EventSlimSerializer().fields["ends_at"].read_only)


class EventModelCleanTest(EventTestCase):
    def test_clean_rejects_end_not_after_start(self) -> None:
        for offset in (timedelta(0), -timedelta(hours=1)):
            self.event.ends_at = self.event.scheduled_at + offset
            with self.assertRaises(ValidationError) as ctx:
                self.event.clean()
            self.assertIn("ends_at", ctx.exception.message_dict)

    def test_clean_accepts_end_after_start_or_none(self) -> None:
        self.event.ends_at = self.event.scheduled_at + timedelta(hours=1)
        self.event.clean()
        self.event.ends_at = None
        self.event.clean()


class EventAdminStaffReadOnlyTest(EventTestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="event_admin_site", password="x", email="eas@example.com"
        )
        self.client.force_login(self.superuser)

    def test_host_and_helpers_not_in_admin_form(self) -> None:
        model_admin = admin_site._registry[Event]
        request = RequestFactory().get("/")
        request.user = self.superuser
        form_class = model_admin.get_form(request, self.event)
        self.assertNotIn("host", form_class.base_fields)
        self.assertNotIn("helpers", form_class.base_fields)
        readonly = model_admin.get_readonly_fields(request, self.event)
        self.assertIn("host", readonly)
        self.assertIn("helpers", readonly)

    def test_admin_change_page_renders(self) -> None:
        self.event.host = self.user
        self.event.save()
        self.event.helpers.add(self.unrelated_user)
        resp = self.client.get(f"/admin/events/event/{self.event.pk}/change/")
        self.assertEqual(resp.status_code, 200)


class OrganizationImmutableTest(EventEndAndStaffTestBase):
    def test_move_to_other_org_rejected(self) -> None:
        resp = self._patch({"organization": self.other_org.pk})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("organization", resp.json())
        self.event.refresh_from_db()
        self.assertEqual(self.event.organization_id, self.org.pk)

    def test_same_org_accepted(self) -> None:
        resp = self._patch({"organization": self.org.pk})
        self.assertEqual(resp.status_code, 200, resp.content)


class SeriesCopyFieldsTest(EventTestCase):
    def test_ends_at_not_copied_from_series(self) -> None:
        self.assertNotIn("ends_at", REPEATER_CREATE_COPY_FIELDS)
        self.assertNotIn("ends_at", ONE_OFF_OVERRIDE_FIELDS)


class OneOffEndsAtTest(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        self.url = f"/api/events/repeaters/{self.repeater.pk}/create-event/"
        self.when = (tz.now() + timedelta(days=2, hours=5)).replace(microsecond=0)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_one_off_create_stores_ends_at(self, *_mocks: Any) -> None:
        ends_at = self.when + timedelta(hours=3)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {"scheduled_at": self.when.isoformat(), "ends_at": ends_at.isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        event = Event.objects.get(pk=resp.data["id"])
        self.assertEqual(event.ends_at, ends_at)

    def test_one_off_ends_before_start_rejected(self) -> None:
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {
                "scheduled_at": self.when.isoformat(),
                "ends_at": (self.when - timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("ends_at", resp.json())


class EventStaffCacheTest(TransactionTestCase):
    """Real commits so cacheops caches and evicts between requests."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        owner = CustomUser.objects.create_user(username="staffcache_owner")
        self.helper = CustomUser.objects.create_user(username="staffcache_helper")
        self.helper.nickname = "HelperNick"
        self.helper.save()
        org = Organization.objects.create(name="Staff Cache Org", owner=owner)
        self.event = Event.objects.create(
            organization=org,
            name="Staff Cache Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
        )
        self.url = f"/api/events/{self.event.pk}/"
        self.client = APIClient()

    def test_helper_added_after_cached_get_shows(self) -> None:
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["helpers"], [])

        self.event.helpers.add(self.helper)
        invalidate_obj(self.event)

        second = self.client.get(self.url).json()
        self.assertEqual([h["pk"] for h in second["helpers"]], [self.helper.pk])
        self.assertEqual(
            set(second["helpers"][0]), {"pk", "username", "nickname", "avatarUrl"}
        )

    def test_host_nickname_change_after_cached_get_shows(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(host=self.helper)
        invalidate_obj(self.event)
        first = self.client.get(self.url).json()
        self.assertEqual(first["host"]["nickname"], "HelperNick")

        profile = BaseUserProfile.objects.get(user=self.helper)
        profile.nickname = "RenamedHost"
        profile.save()

        second = self.client.get(self.url).json()
        self.assertEqual(second["host"]["nickname"], "RenamedHost")

    def test_helper_nickname_change_after_cached_get_shows(self) -> None:
        self.event.helpers.add(self.helper)
        invalidate_obj(self.event)
        first = self.client.get(self.url).json()
        self.assertEqual(first["helpers"][0]["nickname"], "HelperNick")

        profile = BaseUserProfile.objects.get(user=self.helper)
        profile.nickname = "RenamedHelper"
        profile.save()

        second = self.client.get(self.url).json()
        self.assertEqual(second["helpers"][0]["nickname"], "RenamedHelper")

    def test_anonymous_payload_has_no_points(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(host=self.helper)
        invalidate_obj(self.event)
        payload = self.client.get(self.url).json()
        self.assertEqual(payload["host"]["pk"], self.helper.pk)
        self.assertFalse(payload["user_can_manage_event_staff"])
        self.assertIsNone(payload["contributions_awarded_at"])
        self.assertIsNone(payload["ends_at"])
        self.assertNotIn("points", _keys(payload))
