from datetime import timedelta

from django.contrib.admin.sites import site as admin_site
from django.http import HttpRequest
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.admin import CustomUserAdmin
from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, Organization, OrgLog, ProfileClaimRequest
from events.admin import EventAdmin
from events.completion import close_event
from events.constants import EventState, SignupStatus
from events.ledger import SignupActor
from events.models import Event, EventSignup
from events.reopen import reopen_event
from events.services import (
    cancel_event,
    cancel_signup,
    create_tentative_signup,
    decline_signup,
    teardown_event,
)
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
        self.assertEqual(
            result.details, {"revoked": 0, "attendance_reopened": 0, "fake_count": 1}
        )
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

    def test_patch_other_field_passes_changed_fields(self) -> None:
        response = self.client.patch(
            f"/api/events/{self.event.pk}/", {"description": "x"}, format="json"
        )
        self.assertLess(response.status_code, 300, response.content)
        self.assertEqual(self.fake.hooks, ["on_event_changed"])
        self.assertEqual(
            self.fake.calls[0].kwargs["fields"], frozenset({"description"})
        )

    def test_patch_unchanged_value_skips_hook(self) -> None:
        response = self.client.patch(
            f"/api/events/{self.event.pk}/", {"name": self.event.name}, format="json"
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

    def test_claim_merge_calls_merge_users_and_dedupe_hook(self) -> None:
        claimer, target, claimer_ou, target_ou = self._merge_fixture()
        self.event.host = claimer
        self.event.save()
        self.event.helpers.add(target)
        claim = ProfileClaimRequest.objects.create(
            claimer=claimer,
            target_user=target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        baseline = atomic_baseline()
        response = self.client.post(f"/api/claim-requests/{claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)
        self._assert_nested(baseline)
        self.assertEqual(
            self.fake.hooks, ["merge_members", "repoint_user", "on_event_changed"]
        )
        self.assertEqual(
            self.fake.calls[0].kwargs,
            {"drop": target_ou.pk, "keep": claimer_ou.pk, "drop_exists": True},
        )
        self.assertEqual(self.fake.calls[-1].kwargs["fields"], frozenset({"helpers"}))
        self.assertFalse(OrgUser.objects.filter(pk=target_ou.pk).exists())
        self.assertFalse(self.event.helpers.filter(pk=claimer.pk).exists())

    def _admin_request(self) -> HttpRequest:
        request = RequestFactory().post("/admin/app/customuser/")
        request.user = self.admin
        return request

    def test_admin_user_delete_calls_on_user_deleted(self) -> None:
        victim = CustomUser.objects.create_user(username="cs_victim", password="x")
        victim_pk = victim.pk
        baseline = atomic_baseline()
        CustomUserAdmin(CustomUser, admin_site).delete_model(
            self._admin_request(), victim
        )
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_user_deleted"])
        self.assertEqual(self.fake.calls[0].kwargs["user"], victim_pk)
        self.assertEqual(self.fake.calls[0].kwargs["actor"], self.admin)
        self.assertFalse(CustomUser.objects.filter(pk=victim_pk).exists())

    def test_admin_bulk_delete_calls_on_user_deleted_per_user(self) -> None:
        victims = [
            CustomUser.objects.create_user(username=f"cs_victim{i}", password="x")
            for i in range(2)
        ]
        pks = [v.pk for v in victims]
        baseline = atomic_baseline()
        CustomUserAdmin(CustomUser, admin_site).delete_queryset(
            self._admin_request(), CustomUser.objects.filter(pk__in=pks)
        )
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_user_deleted", "on_user_deleted"])
        self.assertCountEqual([c.kwargs["user"] for c in self.fake.calls], pks)
        self.assertFalse(CustomUser.objects.filter(pk__in=pks).exists())

    def test_admin_event_delete_calls_delete_hook(self) -> None:
        event_pk = self.event.pk
        baseline = atomic_baseline()
        EventAdmin(Event, admin_site).delete_model(self._admin_request(), self.event)
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_event_deleted"])
        self.assertTrue(self.fake.calls[0].kwargs["exists"])
        self.assertEqual(self.fake.calls[0].kwargs["actor"], self.admin)
        self.assertFalse(Event.objects.filter(pk=event_pk).exists())

    def test_admin_event_bulk_delete_calls_hook_per_event(self) -> None:
        other = Event.objects.create(
            organization=self.org,
            name="CS Other",
            scheduled_at=timezone.now(),
            created_by=self.admin,
        )
        baseline = atomic_baseline()
        EventAdmin(Event, admin_site).delete_queryset(
            self._admin_request(),
            Event.objects.filter(pk__in=[self.event.pk, other.pk]),
        )
        self._assert_nested(baseline)
        self.assertEqual(self.fake.hooks, ["on_event_deleted", "on_event_deleted"])
        self.assertEqual(len({c.atomic_depth for c in self.fake.calls}), 1)
        self.assertCountEqual(
            [c.kwargs["event"].pk for c in self.fake.calls], [self.event.pk, other.pk]
        )
        self.assertFalse(
            Event.objects.filter(pk__in=[self.event.pk, other.pk]).exists()
        )

    def test_admin_event_delete_rolls_back_when_track_raises(self) -> None:
        self.fake.raise_on = {"on_event_deleted"}
        with self.assertRaises(RuntimeError):
            EventAdmin(Event, admin_site).delete_model(
                self._admin_request(), self.event
            )
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_cancel_event_calls_close_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        baseline = atomic_baseline()
        cancel_event(self.event, actor=self.admin)
        self._assert_nested(baseline)
        kwargs = self.fake.calls[0].kwargs
        self.assertEqual(self.fake.hooks, ["on_event_closed"])
        self.assertTrue(kwargs["cancelled"])
        self.assertEqual(kwargs["source"], "cancel")
        self.assertEqual(kwargs["actor"], self.admin)
        self.assertEqual(kwargs["state"], EventState.CANCELLED)

    def test_cancel_signup_calls_withdrawn_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member", password="x")
        signup = EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        cancel_signup(signup, actor=SignupActor.discord(member))
        self.assertEqual(self.fake.hooks, ["on_signup_withdrawn"])
        kwargs = self.fake.calls[0].kwargs
        self.assertEqual(kwargs["prior_status"], SignupStatus.APPROVED)
        self.assertTrue(kwargs["by_member"])

    def test_member_web_cancel_calls_withdrawn_hook_once(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member3", password="x")
        signup = EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        client = APIClient()
        client.force_authenticate(member)
        response = client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.fake.hooks, ["on_signup_withdrawn"])
        self.assertTrue(self.fake.calls[0].kwargs["by_member"])

    def test_staff_cancel_signup_skips_withdrawn_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member2", password="x")
        signup = EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        response = self.client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.fake.hooks, [])

    def test_actorless_cancel_skips_withdrawn_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member4", password="x")
        signup = EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        cancel_signup(signup)
        self.assertEqual(self.fake.hooks, [])

    def test_tentative_switch_from_approved_calls_withdrawn_hook_once(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member5", password="x")
        EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        create_tentative_signup(self.event, member, actor=SignupActor.discord(member))
        self.assertEqual(self.fake.hooks, ["on_signup_withdrawn"])
        kwargs = self.fake.calls[0].kwargs
        self.assertEqual(kwargs["prior_status"], SignupStatus.APPROVED)
        self.assertTrue(kwargs["by_member"])

    def test_tentative_switch_from_waitlist_skips_withdrawn_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member6", password="x")
        EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.WAITLISTED
        )
        create_tentative_signup(self.event, member, actor=SignupActor.discord(member))
        self.assertEqual(self.fake.hooks, [])

    def test_member_decline_forwards_actor_to_withdrawn_hook(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        member = CustomUser.objects.create_user(username="cs_member7", password="x")
        EventSignup.objects.create(
            event=self.event, user=member, status=SignupStatus.APPROVED
        )
        decline_signup(self.event, member, actor=SignupActor.discord(member))
        self.assertEqual(self.fake.hooks, ["on_signup_withdrawn"])
        self.assertTrue(self.fake.calls[0].kwargs["by_member"])

    def test_feature_toggle_calls_hook_for_matching_track(self) -> None:
        response = self.client.put(
            reverse("org-features", args=[self.org.pk]),
            {"feature": "promotion", "enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.fake.hooks, ["on_feature_toggled"])
        self.assertTrue(self.fake.calls[0].kwargs["enabled"])
