from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, Organization, OrgLog
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from org.contributions.kinds import ContributionKind
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import ContributionEntry, OrgUser
from org.views import ClaimRequestViewSet

QUERIES: dict[str, int] = {
    "close_admin": 29,
    "close_auto_cancel": 28,
    "close_admin_cancel": 5,
    "reopen": 7,
    "patch_name": 20,
    "staff_edit": 39,
    "staff_noop": 25,
    "merge_discord": 156,
    "merge_claim": 131,
    "delete_user": 90,
    "leaderboard": 8,
    "member": 10,
}


def rows(org: Organization) -> list[tuple[Any, ...]]:
    return list(
        ContributionEntry.objects.nocache()
        .filter(organization=org)
        .order_by("org_user__user__username", "kind", "event_id")
        .values_list("org_user__user__username", "kind", "points", "event_id")
    )


@override_settings(CACHEOPS_ENABLED=False)
class _Parity(TestCase):
    locked = False

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="par_admin", password="x", is_staff=True, is_superuser=True
        )
        self.host = CustomUser.objects.create_user(username="par_host", password="x")
        self.helper = CustomUser.objects.create_user(
            username="par_helper", password="x"
        )
        self.org = Organization.objects.create(name="Parity Org", owner=self.admin)
        if not self.locked:
            set_org_feature(
                self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.admin
            )
        self.event = self._event("Parity Event")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _event(self, name: str) -> Event:
        event = Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=timezone.now() - timedelta(hours=3),
            ends_at=timezone.now() - timedelta(hours=1),
            created_by=self.admin,
            state=EventState.IN_PROGRESS,
            host=self.host,
        )
        event.helpers.add(self.helper)
        return event

    def measure(self, name: str, fn: Callable[[], Any]) -> Any:
        with CaptureQueriesContext(connection) as ctx:
            result = fn()
        self.assertEqual(
            len(ctx.captured_queries),
            QUERIES[name],
            f"{name}: {len(ctx.captured_queries)} queries",
        )
        return result

    def _close(self, state: EventState, source: str) -> None:
        close_event(self.event, new_state=state, source=source, actor=self.admin)  # type: ignore[arg-type]


class ContributionParityTest(_Parity):
    def test_close_admin_awards_and_logs(self) -> None:
        with capture_logs() as logs:
            self.measure(
                "close_admin", lambda: self._close(EventState.COMPLETED, "admin")
            )
        self.assertEqual(
            rows(self.org),
            [
                ("par_helper", "event_helper", 5, self.event.pk),
                ("par_host", "event_host", 10, self.event.pk),
            ],
        )
        details = OrgLog.objects.get(action="complete_event").details
        self.assertEqual(
            details,
            {
                "event_id": self.event.pk,
                "from": EventState.IN_PROGRESS.value,
                "to": EventState.COMPLETED.value,
                "awarded": 2,
            },
        )
        closed = [e for e in logs if e["event"] == "event_closed"][0]
        self.assertEqual((closed["awarded"], closed["created"]), (True, 2))
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def _open(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.SIGNUPS_OPEN)
        self.event.refresh_from_db()

    def test_auto_cancel_with_staff_awards(self) -> None:
        self._open()
        with capture_logs() as logs:
            self.measure(
                "close_auto_cancel",
                lambda: self._close(EventState.CANCELLED, "auto"),
            )
        self.assertEqual(len(rows(self.org)), 2)
        closed = [e for e in logs if e["event"] == "event_closed"][0]
        self.assertEqual((closed["awarded"], closed["created"]), (True, 2))

    def test_admin_cancel_awards_nothing(self) -> None:
        self._open()
        with capture_logs() as logs:
            self.measure(
                "close_admin_cancel",
                lambda: self._close(EventState.CANCELLED, "admin"),
            )
        self.assertEqual(rows(self.org), [])
        closed = [e for e in logs if e["event"] == "event_closed"][0]
        self.assertEqual((closed["awarded"], closed["created"]), (False, 0))
        self.assertIsNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_reopen_revokes_in_one_update(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        with CaptureQueriesContext(connection) as ctx:
            result = self.measure(
                "reopen", lambda: reopen_event(self.event, actor=self.admin)
            )
        updates = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith('UPDATE "events_event"')
        ]
        self.assertEqual(len(updates), 1)
        self.assertEqual(result.revoked, 2)
        self.assertEqual(rows(self.org), [])
        self.assertEqual(
            OrgLog.objects.get(action="reopen_event").details,
            {
                "event_id": self.event.pk,
                "from": EventState.COMPLETED.value,
                "to": EventState.SIGNUPS_OPEN.value,
                "revoked": 2,
            },
        )
        self.assertIsNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_patch_name_resyncs(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        response = self.measure(
            "patch_name",
            lambda: self.client.patch(
                f"/api/events/{self.event.pk}/", {"name": "Renamed"}, format="json"
            ),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            set(
                ContributionEntry.objects.nocache()
                .filter(organization=self.org)
                .values_list("event_name", flat=True)
            ),
            {"Renamed"},
        )

    def _staff(self, host: CustomUser, helpers: list[CustomUser]) -> Any:
        return self.client.put(
            f"/api/events/{self.event.pk}/staff/",
            {"host_id": host.pk, "helper_ids": [h.pk for h in helpers]},
            format="json",
        )

    def test_staff_edit_resyncs_and_logs_synced(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        with capture_logs() as logs:
            response = self.measure(
                "staff_edit", lambda: self._staff(self.helper, [self.host])
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            rows(self.org),
            [
                ("par_helper", "event_host", 10, self.event.pk),
                ("par_host", "event_helper", 5, self.event.pk),
            ],
        )
        staff = [e for e in logs if e["event"] == "event_staff_set"][0]
        self.assertIs(staff["synced"], True)
        self.assertNotIn("synced", OrgLog.objects.get(action="set_event_staff").details)

    def test_noop_staff_edit_still_reports_synced(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        with capture_logs() as logs:
            self.measure("staff_noop", lambda: self._staff(self.host, [self.helper]))
        staff = [e for e in logs if e["event"] == "event_staff_set"][0]
        self.assertIs(staff["synced"], True)
        self.assertEqual(len(rows(self.org)), 2)

    def test_staff_edit_on_open_event_does_not_sync(self) -> None:
        with capture_logs() as logs:
            self._staff(self.helper, [])
        staff = [e for e in logs if e["event"] == "event_staff_set"][0]
        self.assertIs(staff["synced"], False)
        self.assertEqual(rows(self.org), [])

    def _dupes(self) -> tuple[CustomUser, CustomUser]:
        keep = CustomUser.objects.create_user(username="par_keep", password="x")
        drop = CustomUser.objects.create_user(username="par_drop", password="x")
        OrgUser.objects.create(user=keep, organization=self.org)
        OrgUser.objects.create(user=drop, organization=self.org)
        Event.objects.filter(pk=self.event.pk).update(host=keep)
        self.event.helpers.set([drop])
        self.event.refresh_from_db()
        self._close(EventState.COMPLETED, "admin")
        return keep, drop

    def _assert_merged(self, keep: CustomUser) -> None:
        self.assertEqual(
            rows(self.org), [("par_keep", "event_host", 10, self.event.pk)]
        )
        self.assertFalse(self.event.helpers.exists())

    def test_discord_merge(self) -> None:
        keep, drop = self._dupes()
        self.measure(
            "merge_discord", lambda: merge_discord_accounts(keep=keep, drop=drop)
        )
        self._assert_merged(keep)

    def test_claim_merge(self) -> None:
        keep, drop = self._dupes()

        def run() -> None:
            with transaction.atomic():
                ClaimRequestViewSet()._merge_profiles(keep, drop)

        self.measure("merge_claim", run)
        self._assert_merged(keep)

    def test_user_delete_logs_per_org(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        response = self.measure(
            "delete_user",
            lambda: self.client.delete(f"/api/users/{self.helper.pk}/"),
        )
        self.assertLess(response.status_code, 300, response.content)
        log = OrgLog.objects.get(action="delete_user_contributions")
        self.assertEqual(log.details["count"], 1)


class ContributionReadParityTest(_Parity):
    def test_leaderboard_and_member_payloads(self) -> None:
        self._close(EventState.COMPLETED, "admin")
        zero = CustomUser.objects.create_user(username="par_zero", password="x")
        zero_ou = OrgUser.objects.create(user=zero, organization=self.org)
        ContributionEntry.objects.create(
            org_user=zero_ou,
            organization=self.org,
            kind=ContributionKind.MANUAL,
            points=0,
            occurred_at=timezone.now(),
        )
        viewer = APIClient()
        viewer.force_authenticate(zero)
        base = f"/api/organizations/{self.org.pk}/contributions"
        board = self.measure("leaderboard", lambda: viewer.get(f"{base}/leaderboard/"))
        self.assertEqual(board.status_code, 200, board.content)
        body = board.json()
        self.assertEqual(body["total"], 15)
        self.assertEqual([r["points"] for r in body["rows"]], [10, 5])
        self.assertEqual(body["own_row"]["points"], 0)
        self.assertEqual(body["own_row"]["entries"], 1)
        host_ou = OrgUser.objects.get(user=self.host, organization=self.org)
        member = self.measure(
            "member", lambda: viewer.get(f"{base}/members/{host_ou.pk}/")
        )
        self.assertEqual(member.status_code, 200, member.content)
        self.assertEqual(member.json()["totals"]["all_time"], 10)


class LockedContributionParityTest(ContributionParityTest):
    locked = True
