from datetime import timedelta
from typing import Any

from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Organization
from events.constants import EventState
from events.models import Event
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.services import CLOSE_NOTE_MAX
from opsnotices.tests.types import register_test_types
from org.models import OrgUser

RESOLVE_URLS: tuple[str, ...] = ("org_ops_notice_resolve", "event_ops_notice_resolve")


def _make_event(org: Organization, name: str, creator: CustomUser) -> Event:
    return Event.objects.create(
        organization=org,
        name=name,
        scheduled_at=timezone.now() + timedelta(days=7),
        state=EventState.SIGNUPS_OPEN,
        created_by=creator,
    )


class OpsNoticeViewTestBase(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org_admin = CustomUser.objects.create_user(
            username="ops_org_admin", password="testpass"
        )
        cls.org.admins.add(cls.org_admin)
        cls.org_staff = CustomUser.objects.create_user(
            username="ops_org_staff", password="testpass"
        )
        cls.org.staff.add(cls.org_staff)
        cls.site_admin = CustomUser.objects.create_user(
            username="ops_site_admin", password="testpass", is_staff=True
        )
        cls.member = cls.user
        OrgUser.objects.create(user=cls.member, organization=cls.org)
        cls.other_owner = CustomUser.objects.create_user(
            username="ops_other_owner", password="testpass"
        )
        cls.org2 = Organization.objects.create(name="Other Org", owner=cls.other_owner)
        cls.event2 = _make_event(cls.org2, "Other Org Event", cls.other_owner)
        cls.sibling_event = _make_event(cls.org, "Sibling Event", cls.admin)

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.client = APIClient()

    def _as(self, user: CustomUser | None) -> APIClient:
        self.client.force_authenticate(user=user)
        return self.client

    def _notice(self, **overrides: Any) -> OpsNotice:
        fields: dict[str, Any] = {
            "organization": self.org,
            "key": "test.alert",
            "category": "urgent",
            "severity": "warning",
            "payload": {"member_id": 1, "reason": "late"},
        }
        fields.update(overrides)
        event = fields.get("event")
        if event is not None:
            fields.setdefault("event_key", event.pk)
            fields.setdefault("event_name", event.name)
        if fields.get("state") == OpsNotice.State.RESOLVED:
            fields.setdefault("closed_at", timezone.now())
        return OpsNotice.objects.create(**fields)

    def _org_list(self, user: CustomUser | None, query: str = "") -> Response:
        url = reverse("org_ops_notices", args=[self.org.pk])
        return self._as(user).get(f"{url}{query}")

    def _event_list(
        self, user: CustomUser | None, event: Event | None = None, query: str = ""
    ) -> Response:
        url = reverse("event_ops_notices", args=[(event or self.event).pk])
        return self._as(user).get(f"{url}{query}")

    def _resolve_url(
        self, name: str, notice: OpsNotice, event: Event | None = None
    ) -> str:
        if name == "org_ops_notice_resolve":
            return reverse(name, args=[self.org.pk, notice.pk])
        return reverse(name, args=[(event or self.event).pk, notice.pk])

    @staticmethod
    def _ids(response: Response) -> list[int]:
        return [row["id"] for row in response.json()]


class PermissionTests(OpsNoticeViewTestBase):
    def test_org_staff_roles_get_200_on_both_lists(self) -> None:
        for user in (self.org_staff, self.org_admin, self.admin, self.site_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self._org_list(user).status_code, 200)
                self.assertEqual(self._event_list(user).status_code, 200)

    def test_league_staff_event_list_only(self) -> None:
        mine = self._notice(event=self.event)
        self._notice(event=self.sibling_event)
        self._notice()
        response = self._event_list(self.league_staff)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [mine.pk])
        self.assertEqual(self._org_list(self.league_staff).status_code, 403)
        self.assertEqual(
            self._event_list(self.league_staff, self.sibling_event).status_code, 403
        )

    def test_member_and_non_member_get_403(self) -> None:
        for user in (self.member, self.unrelated_user):
            with self.subTest(user=user.username):
                self.assertEqual(self._org_list(user).status_code, 403)
                self.assertEqual(self._event_list(user).status_code, 403)

    def test_anonymous_gets_403_on_all_four(self) -> None:
        notice = self._notice(event=self.event)
        client = APIClient()
        urls = [
            reverse("org_ops_notices", args=[self.org.pk]),
            reverse("event_ops_notices", args=[self.event.pk]),
        ]
        for name in RESOLVE_URLS:
            urls.append(self._resolve_url(name, notice))
        for index, url in enumerate(urls):
            with self.subTest(url=url):
                if index < 2:
                    response = client.get(url)
                else:
                    response = client.post(url, {}, format="json")
                self.assertEqual(response.status_code, 403)

    def test_unknown_org_and_event_404(self) -> None:
        client = self._as(self.site_admin)
        self.assertEqual(
            client.get(reverse("org_ops_notices", args=[999999])).status_code, 404
        )
        self.assertEqual(
            client.get(reverse("event_ops_notices", args=[999999])).status_code, 404
        )
        self.assertEqual(
            client.post(
                reverse("org_ops_notice_resolve", args=[999999, 1]), {}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            client.post(
                reverse("event_ops_notice_resolve", args=[999999, 1]), {}, format="json"
            ).status_code,
            404,
        )


class ListTests(OpsNoticeViewTestBase):
    def test_state_filter(self) -> None:
        open_row = self._notice()
        closed = self._notice(state=OpsNotice.State.RESOLVED)
        cases = {
            "": [open_row.pk],
            "?state=open": [open_row.pk],
            "?state=resolved": [closed.pk],
            "?state=all": sorted([open_row.pk, closed.pk], reverse=True),
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                response = self._org_list(self.admin, query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(sorted(self._ids(response), reverse=True), expected)

    def test_category_filter(self) -> None:
        urgent = self._notice()
        task = self._notice(key="test.chore", category="task", severity="info")
        self._notice(key="test.log", category="log", severity="info")
        response = self._org_list(self.admin, "?category=urgent,task")
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(self._ids(response), [urgent.pk, task.pk])
        self.assertEqual(len(self._ids(self._org_list(self.admin))), 3)

    def test_bad_params_return_400(self) -> None:
        for query in (
            "?state=bogus",
            "?category=nope",
            "?category=urgent,nope",
            "?limit=abc",
            "?limit=0",
            "?limit=-3",
        ):
            with self.subTest(query=query):
                self.assertEqual(self._org_list(self.admin, query).status_code, 400)
                self.assertEqual(
                    self._event_list(self.admin, query=query).status_code, 400
                )

    def test_limit_default_and_clamp(self) -> None:
        OpsNotice.objects.bulk_create(
            OpsNotice(
                organization=self.org,
                key="test.alert",
                category="urgent",
                severity="warning",
                payload={"member_id": i, "reason": "late"},
            )
            for i in range(205)
        )
        self.assertEqual(len(self._org_list(self.admin).json()), 50)
        self.assertEqual(len(self._org_list(self.admin, "?limit=3").json()), 3)
        self.assertEqual(len(self._org_list(self.admin, "?limit=1000").json()), 200)

    def test_ordering_last_seen_then_id(self) -> None:
        now = timezone.now()
        older = self._notice()
        tie_a = self._notice()
        tie_b = self._notice()
        OpsNotice.objects.filter(pk=older.pk).update(
            last_seen_at=now - timedelta(hours=1)
        )
        OpsNotice.objects.filter(pk__in=[tie_a.pk, tie_b.pk]).update(last_seen_at=now)
        self.assertEqual(
            self._ids(self._org_list(self.admin)), [tie_b.pk, tie_a.pk, older.pk]
        )

    def test_org_list_includes_event_less_and_excludes_other_org(self) -> None:
        orgwide = self._notice()
        on_event = self._notice(event=self.event)
        self._notice(organization=self.org2, event=self.event2)
        self.assertCountEqual(
            self._ids(self._org_list(self.admin)), [orgwide.pk, on_event.pk]
        )

    def test_event_list_excludes_event_less_and_other_events(self) -> None:
        mine = self._notice(event=self.event)
        self._notice()
        self._notice(event=self.sibling_event)
        self.assertEqual(self._ids(self._event_list(self.admin)), [mine.pk])

    def test_row_shape(self) -> None:
        notice = self._notice(
            event=self.event, subject_user=self.member, actor=self.admin
        )
        row = self._org_list(self.admin).json()[0]
        self.assertEqual(
            list(row),
            [
                "id",
                "key",
                "label",
                "category",
                "severity",
                "state",
                "summary",
                "event_id",
                "event_name",
                "subject_user",
                "actor",
                "dedupe_key",
                "occurrences",
                "first_seen_at",
                "last_seen_at",
                "closed_at",
                "close_note",
                "delivery_state",
                "payload",
            ],
        )
        self.assertEqual(row["id"], notice.pk)
        self.assertEqual(row["label"], "test.alert")
        self.assertEqual(row["summary"], "Member 1: late")
        self.assertEqual(row["event_id"], self.event.pk)
        self.assertEqual(row["event_name"], "Test Event")
        self.assertEqual(
            row["subject_user"],
            {
                "id": self.member.pk,
                "username": "event_user",
                "nickname": "EventUser",
                "avatar": self.member.avatar,
            },
        )
        self.assertEqual(row["actor"]["id"], self.admin.pk)
        self.assertEqual(row["payload"], {"member_id": 1, "reason": "late"})
        self.assertEqual(row["delivery_state"], "pending")

    def test_list_survives_unknown_type_and_stale_payload(self) -> None:
        gone = self._notice(key="gone.type", payload={"x": 1})
        stale = self._notice(payload={"bad": 1})
        response = self._org_list(self.admin)
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()}
        self.assertEqual(rows[gone.pk]["label"], "gone.type")
        self.assertEqual(rows[gone.pk]["summary"], "gone.type")
        self.assertEqual(rows[stale.pk]["label"], "test.alert")
        self.assertEqual(rows[stale.pk]["summary"], "test.alert")
        self.assertEqual(rows[stale.pk]["payload"], {"bad": 1})

    def test_list_query_count_constant(self) -> None:
        def add_row(index: int) -> None:
            subject = CustomUser.objects.create_user(
                username=f"ops_subject_{index}", password="testpass"
            )
            actor = CustomUser.objects.create_user(
                username=f"ops_actor_{index}", password="testpass"
            )
            self.assertTrue(hasattr(subject, "base_profile"))
            event = _make_event(self.org, f"Query Event {index}", self.admin)
            self._notice(event=event, subject_user=subject, actor=actor)

        add_row(0)
        self.assertEqual(self._org_list(self.admin).status_code, 200)
        reset_queries()
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(len(self._org_list(self.admin).json()), 1)
        one_row = len(one.captured_queries)
        self.assertGreater(one_row, 0)
        for index in range(1, 5):
            add_row(index)
        reset_queries()
        with self.assertNumQueries(one_row):
            self.assertEqual(len(self._org_list(self.admin).json()), 5)


class ResolveTests(OpsNoticeViewTestBase):
    def _post(
        self,
        name: str,
        notice: OpsNotice,
        user: CustomUser,
        body: dict[str, Any] | None = None,
        event: Event | None = None,
    ) -> Response:
        return self._as(user).post(
            self._resolve_url(name, notice, event), body or {}, format="json"
        )

    def test_resolve_urgent_defaults_reason_and_logs(self) -> None:
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                notice = self._notice(event=self.event)
                with capture_logs() as logs:
                    response = self._post(name, notice, self.org_staff)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["id"], notice.pk)
                self.assertEqual(body["state"], "resolved")
                self.assertEqual(body["close_note"], "resolved by staff")
                self.assertIsNotNone(body["closed_at"])
                notice.refresh_from_db()
                self.assertEqual(notice.closed_by, self.org_staff)
                entries = [e for e in logs if e["event"] == "ops_notice_staff_resolved"]
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["notice_id"], notice.pk)
                self.assertEqual(entries[0]["user_id"], self.org_staff.pk)
                self.assertEqual(entries[0]["system"], "opsnotices")
                self.assertEqual(entries[0]["subsystem"], "api")

    def test_resolve_custom_reason(self) -> None:
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                notice = self._notice(event=self.event)
                response = self._post(name, notice, self.admin, {"reason": "handled"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["close_note"], "handled")

    def test_resolve_bad_reason_400(self) -> None:
        for name in RESOLVE_URLS:
            for reason in ("x" * (CLOSE_NOTE_MAX + 1), 5):
                with self.subTest(url=name, reason=reason):
                    notice = self._notice(event=self.event)
                    response = self._post(name, notice, self.admin, {"reason": reason})
                    self.assertEqual(response.status_code, 400)
                    notice.refresh_from_db()
                    self.assertEqual(notice.state, OpsNotice.State.OPEN)

    def test_resolve_already_closed_is_unchanged(self) -> None:
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                notice = self._notice(
                    event=self.event,
                    state=OpsNotice.State.RESOLVED,
                    close_note="auto",
                )
                closed_at = notice.closed_at
                with capture_logs() as logs:
                    response = self._post(name, notice, self.admin, {"reason": "again"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["close_note"], "auto")
                notice.refresh_from_db()
                self.assertEqual(notice.closed_at, closed_at)
                self.assertIsNone(notice.closed_by)
                self.assertFalse(
                    [e for e in logs if e["event"] == "ops_notice_staff_resolved"]
                )

    def test_resolve_task_unsupported(self) -> None:
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                notice = self._notice(
                    event=self.event, key="test.chore", category="task", severity="info"
                )
                response = self._post(name, notice, self.admin)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"code": "task_resolve_unsupported"})
                notice.refresh_from_db()
                self.assertEqual(notice.state, OpsNotice.State.OPEN)

    def test_resolve_plain_member_403(self) -> None:
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                notice = self._notice(event=self.event)
                self.assertEqual(self._post(name, notice, self.member).status_code, 403)
                notice.refresh_from_db()
                self.assertEqual(notice.state, OpsNotice.State.OPEN)

    def test_league_staff_resolve_scope(self) -> None:
        notice = self._notice(event=self.event)
        self.assertEqual(
            self._post("org_ops_notice_resolve", notice, self.league_staff).status_code,
            403,
        )
        self.assertEqual(
            self._post(
                "event_ops_notice_resolve", notice, self.league_staff
            ).status_code,
            200,
        )

    def test_cross_org_notice_404(self) -> None:
        foreign = self._notice(organization=self.org2, event=self.event2)
        for name in RESOLVE_URLS:
            with self.subTest(url=name):
                self.assertEqual(self._post(name, foreign, self.admin).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.state, OpsNotice.State.OPEN)

    def test_cross_event_notice_404(self) -> None:
        sibling = self._notice(event=self.sibling_event)
        orgwide = self._notice()
        for notice in (sibling, orgwide):
            with self.subTest(notice=notice.pk):
                response = self._post("event_ops_notice_resolve", notice, self.admin)
                self.assertEqual(response.status_code, 404)
                notice.refresh_from_db()
                self.assertEqual(notice.state, OpsNotice.State.OPEN)
