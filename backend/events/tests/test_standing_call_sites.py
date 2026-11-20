from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, Organization, OrgLog
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from events.services import teardown_event
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.standing import registry
from org.standing.registry import override_tracks
from org.tests.standing_fakes import FakeTrack, atomic_baseline


class StandingCallSiteTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="cs_admin", password="x", is_staff=True, is_superuser=True
        )
        self.org = Organization.objects.create(name="CS Org", owner=self.admin)
        self.event = Event.objects.create(
            organization=self.org,
            name="CS Event",
            scheduled_at=timezone.now() - timedelta(hours=2),
            created_by=self.admin,
            state=EventState.IN_PROGRESS,
        )
        self.fake = FakeTrack()
        self.tracks = override_tracks(*registry.TRACKS, self.fake)
        self.tracks.__enter__()
        self.addCleanup(self.tracks.__exit__, None, None, None)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _assert_nested(self, baseline: int) -> None:
        self.assertTrue(self.fake.calls)
        for call in self.fake.calls:
            self.assertGreater(call.atomic_depth, baseline, call.hook)

    def _set_state(self, state: EventState) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=state)
        self.event.refresh_from_db()

    def test_close_admin_completed_calls_hook(self) -> None:
        baseline = atomic_baseline()
        close_event(
            self.event, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        self._assert_nested(baseline)
        kwargs = self.fake.calls[0].kwargs
        self.assertEqual(self.fake.hooks, ["on_event_closed"])
        self.assertFalse(kwargs["cancelled"])
        self.assertEqual(kwargs["source"], "admin")
        self.assertEqual(kwargs["actor"], self.admin)
        self.assertEqual(kwargs["now"], self.event.updated_at)
        details = OrgLog.objects.get(action="complete_event").details
        self.assertEqual(details["fake_count"], 1)

    def test_close_auto_cancelled_calls_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        baseline = atomic_baseline()
        close_event(self.event, new_state=EventState.CANCELLED, source="auto")
        self._assert_nested(baseline)
        kwargs = self.fake.calls[0].kwargs
        self.assertTrue(kwargs["cancelled"])
        self.assertEqual(kwargs["source"], "auto")

    def test_close_skipped_does_not_call_hook(self) -> None:
        self._set_state(EventState.COMPLETED)
        close_event(
            self.event,
            new_state=EventState.COMPLETED,
            source="auto",
            expected_from=[EventState.IN_PROGRESS],
        )
        self.assertEqual(self.fake.hooks, [])

    def test_close_rolls_back_when_track_raises(self) -> None:
        self.fake.raise_on = {"on_event_closed"}
        with self.assertRaises(RuntimeError):
            close_event(self.event, new_state=EventState.COMPLETED, source="admin")
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).state, EventState.IN_PROGRESS
        )
        self.assertFalse(OrgLog.objects.filter(action="complete_event").exists())

    def test_reopen_calls_hook_after_cas(self) -> None:
        self._set_state(EventState.COMPLETED)
        baseline = atomic_baseline()
        result = reopen_event(self.event, actor=self.admin)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_event_reopened"])
        self.assertEqual(self.fake.calls[0].kwargs["state"], EventState.SIGNUPS_OPEN)
        self.assertEqual(result.details, {"revoked": 0, "fake_count": 1})
        details = OrgLog.objects.get(action="reopen_event").details
        self.assertEqual(details["fake_count"], 1)
        self.assertEqual(details["revoked"], 0)

    def test_reopen_rolls_back_when_track_raises(self) -> None:
        self._set_state(EventState.COMPLETED)
        self.fake.raise_on = {"on_event_reopened"}
        with self.assertRaises(RuntimeError):
            reopen_event(self.event, actor=None)
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).state, EventState.COMPLETED
        )

    def test_teardown_calls_delete_hook_first(self) -> None:
        baseline = atomic_baseline()
        teardown_event(self.event)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_event_deleted"])
        self.assertTrue(self.fake.calls[0].kwargs["exists"])

    def test_teardown_rolls_back_when_track_raises(self) -> None:
        self.fake.raise_on = {"on_event_deleted"}
        with self.assertRaises(RuntimeError):
            teardown_event(self.event)
        self.assertTrue(Event.objects.nocache().filter(pk=self.event.pk).exists())

    def test_patch_timing_calls_changed_hook(self) -> None:
        baseline = atomic_baseline()
        response = self.client.patch(
            f"/api/events/{self.event.pk}/",
            {"scheduled_at": (timezone.now() - timedelta(hours=3)).isoformat()},
            format="json",
        )
        self.assertLess(response.status_code, 300, response.content)
        self._assert_nested(baseline)
        self.assertEqual(
            self.fake.calls[0].kwargs["fields"], frozenset({"scheduled_at"})
        )

    def test_patch_other_field_skips_hook(self) -> None:
        response = self.client.patch(
            f"/api/events/{self.event.pk}/", {"description": "x"}, format="json"
        )
        self.assertLess(response.status_code, 300, response.content)
        self.assertEqual(self.fake.hooks, [])

    def test_staff_put_calls_changed_hook(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.admin
        )
        baseline = atomic_baseline()
        with capture_logs() as logs:
            response = self.client.put(
                f"/api/events/{self.event.pk}/staff/",
                {"host_id": self.admin.pk, "helper_ids": []},
                format="json",
            )
        self.assertLess(response.status_code, 300, response.content)
        self._assert_nested(baseline)
        self.assertEqual(
            self.fake.calls[0].kwargs["fields"], frozenset({"host", "helpers"})
        )
        staff_log = next(e for e in logs if e["event"] == "event_staff_set")
        self.assertIs(staff_log["fake_ran"], True)
        self.assertIs(staff_log["synced"], False)

    def _merge_fixture(self) -> tuple[CustomUser, CustomUser, OrgUser, OrgUser]:
        keep = CustomUser.objects.create_user(username="cs_keep", password="x")
        drop = CustomUser.objects.create_user(username="cs_drop", password="x")
        keep_ou = OrgUser.objects.create(user=keep, organization=self.org)
        drop_ou = OrgUser.objects.create(user=drop, organization=self.org)
        return keep, drop, keep_ou, drop_ou

    def test_discord_merge_calls_merge_users_before_deleting_drop_org_users(
        self,
    ) -> None:
        keep, drop, keep_ou, drop_ou = self._merge_fixture()
        baseline = atomic_baseline()
        merge_discord_accounts(keep=keep, drop=drop)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks[:2], ["merge_members", "repoint_user"])
        self.assertEqual(
            self.fake.calls[0].kwargs,
            {"drop": drop_ou.pk, "keep": keep_ou.pk, "drop_exists": True},
        )

    def test_discord_merge_dedupe_calls_changed_hook(self) -> None:
        keep, drop, _, _ = self._merge_fixture()
        self.event.host = keep
        self.event.save()
        self.event.helpers.add(drop)
        baseline = atomic_baseline()
        merge_discord_accounts(keep=keep, drop=drop)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks[-1], "on_event_changed")
        self.assertEqual(self.fake.calls[-1].kwargs["fields"], frozenset({"helpers"}))
        self.assertFalse(self.event.helpers.filter(pk=keep.pk).exists())

    def test_merge_rolls_back_when_track_raises(self) -> None:
        keep, drop, _, _ = self._merge_fixture()
        self.fake.raise_on = {"merge_members"}
        with self.assertRaises(RuntimeError):
            merge_discord_accounts(keep=keep, drop=drop)
        self.assertEqual(self.fake.hooks, ["merge_members"])
        self.assertTrue(CustomUser.objects.filter(pk=drop.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=keep.pk).exists())

    def test_api_user_delete_calls_on_user_deleted(self) -> None:
        victim = CustomUser.objects.create_user(username="cs_victim", password="x")
        baseline = atomic_baseline()
        response = self.client.delete(f"/api/users/{victim.pk}/")
        self.assertLess(response.status_code, 300, response.content)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_user_deleted"])
        self.assertEqual(self.fake.calls[0].kwargs["user"], victim.pk)
