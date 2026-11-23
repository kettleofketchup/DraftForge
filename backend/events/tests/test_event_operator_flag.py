from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event
from events.tests.base import EventTestCase
from org.models import Organization


class EventOperatorFlagTests(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.host = self.make_user()
        self.helper = self.make_user()
        self.promoter = self.make_user()
        self.org.promoters.add(self.promoter)
        Event.objects.filter(pk=self.event.pk).update(host=self.host)
        self.event.refresh_from_db()
        self.event.helpers.add(self.helper)

    def _detail(self, user: CustomUser | None) -> dict[str, Any]:
        self.client.force_authenticate(user)
        resp = self.client.get(f"/api/events/{self.event.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def _flags(self, user: CustomUser | None) -> tuple[bool, bool]:
        data = self._detail(user)
        return data["user_can_manage"], data["user_is_event_operator"]

    def _list_rows(
        self, user: CustomUser, org: Organization | None = None
    ) -> dict[int, dict[str, Any]]:
        self.client.force_authenticate(user)
        resp = self.client.get("/api/events/", {"organization": (org or self.org).pk})
        self.assertEqual(resp.status_code, 200, resp.content)
        return {r["id"]: r for r in resp.json()}

    def test_org_staff(self) -> None:
        self.assertEqual(self._flags(self.admin), (True, True))

    def test_host(self) -> None:
        self.assertEqual(self._flags(self.host), (False, True))

    def test_helper(self) -> None:
        self.assertEqual(self._flags(self.helper), (False, True))

    def test_unrelated_user(self) -> None:
        self.assertEqual(self._flags(self.unrelated_user), (False, False))

    def test_anonymous(self) -> None:
        self.assertEqual(self._flags(None), (False, False))

    def test_promoter_non_helper(self) -> None:
        self.assertEqual(self._flags(self.promoter), (False, False))

    def test_list_endpoint_sets_flag_per_event(self) -> None:
        other = self.make_event()
        rows = self._list_rows(self.host)
        self.assertTrue(rows[self.event.pk]["user_is_event_operator"])
        self.assertFalse(rows[other.pk]["user_is_event_operator"])

    def test_list_flag_helper_on_other_event(self) -> None:
        other = self.make_event()
        other_helper = self.make_user()
        other.helpers.add(other_helper)
        rows = self._list_rows(other_helper)
        self.assertFalse(rows[self.event.pk]["user_is_event_operator"])
        self.assertTrue(rows[other.pk]["user_is_event_operator"])

    def test_flag_not_cached_across_users(self) -> None:
        self.assertTrue(self._flags(self.helper)[1])
        self.assertFalse(self._flags(self.unrelated_user)[1])
        self.assertTrue(self._flags(self.helper)[1])

    def _helper_lookup_queries(self, count: int) -> list[str]:
        owner = self.make_user()
        org = Organization.objects.create(name=f"Flag Org {count}", owner=owner)
        helper = self.make_user()
        for _ in range(count):
            self.make_event(organization=org).helpers.add(helper)
        self._list_rows(helper, org)
        with CaptureQueriesContext(connection) as ctx:
            rows = self._list_rows(helper, org)
        self.assertEqual(len(rows), count)
        self.assertTrue(all(r["user_is_event_operator"] for r in rows.values()))
        return [
            q["sql"] for q in ctx.captured_queries if "events_event_helpers" in q["sql"]
        ]

    def test_list_flag_helper_lookup_is_one_query(self) -> None:
        self.assertEqual(len(self._helper_lookup_queries(2)), 1)
        self.assertEqual(len(self._helper_lookup_queries(5)), 1)
