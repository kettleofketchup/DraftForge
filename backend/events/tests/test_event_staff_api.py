"""Complete action, host/helper assignment endpoint and the staff-manage flag."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.db.models import QuerySet
from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, OrgLog, PositionsModel
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from events.tests.base import EventTestCase
from events.views import EventViewSet
from org.contributions.kinds import ContributionKind
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import ContributionEntry, OrgUser


class EventStaffApiTestBase(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org_admin = cls._make_user("staff_api_org_admin")
        cls.org.admins.add(cls.org_admin)
        cls.org_staff = cls._make_user("staff_api_org_staff")
        cls.org.staff.add(cls.org_staff)
        cls.host = cls._make_user("staff_api_host")
        cls.helper_a = cls._make_user("staff_api_helper_a")
        cls.helper_b = cls._make_user("staff_api_helper_b")

    @classmethod
    def _make_user(cls, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        user.positions = PositionsModel.objects.create()
        user.save()
        return user

    def setUp(self) -> None:
        self.client = APIClient()
        self.start = tz.now() - timedelta(hours=4)
        self.end = self.start + timedelta(hours=2)
        Event.objects.filter(pk=self.event.pk).update(
            scheduled_at=self.start,
            ends_at=self.end,
            state=EventState.IN_PROGRESS,
        )
        self.event.refresh_from_db()
        self.detail_url = f"/api/events/{self.event.pk}/"
        self.complete_url = f"/api/events/{self.event.pk}/complete/"
        self.staff_url = f"/api/events/{self.event.pk}/staff/"

    def _as(self, user: CustomUser | None) -> None:
        self.client.force_authenticate(user)

    def _complete(self, user: CustomUser | None) -> Response:
        self._as(user)
        return self.client.post(self.complete_url, format="json")

    def _put_staff(
        self,
        user: CustomUser | None,
        host_id: int | None,
        helper_ids: list[int],
    ) -> Response:
        self._as(user)
        return self.client.put(
            self.staff_url,
            {"host_id": host_id, "helper_ids": helper_ids},
            format="json",
        )

    def _entries(self) -> QuerySet[ContributionEntry]:
        return ContributionEntry.objects.nocache().filter(event=self.event)

    def _staff_keys(self) -> set[tuple[int, str]]:
        return set(self._entries().values_list("org_user__user_id", "kind"))

    def _set_state(self, state: EventState) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=state)
        self.event.refresh_from_db()

    def _assert_not_permitted(self, resp: Any) -> None:
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(resp.json()["code"], "not_permitted")


class CompleteEventTest(EventStaffApiTestBase):
    def test_admin_completes_from_in_progress(self) -> None:
        self.event.host = self.host
        self.event.save(update_fields=["host"])
        self.event.helpers.add(self.helper_a)
        resp = self._complete(self.org_admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["state"], EventState.COMPLETED)
        self.assertIsNotNone(body["contributions_awarded_at"])
        self.assertTrue(body["user_can_manage_event_staff"])
        self.assertTrue(body["user_can_manage"])
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.COMPLETED)
        self.assertEqual(
            self._staff_keys(),
            {
                (self.host.pk, ContributionKind.EVENT_HOST),
                (self.helper_a.pk, ContributionKind.EVENT_HELPER),
            },
        )
        log = OrgLog.objects.get(organization=self.org, action="complete_event")
        self.assertEqual(log.actor, self.org_admin)

    def test_admin_completes_from_roll_call(self) -> None:
        self._set_state(EventState.ROLL_CALL)
        resp = self._complete(self.org_admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["state"], EventState.COMPLETED)

    def test_org_owner_can_complete(self) -> None:
        resp = self._complete(self.admin)
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_org_staff_forbidden(self) -> None:
        self._assert_not_permitted(self._complete(self.org_staff))
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.IN_PROGRESS)

    def test_league_staff_forbidden(self) -> None:
        self._assert_not_permitted(self._complete(self.league_staff))
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.IN_PROGRESS)

    def test_anonymous_gets_plain_403(self) -> None:
        resp = self._complete(None)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNotIn("code", resp.json())
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.IN_PROGRESS)

    def test_from_upcoming_is_400(self) -> None:
        self._set_state(EventState.UPCOMING)
        resp = self._complete(self.org_admin)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("error", resp.json())
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, EventState.UPCOMING)

    def test_from_signups_open_is_400(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        resp = self._complete(self.org_admin)
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_second_complete_is_400_and_awards_nothing(self) -> None:
        self.event.host = self.host
        self.event.save(update_fields=["host"])
        self.assertEqual(self._complete(self.org_admin).status_code, 200)
        resp = self._complete(self.org_admin)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(self._entries().count(), 1)

    def test_missing_event_is_404(self) -> None:
        self._as(self.org_admin)
        resp = self.client.post("/api/events/999999/complete/", format="json")
        self.assertEqual(resp.status_code, 404)


class EventStaffEndpointTest(EventStaffApiTestBase):
    def test_admin_assigns_host_and_helpers(self) -> None:
        resp = self._put_staff(
            self.org_admin, self.host.pk, [self.helper_a.pk, self.helper_b.pk]
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["host"]["pk"], self.host.pk)
        self.assertEqual(
            {h["pk"] for h in body["helpers"]}, {self.helper_a.pk, self.helper_b.pk}
        )
        self.assertTrue(body["user_can_manage_event_staff"])

        self._as(self.org_admin)
        detail = self.client.get(self.detail_url).json()
        self.assertEqual(detail["host"]["pk"], self.host.pk)
        self.assertEqual(
            {h["pk"] for h in detail["helpers"]}, {self.helper_a.pk, self.helper_b.pk}
        )
        self.assertEqual(self._entries().count(), 0)

    def test_assign_after_cached_get_shows_new_staff(self) -> None:
        self._as(None)
        self.assertEqual(self.client.get(self.detail_url).json()["helpers"], [])
        self._put_staff(self.org_admin, None, [self.helper_a.pk])
        self._as(None)
        helpers = self.client.get(self.detail_url).json()["helpers"]
        self.assertEqual([h["pk"] for h in helpers], [self.helper_a.pk])

    def test_creates_missing_org_users(self) -> None:
        self.assertFalse(
            OrgUser.objects.filter(user=self.helper_a, organization=self.org).exists()
        )
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        for user in (self.host, self.helper_a):
            self.assertTrue(
                OrgUser.objects.filter(user=user, organization=self.org).exists()
            )

    def test_writes_org_log(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        log = OrgLog.objects.get(organization=self.org, action="set_event_staff")
        self.assertEqual(log.actor, self.org_admin)
        self.assertEqual(log.details["event_id"], self.event.pk)
        self.assertEqual(log.details["host_id"], self.host.pk)
        self.assertEqual(log.details["helper_ids"], [self.helper_a.pk])

    def test_clear_staff(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        resp = self._put_staff(self.org_admin, None, [])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.host_id)
        self.assertFalse(self.event.helpers.exists())

    def test_host_also_helper_is_400(self) -> None:
        resp = self._put_staff(self.org_admin, self.host.pk, [self.host.pk])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.host_id)

    def test_unknown_user_is_400(self) -> None:
        resp = self._put_staff(self.org_admin, 999999, [])
        self.assertEqual(resp.status_code, 400, resp.content)
        resp = self._put_staff(self.org_admin, None, [self.helper_a.pk, 999998])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(self.event.helpers.exists())

    def test_malformed_body_is_400(self) -> None:
        self._as(self.org_admin)
        resp = self.client.put(
            self.staff_url, {"host_id": "x", "helper_ids": "nope"}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_org_staff_forbidden(self) -> None:
        resp = self._put_staff(self.org_staff, self.host.pk, [])
        self._assert_not_permitted(resp)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.host_id)

    def test_league_staff_forbidden(self) -> None:
        self._assert_not_permitted(self._put_staff(self.league_staff, self.host.pk, []))

    def test_anonymous_gets_plain_403(self) -> None:
        resp = self._put_staff(None, self.host.pk, [])
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNotIn("code", resp.json())

    def test_assign_after_staffless_complete_creates_entry(self) -> None:
        self.assertEqual(self._complete(self.org_admin).status_code, 200)
        self.assertEqual(self._entries().count(), 0)
        resp = self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            self._staff_keys(),
            {
                (self.host.pk, ContributionKind.EVENT_HOST),
                (self.helper_a.pk, ContributionKind.EVENT_HELPER),
            },
        )
        entry = self._entries().get(kind=ContributionKind.EVENT_HOST)
        self.assertEqual(entry.occurred_at, self.end)
        self.assertEqual(entry.points, 10)

    def test_removing_helper_after_complete_deletes_entry(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        self._complete(self.org_admin)
        self.assertEqual(self._entries().count(), 2)
        self._put_staff(self.org_admin, self.host.pk, [])
        self.assertEqual(
            self._staff_keys(), {(self.host.pk, ContributionKind.EVENT_HOST)}
        )

    def test_close_between_load_and_write_syncs_new_staff(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        original = EventViewSet.get_object

        def load_then_close(view: EventViewSet) -> Event:
            stale = original(view)
            close_event(
                Event.objects.nocache().get(pk=stale.pk),
                new_state=EventState.COMPLETED,
                source="auto",
            )
            return stale

        with patch.object(EventViewSet, "get_object", load_then_close):
            resp = self._put_staff(self.org_admin, self.helper_b.pk, [])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            self._staff_keys(), {(self.helper_b.pk, ContributionKind.EVENT_HOST)}
        )

    def test_edits_after_manual_cancel_create_none(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        self._as(self.org_staff)
        resp = self.client.post(f"/api/events/{self.event.pk}/cancel/")
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._entries().count(), 0)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.contributions_awarded_at)

    def test_locked_contributions_org_still_works(self) -> None:
        self.assertFalse(org_has_feature(self.org, FeatureKey.CONTRIBUTIONS))
        self._complete(self.org_admin)
        resp = self._put_staff(self.org_admin, self.host.pk, [])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            self._staff_keys(), {(self.host.pk, ContributionKind.EVENT_HOST)}
        )


class ManageEventStaffFlagTest(EventStaffApiTestBase):
    def _flag(self, user: CustomUser | None) -> bool:
        self._as(user)
        return self.client.get(self.detail_url).json()["user_can_manage_event_staff"]

    def test_true_for_org_admin_and_owner(self) -> None:
        self.assertTrue(self._flag(self.org_admin))
        self.assertTrue(self._flag(self.admin))

    def test_false_for_staff_league_staff_and_anonymous(self) -> None:
        self.assertFalse(self._flag(self.org_staff))
        self.assertFalse(self._flag(self.league_staff))
        self.assertFalse(self._flag(None))

    def test_cached_payload_not_shared_between_viewers(self) -> None:
        self.assertTrue(self._flag(self.org_admin))
        self.assertFalse(self._flag(self.org_staff))
        self.assertTrue(self._flag(self.org_admin))

    def test_list_payload_carries_flag(self) -> None:
        self._as(self.org_admin)
        rows = self.client.get("/api/events/", {"organization": self.org.pk}).json()
        row = next(r for r in rows if r["id"] == self.event.pk)
        self.assertTrue(row["user_can_manage_event_staff"])
        self._as(self.org_staff)
        rows = self.client.get("/api/events/", {"organization": self.org.pk}).json()
        row = next(r for r in rows if r["id"] == self.event.pk)
        self.assertFalse(row["user_can_manage_event_staff"])


class EventEditResyncTest(EventStaffApiTestBase):
    def _patch(self, body: dict[str, Any]) -> Response:
        self._as(self.org_staff)
        return self.client.patch(self.detail_url, body, format="json")

    def test_renaming_completed_event_updates_entry_names(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        self._complete(self.org_admin)
        resp = self._patch({"name": "Renamed Event"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            set(self._entries().values_list("event_name", flat=True)),
            {"Renamed Event"},
        )

    def test_redating_completed_event_moves_occurred_at(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [])
        self._complete(self.org_admin)
        new_end = self.end + timedelta(hours=1)
        resp = self._patch({"ends_at": new_end.isoformat()})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._entries().get().occurred_at, new_end)

    def _patch_racing(
        self, body: dict[str, Any], race: Callable[[Event], None]
    ) -> Response:
        original = EventViewSet.get_object

        def load_then_race(view: EventViewSet) -> Event:
            stale = original(view)
            if view.request.method == "PATCH":
                race(stale)
            return stale

        with patch.object(EventViewSet, "get_object", load_then_race):
            return self._patch(body)

    def test_staff_put_during_patch_survives(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [self.helper_a.pk])
        self._complete(self.org_admin)
        admin_client = APIClient()
        admin_client.force_authenticate(self.org_admin)

        def reassign(stale: Event) -> None:
            resp = admin_client.put(
                self.staff_url,
                {"host_id": self.helper_b.pk, "helper_ids": []},
                format="json",
            )
            self.assertEqual(resp.status_code, 200, resp.content)

        resp = self._patch_racing({"name": "Renamed Event"}, reassign)
        self.assertEqual(resp.status_code, 200, resp.content)
        event = Event.objects.nocache().get(pk=self.event.pk)
        self.assertEqual(event.host_id, self.helper_b.pk)
        self.assertEqual(event.state, EventState.COMPLETED)
        self.assertIsNotNone(event.contributions_awarded_at)
        self.assertEqual(event.name, "Renamed Event")
        self.assertEqual(
            self._staff_keys(), {(self.helper_b.pk, ContributionKind.EVENT_HOST)}
        )
        self.assertEqual(
            set(self._entries().values_list("event_name", flat=True)),
            {"Renamed Event"},
        )
        self.assertEqual(resp.json()["host"]["pk"], self.helper_b.pk)
        self.assertEqual(resp.json()["helpers"], [])

    def test_close_during_patch_survives_and_resyncs(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [])

        def close(stale: Event) -> None:
            result = close_event(
                Event.objects.nocache().get(pk=stale.pk),
                new_state=EventState.COMPLETED,
                source="auto",
            )
            self.assertTrue(result.closed)

        resp = self._patch_racing({"name": "Renamed Event"}, close)
        self.assertEqual(resp.status_code, 200, resp.content)
        event = Event.objects.nocache().get(pk=self.event.pk)
        self.assertEqual(event.state, EventState.COMPLETED)
        self.assertIsNotNone(event.contributions_awarded_at)
        self.assertEqual(event.host_id, self.host.pk)
        self.assertEqual(
            self._staff_keys(), {(self.host.pk, ContributionKind.EVENT_HOST)}
        )
        self.assertEqual(
            set(self._entries().values_list("event_name", flat=True)),
            {"Renamed Event"},
        )
        self.assertEqual(resp.json()["state"], EventState.COMPLETED)
        self.assertIsNotNone(resp.json()["contributions_awarded_at"])

    def test_renaming_open_event_creates_no_entries(self) -> None:
        self._put_staff(self.org_admin, self.host.pk, [])
        resp = self._patch({"name": "Renamed Event"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._entries().count(), 0)
