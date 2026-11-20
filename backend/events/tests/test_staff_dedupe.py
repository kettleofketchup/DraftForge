from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Organization
from events.models import Event
from events.staff import dedupe_host_helpers
from org.models import ContributionEntry, OrgUser


class DedupeHostHelpersTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create_user(username="dd_user", password="x")
        self.org = Organization.objects.create(name="DD Org", owner=self.user)
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)
        when = timezone.now() - timedelta(hours=1)
        self.event_a = Event.objects.create(
            organization=self.org, name="A", scheduled_at=when, host=self.user
        )
        self.event_b = Event.objects.create(
            organization=self.org, name="B", scheduled_at=when
        )
        self.event_a.helpers.add(self.user)
        self.event_b.helpers.add(self.user)

    def test_removes_user_from_helpers_where_host(self) -> None:
        with self.assertLogs("events.staff", level="INFO") as logs:
            self.assertEqual(dedupe_host_helpers(self.user), [self.event_a])
        self.assertIn("event_staff_deduped", logs.output[0])
        self.assertFalse(self.event_a.helpers.filter(pk=self.user.pk).exists())
        self.assertTrue(self.event_b.helpers.filter(pk=self.user.pk).exists())

    def test_no_overlap_returns_empty_and_logs_nothing(self) -> None:
        self.event_a.helpers.remove(self.user)
        with self.assertNoLogs("events.staff", level="INFO"):
            self.assertEqual(dedupe_host_helpers(self.user), [])

    def test_does_not_touch_ledger(self) -> None:
        entry = ContributionEntry.objects.create(
            organization=self.org,
            org_user=self.org_user,
            kind="event_helper",
            points=1,
            event=self.event_a,
            occurred_at=timezone.now(),
        )
        dedupe_host_helpers(self.user)
        self.assertTrue(
            ContributionEntry.objects.nocache().filter(pk=entry.pk).exists()
        )
