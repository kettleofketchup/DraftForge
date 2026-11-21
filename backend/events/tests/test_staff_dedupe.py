from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser
from events.models import Event
from events.staff import dedupe_host_helpers
from org.models import ContributionEntry, Organization, OrgUser
from org.standing import registry
from org.standing.registry import override_tracks
from org.tests.standing_fakes import FakeTrack


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

    def _deduped_log(self, logs: list[dict[str, object]]) -> dict[str, object]:
        return next(e for e in logs if e["event"] == "event_staff_deduped")

    def test_removes_user_from_helpers_where_host(self) -> None:
        with capture_logs() as logs:
            self.assertEqual(dedupe_host_helpers(self.user), [self.event_a])
        self.assertEqual(
            self._deduped_log(logs),
            {
                "event": "event_staff_deduped",
                "system": "events",
                "subsystem": "services",
                "user_id": self.user.pk,
                "event_ids": [self.event_a.pk],
                "synced": 0,
                "log_level": "info",
            },
        )
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

    def test_counts_synced_events(self) -> None:
        Event.objects.filter(pk=self.event_a.pk).update(
            contributions_awarded_at=timezone.now()
        )
        with capture_logs() as logs:
            dedupe_host_helpers(self.user)
        self.assertEqual(self._deduped_log(logs)["synced"], 1)

    def test_calls_changed_hook_per_deduped_event(self) -> None:
        fake = FakeTrack()
        with override_tracks(*registry.TRACKS, fake), capture_logs() as logs:
            dedupe_host_helpers(self.user)
        self.assertEqual(fake.hooks, ["on_event_changed"])
        self.assertEqual(fake.calls[0].kwargs["fields"], frozenset({"helpers"}))
        self.assertEqual(self._deduped_log(logs)["fake_ran"], 1)
