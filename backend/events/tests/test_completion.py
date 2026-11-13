"""close_event and the event-staff ledger sync."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone as tz

from app.models import CustomUser, Organization, OrgLog, PositionsModel
from events.completion import CloseResult, close_event
from events.constants import EventState
from events.models import Event
from events.services import resolve_or_create_org_user
from events.tests.base import EventTestCase
from org.contributions.kinds import ContributionKind
from org.contributions.services import (
    SyncResult,
    should_sync_staff,
    sync_event_staff_entries,
)
from org.feature_keys import FeatureKey
from org.features import org_has_feature, set_org_feature
from org.models import ContributionEntry


class CompletionTestBase(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.helper_a = cls._make_user("completion_helper_a")
        cls.helper_b = cls._make_user("completion_helper_b")
        cls.host = cls._make_user("completion_host")

    @classmethod
    def _make_user(cls, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        user.positions = PositionsModel.objects.create()
        user.save()
        return user

    def setUp(self) -> None:
        self.start = tz.now() - timedelta(hours=5)
        self.end = self.start + timedelta(hours=3)
        self.ev = Event.objects.create(
            organization=self.org,
            name="Completion Event",
            scheduled_at=self.start,
            ends_at=self.end,
            state=EventState.IN_PROGRESS,
            created_by=self.admin,
        )

    def _staff(self, host: bool = True, helpers: int = 2) -> None:
        if host:
            self.ev.host = self.host
            self.ev.save(update_fields=["host"])
        self.ev.helpers.add(*[self.helper_a, self.helper_b][:helpers])

    def _entries(self, event: Event | None = None):
        return ContributionEntry.objects.nocache().filter(event=event or self.ev)

    def _set_state(self, state: EventState) -> None:
        Event.objects.filter(pk=self.ev.pk).update(state=state)
        self.ev.refresh_from_db()


class CloseEventTest(CompletionTestBase):
    def test_complete_from_in_progress_awards_host_and_helpers(self) -> None:
        self._staff()
        result = close_event(
            self.ev, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        self.assertEqual(result, CloseResult(closed=True, state=EventState.COMPLETED))
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.COMPLETED)
        self.assertIsNotNone(self.ev.contributions_awarded_at)
        rows = {
            (e.org_user.user_id, e.kind): e
            for e in self._entries().select_related("org_user")
        }
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[(self.host.pk, ContributionKind.EVENT_HOST)].points, 10)
        for helper in (self.helper_a, self.helper_b):
            self.assertEqual(rows[(helper.pk, ContributionKind.EVENT_HELPER)].points, 5)
        for entry in rows.values():
            self.assertEqual(entry.occurred_at, self.end)
            self.assertEqual(entry.event_name, "Completion Event")
            self.assertEqual(entry.organization_id, self.org.pk)

    def test_complete_from_roll_call(self) -> None:
        self._set_state(EventState.ROLL_CALL)
        self._staff()
        result = close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertTrue(result.closed)
        self.assertEqual(self._entries().count(), 3)

    def test_occurred_at_falls_back_to_scheduled_at(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(ends_at=None)
        self.ev.refresh_from_db()
        self._staff(helpers=0)
        close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertEqual(self._entries().get().occurred_at, self.start)

    def test_complete_with_no_staff_sets_marker(self) -> None:
        result = close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertTrue(result.closed)
        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._entries().count(), 0)

    def test_second_close_awards_nothing(self) -> None:
        self._staff()
        stale = Event.objects.nocache().get(pk=self.ev.pk)
        first = close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        second = close_event(stale, new_state=EventState.COMPLETED, source="auto")
        self.assertTrue(first.closed)
        self.assertEqual(second, CloseResult(closed=False, state=EventState.COMPLETED))
        self.assertEqual(self._entries().count(), 3)
        self.assertEqual(OrgLog.objects.filter(action="complete_event").count(), 1)

    def test_complete_from_upcoming_is_refused(self) -> None:
        self._set_state(EventState.UPCOMING)
        self._staff()
        result = close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertEqual(result, CloseResult(closed=False, state=EventState.UPCOMING))
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.UPCOMING)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._entries().count(), 0)

    def test_auto_cancel_with_host_awards(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        self._staff(helpers=0)
        result = close_event(self.ev, new_state=EventState.CANCELLED, source="auto")
        self.assertEqual(result, CloseResult(closed=True, state=EventState.CANCELLED))
        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.contributions_awarded_at)
        entry = self._entries().get()
        self.assertEqual(entry.kind, ContributionKind.EVENT_HOST)

    def test_auto_cancel_with_only_helpers_awards(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        self._staff(host=False, helpers=1)
        close_event(self.ev, new_state=EventState.CANCELLED, source="auto")
        self.assertEqual(self._entries().get().kind, ContributionKind.EVENT_HELPER)

    def test_auto_cancel_without_staff_awards_nothing(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        result = close_event(self.ev, new_state=EventState.CANCELLED, source="auto")
        self.assertTrue(result.closed)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.CANCELLED)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._entries().count(), 0)

    def test_admin_cancel_awards_nothing(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        self._staff()
        result = close_event(self.ev, new_state=EventState.CANCELLED, source="admin")
        self.assertTrue(result.closed)
        self.ev.refresh_from_db()
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._entries().count(), 0)

    def test_admin_close_writes_org_log(self) -> None:
        close_event(
            self.ev, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        log = OrgLog.objects.get(action="complete_event")
        self.assertEqual(log.organization_id, self.org.pk)
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual(log.details["event_id"], self.ev.pk)

    def test_auto_close_writes_no_org_log(self) -> None:
        close_event(self.ev, new_state=EventState.COMPLETED, source="auto")
        self.assertFalse(OrgLog.objects.filter(action="complete_event").exists())

    def test_caller_instance_refreshed(self) -> None:
        close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertEqual(self.ev.state, EventState.COMPLETED)
        self.assertIsNotNone(self.ev.contributions_awarded_at)

    def test_invalidates_stale_and_refreshed_event(self) -> None:
        seen: list[str] = []

        def record(obj: object) -> None:
            if isinstance(obj, Event):
                seen.append(obj.state)

        with (
            patch("app.cache_utils._cacheops_invalidate_obj", side_effect=record),
            self.captureOnCommitCallbacks(execute=True),
        ):
            close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertIn(EventState.IN_PROGRESS, seen)
        self.assertIn(EventState.COMPLETED, seen)

    def test_close_event_with_bad_org_timezone(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(timezone="Mars/Base")
        self.ev = Event.objects.nocache().get(pk=self.ev.pk)
        self._staff()
        result = close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.assertTrue(result.closed)
        self.assertEqual(self._entries().count(), 3)

    def test_locked_contributions_org_still_gets_entries(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=False, actor=self.admin
        )
        self.assertFalse(org_has_feature(self.org, FeatureKey.CONTRIBUTIONS))
        self._staff()
        close_event(self.ev, new_state=EventState.COMPLETED, source="auto")
        self.assertEqual(self._entries().count(), 3)


class SyncEventStaffEntriesTest(CompletionTestBase):
    def _complete(self) -> None:
        close_event(self.ev, new_state=EventState.COMPLETED, source="admin")
        self.ev.refresh_from_db()

    def test_sync_is_idempotent(self) -> None:
        self._staff()
        self._complete()
        self.assertEqual(
            sync_event_staff_entries(self.ev),
            SyncResult(created=0, deleted=0, updated=0),
        )
        self.assertEqual(self._entries().count(), 3)

    def test_removing_helper_deletes_their_entry(self) -> None:
        self._staff()
        self._complete()
        self.ev.helpers.remove(self.helper_b)
        result = sync_event_staff_entries(self.ev)
        self.assertEqual(result, SyncResult(created=0, deleted=1, updated=0))
        users = set(self._entries().values_list("org_user__user_id", flat=True))
        self.assertEqual(users, {self.host.pk, self.helper_a.pk})

    def test_host_listed_as_helper_gets_only_host_entry(self) -> None:
        self._staff(helpers=0)
        self.ev.helpers.add(self.host)
        self._complete()
        entry = self._entries().get()
        self.assertEqual(entry.kind, ContributionKind.EVENT_HOST)

    def test_changing_host_swaps_entry(self) -> None:
        self._staff(helpers=0)
        self._complete()
        self.ev.host = self.helper_a
        self.ev.save(update_fields=["host"])
        result = sync_event_staff_entries(self.ev)
        self.assertEqual(result, SyncResult(created=1, deleted=1, updated=0))
        self.assertEqual(self._entries().get().org_user.user_id, self.helper_a.pk)

    def test_redating_event_moves_occurred_at(self) -> None:
        self._staff()
        self._complete()
        new_end = self.end - timedelta(days=40)
        self.ev.scheduled_at = new_end - timedelta(hours=2)
        self.ev.ends_at = new_end
        self.ev.name = "Renamed Event"
        self.ev.save(update_fields=["scheduled_at", "ends_at", "name"])
        result = sync_event_staff_entries(self.ev)
        self.assertEqual(result, SyncResult(created=0, deleted=0, updated=3))
        for entry in self._entries():
            self.assertEqual(entry.occurred_at, new_end)
            self.assertEqual(entry.event_name, "Renamed Event")

    def test_kept_entry_keeps_points(self) -> None:
        self._staff(helpers=0)
        self._complete()
        self._entries().update(points=42)
        sync_event_staff_entries(self.ev)
        self.assertEqual(self._entries().get().points, 42)

    def test_other_kinds_and_other_org_rows_untouched(self) -> None:
        self._staff(helpers=0)
        self._complete()
        manual = ContributionEntry.objects.create(
            org_user=self._entries().get().org_user,
            organization=self.org,
            kind=ContributionKind.MANUAL,
            points=3,
            event=self.ev,
            occurred_at=self.start,
        )
        other_org = Organization.objects.create(
            name="Completion Other Org", owner=self.unrelated_user
        )
        foreign = ContributionEntry.objects.create(
            org_user=resolve_or_create_org_user(self.host, other_org),
            organization=other_org,
            kind=ContributionKind.EVENT_HELPER,
            points=5,
            event=self.ev,
            occurred_at=self.start,
        )
        self.ev.host = None
        self.ev.save(update_fields=["host"])
        result = sync_event_staff_entries(self.ev)
        self.assertEqual(result.deleted, 1)
        kept = ContributionEntry.objects.nocache().filter(
            pk__in=[manual.pk, foreign.pk]
        )
        self.assertEqual(kept.count(), 2)


class ShouldSyncStaffTest(CompletionTestBase):
    def test_completed_syncs(self) -> None:
        self._set_state(EventState.COMPLETED)
        self.assertTrue(should_sync_staff(self.ev))

    def test_marker_syncs(self) -> None:
        self._set_state(EventState.CANCELLED)
        self.ev.contributions_awarded_at = tz.now()
        self.assertTrue(should_sync_staff(self.ev))

    def test_manual_cancel_does_not_sync(self) -> None:
        self._set_state(EventState.CANCELLED)
        self.assertFalse(should_sync_staff(self.ev))

    def test_open_event_does_not_sync(self) -> None:
        self.assertFalse(should_sync_staff(self.ev))
