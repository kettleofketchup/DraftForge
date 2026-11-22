from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, ProfileClaimRequest, Tournament
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from league.models import League
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import (
    ContributionEntry,
    Organization,
    OrgFeature,
    OrgLog,
    OrgUser,
    PromoSend,
    PromoTemplate,
)
from org.promotion.services import record_promo_send, undo_promo_send

# Close, reopen, merge and delete counts include the registered conduct and
# leadership tracks.
CLOSE_ADMIN_COMPLETE_QUERIES = 46
CLOSE_AUTO_CANCEL_QUERIES = 42
CLOSE_ADMIN_CANCEL_QUERIES = 12
CLOSE_AUTO_CANCEL_NO_STAFF_QUERIES = 12
REOPEN_QUERIES = 12
PATCH_NAME_QUERIES = 21
PATCH_UNRELATED_QUERIES = 15
STAFF_PUT_QUERIES = 39
STAFF_PUT_NOOP_QUERIES = 26
STAFF_PUT_OPEN_QUERIES = 22
MERGE_DISCORD_QUERIES = 200
MERGE_CLAIM_QUERIES = 180
DELETE_API_QUERIES = 111
DELETE_ADMIN_QUERIES = 162
DELETE_ADMIN_CONFIRM_QUERIES = 53
PROMO_SEND_QUERIES = 23
PROMO_UNDO_QUERIES = 8
PROMO_RELEASE_QUERIES = 124
LEADERBOARD_MEMBER_QUERIES = 8
LEADERBOARD_ANON_QUERIES = 3
LEADERBOARD_OWN_ROW_QUERIES = 8
MEMBER_DETAIL_QUERIES = 7
LOCKED_BAD_PERIOD_QUERIES = 2

START = datetime(2024, 3, 10, 18, 0, tzinfo=UTC)
END = START + timedelta(hours=3)
EVENT_NAME = "Parity Event"

Row = tuple[int, str, int, int | None, datetime, str]


def ledger(org: Organization) -> list[Row]:
    return sorted(
        ContributionEntry.objects.nocache()
        .filter(organization=org)
        .values_list(
            "org_user__user_id",
            "kind",
            "points",
            "event_id",
            "occurred_at",
            "event_name",
        ),
        key=lambda row: (row[0], row[1], row[2], row[3] or 0, row[4], row[5]),
    )


def one_log(logs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [entry for entry in logs if entry["event"] == name]
    assert len(matches) == 1, f"{name}: {len(matches)} log lines"
    return matches[0]


@override_settings(CACHEOPS_ENABLED=False)
class _ParityBase(TestCase):
    locked = False

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="parity_admin", password="x", is_staff=True, is_superuser=True
        )
        self.host = CustomUser.objects.create_user(username="parity_host", password="x")
        self.helper_a = CustomUser.objects.create_user(
            username="parity_helper_a", password="x"
        )
        self.helper_b = CustomUser.objects.create_user(
            username="parity_helper_b", password="x"
        )
        self.org = Organization.objects.create(name="Parity Org", owner=self.admin)
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=not self.locked, actor=None
        )
        self.event = Event.objects.create(
            organization=self.org,
            name=EVENT_NAME,
            scheduled_at=START,
            ends_at=END,
            created_by=self.admin,
            state=EventState.IN_PROGRESS,
            host=self.host,
        )
        self.event.helpers.add(self.helper_a, self.helper_b)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def measure(self, expected: int, fn: Callable[[], Any]) -> Any:
        ContentType.objects.clear_cache()
        with CaptureQueriesContext(connection) as ctx:
            result = fn()
        self.queries = ctx.captured_queries
        self.assertEqual(len(ctx.captured_queries), expected)
        return result

    def assertDetails(self, action: str, expected: dict[str, Any]) -> None:
        details = OrgLog.objects.get(organization=self.org, action=action).details
        self.assertEqual(details, expected)
        self.assertEqual(list(details), list(expected))

    def _set_state(self, state: EventState) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=state)
        self.event.refresh_from_db()

    def _close(self, state: EventState, source: str) -> None:
        close_event(self.event, new_state=state, source=source, actor=self.admin)  # type: ignore[arg-type]

    def _complete(self) -> None:
        self._close(EventState.COMPLETED, "admin")

    def _staff_rows(
        self, host: CustomUser, helpers: list[CustomUser], name: str = EVENT_NAME
    ) -> list[Row]:
        rows: list[Row] = [(host.pk, "event_host", 10, self.event.pk, END, name)]
        rows += [(h.pk, "event_helper", 5, self.event.pk, END, name) for h in helpers]
        return sorted(rows)

    def _entry(
        self,
        user: CustomUser,
        kind: str,
        points: int,
        *,
        event: Event | None = None,
        occurred_at: datetime = START,
        awarded_by: CustomUser | None = None,
        org: Organization | None = None,
    ) -> ContributionEntry:
        org = org or self.org
        org_user, _ = OrgUser.objects.get_or_create(user=user, organization=org)
        return ContributionEntry.objects.create(
            org_user=org_user,
            organization=org,
            kind=kind,
            points=points,
            event=event,
            event_name=event.name if event is not None else "",
            reason="thanks" if kind == "manual" else "",
            awarded_by=awarded_by,
            occurred_at=occurred_at,
        )


class CloseParityTest(_ParityBase):
    def test_admin_complete_awards_staff(self) -> None:
        with capture_logs() as logs:
            self.measure(CLOSE_ADMIN_COMPLETE_QUERIES, self._complete)
        self.assertEqual(
            ledger(self.org),
            self._staff_rows(self.host, [self.helper_a, self.helper_b]),
        )
        self.assertDetails(
            "complete_event",
            {
                "event_id": self.event.pk,
                "from": EventState.IN_PROGRESS.value,
                "to": EventState.COMPLETED.value,
                "awarded": 3,
                "captains_snapshotted": 0,
                "leadership_awarded": 0,
            },
        )
        closed = one_log(logs, "event_closed")
        self.assertIs(closed["awarded"], True)
        self.assertEqual(closed["created"], 3)
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_auto_cancel_with_staff_awards(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        with capture_logs() as logs:
            self.measure(
                CLOSE_AUTO_CANCEL_QUERIES,
                lambda: self._close(EventState.CANCELLED, "auto"),
            )
        self.assertEqual(
            ledger(self.org),
            self._staff_rows(self.host, [self.helper_a, self.helper_b]),
        )
        closed = one_log(logs, "event_closed")
        self.assertIs(closed["awarded"], True)
        self.assertEqual(closed["created"], 3)
        self.assertFalse(
            OrgLog.objects.filter(
                organization=self.org, action="complete_event"
            ).exists()
        )
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_admin_cancel_does_not_award(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        with capture_logs() as logs:
            self.measure(
                CLOSE_ADMIN_CANCEL_QUERIES,
                lambda: self._close(EventState.CANCELLED, "admin"),
            )
        self.assertEqual(ledger(self.org), [])
        closed = one_log(logs, "event_closed")
        self.assertIs(closed["awarded"], False)
        self.assertEqual(closed["created"], 0)
        self.assertFalse(
            OrgLog.objects.filter(
                organization=self.org, action="complete_event"
            ).exists()
        )
        self.assertIsNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_auto_cancel_without_staff_does_not_award(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(
            state=EventState.SIGNUPS_OPEN, host=None
        )
        self.event.helpers.clear()
        self.event.refresh_from_db()
        with capture_logs() as logs:
            self.measure(
                CLOSE_AUTO_CANCEL_NO_STAFF_QUERIES,
                lambda: self._close(EventState.CANCELLED, "auto"),
            )
        self.assertEqual(ledger(self.org), [])
        closed = one_log(logs, "event_closed")
        self.assertIs(closed["awarded"], False)
        self.assertEqual(closed["created"], 0)
        self.assertIsNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )


class ReopenParityTest(_ParityBase):
    def test_reopen_revokes_staff_keeps_manual_and_promo(self) -> None:
        self._complete()
        self._entry(self.helper_a, "manual", 5, event=self.event)
        self._entry(self.helper_b, "promo_message", 1, event=self.event)
        with capture_logs() as logs:
            self.measure(
                REOPEN_QUERIES, lambda: reopen_event(self.event, actor=self.admin)
            )
        updates = [
            q["sql"]
            for q in self.queries
            if q["sql"].startswith('UPDATE "events_event"')
        ]
        self.assertEqual(len(updates), 1)
        self.assertEqual(
            ledger(self.org),
            sorted(
                [
                    (self.helper_a.pk, "manual", 5, self.event.pk, START, EVENT_NAME),
                    (
                        self.helper_b.pk,
                        "promo_message",
                        1,
                        self.event.pk,
                        START,
                        EVENT_NAME,
                    ),
                ]
            ),
        )
        self.assertDetails(
            "reopen_event",
            {
                "event_id": self.event.pk,
                "from": EventState.COMPLETED.value,
                "to": EventState.SIGNUPS_OPEN.value,
                "revoked": 3,
                "attendance_reopened": 0,
                "captain_reviews_voided": 0,
                "leadership_revoked": 0,
            },
        )
        self.assertEqual(one_log(logs, "event_reopened")["revoked"], 3)
        event = Event.objects.nocache().get(pk=self.event.pk)
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(event.contributions_awarded_at)


class EventEditParityTest(_ParityBase):
    def _patch(self, data: dict[str, Any]) -> Any:
        return self.client.patch(
            reverse("event-detail", args=[self.event.pk]), data, format="json"
        )

    def _put_staff(self, host: CustomUser, helpers: list[CustomUser]) -> Any:
        return self.client.put(
            f"/api/events/{self.event.pk}/staff/",
            {"host_id": host.pk, "helper_ids": [h.pk for h in helpers]},
            format="json",
        )

    def test_patch_name_resyncs_completed_event(self) -> None:
        self._complete()
        response = self.measure(
            PATCH_NAME_QUERIES, lambda: self._patch({"name": "Renamed"})
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            ledger(self.org),
            self._staff_rows(self.host, [self.helper_a, self.helper_b], "Renamed"),
        )

    def test_patch_unrelated_field_does_not_resync(self) -> None:
        self._complete()
        ContributionEntry.objects.nocache().filter(organization=self.org).update(
            event_name="Stale"
        )
        response = self.measure(
            PATCH_UNRELATED_QUERIES, lambda: self._patch({"description": "New text"})
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            ledger(self.org),
            self._staff_rows(self.host, [self.helper_a, self.helper_b], "Stale"),
        )

    def _staff_details(
        self, host: CustomUser, helpers: list[CustomUser]
    ) -> dict[str, Any]:
        return {
            "event_id": self.event.pk,
            "host_id": host.pk,
            "helper_ids": [h.pk for h in helpers],
            "previous_host_id": self.host.pk,
            "previous_helper_ids": sorted([self.helper_a.pk, self.helper_b.pk]),
        }

    def test_staff_put_resyncs_and_logs_synced(self) -> None:
        self._complete()
        with capture_logs() as logs:
            response = self.measure(
                STAFF_PUT_QUERIES, lambda: self._put_staff(self.helper_a, [self.host])
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ledger(self.org), self._staff_rows(self.helper_a, [self.host]))
        self.assertIs(one_log(logs, "event_staff_set")["synced"], True)
        self.assertDetails(
            "set_event_staff", self._staff_details(self.helper_a, [self.host])
        )

    def test_staff_put_noop_resync_still_logs_synced_true(self) -> None:
        self._complete()
        helpers = [self.helper_a, self.helper_b]
        with capture_logs() as logs:
            response = self.measure(
                STAFF_PUT_NOOP_QUERIES, lambda: self._put_staff(self.host, helpers)
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ledger(self.org), self._staff_rows(self.host, helpers))
        self.assertIs(one_log(logs, "event_staff_set")["synced"], True)
        self.assertDetails("set_event_staff", self._staff_details(self.host, helpers))

    def test_staff_put_on_open_event_logs_synced_false(self) -> None:
        with capture_logs() as logs:
            response = self.measure(
                STAFF_PUT_OPEN_QUERIES, lambda: self._put_staff(self.helper_a, [])
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ledger(self.org), [])
        self.assertIs(one_log(logs, "event_staff_set")["synced"], False)
        self.assertDetails("set_event_staff", self._staff_details(self.helper_a, []))


class MergeParityTest(_ParityBase):
    def setUp(self) -> None:
        super().setUp()
        self.keep = CustomUser.objects.create_user(
            username="parity_keep", password="x", discordId="771000111"
        )
        self.drop = CustomUser.objects.create_user(username="parity_drop", password="x")
        self.member = CustomUser.objects.create_user(
            username="parity_member", password="x"
        )
        OrgUser.objects.create(user=self.keep, organization=self.org)
        OrgUser.objects.create(user=self.drop, organization=self.org)
        Event.objects.filter(pk=self.event.pk).update(host=self.drop)
        self.event.helpers.set([self.keep])
        self.event.refresh_from_db()
        self._complete()
        self.award_at = START + timedelta(days=1)
        self.manual = self._entry(
            self.member, "manual", 5, occurred_at=self.award_at, awarded_by=self.drop
        )
        self.feature = OrgFeature.objects.create(
            organization=self.org,
            feature=FeatureKey.PROMOTION,
            enabled=True,
            enabled_by=self.drop,
        )
        self.template = PromoTemplate.objects.create(
            organization=self.org, name="Parity", body="Hi", created_by=self.drop
        )

    def _assert_merged(self) -> None:
        self.assertFalse(CustomUser.objects.filter(pk=self.drop.pk).exists())
        self.assertEqual(
            ledger(self.org),
            sorted(
                [
                    (self.keep.pk, "event_host", 10, self.event.pk, END, EVENT_NAME),
                    (self.member.pk, "manual", 5, None, self.award_at, ""),
                ]
            ),
        )
        event = Event.objects.nocache().get(pk=self.event.pk)
        self.assertEqual(event.host_id, self.keep.pk)
        self.assertFalse(event.helpers.nocache().exists())
        self.manual.refresh_from_db()
        self.feature.refresh_from_db()
        self.template.refresh_from_db()
        self.assertEqual(self.manual.awarded_by_id, self.keep.pk)
        self.assertEqual(self.feature.enabled_by_id, self.keep.pk)
        self.assertEqual(self.template.created_by_id, self.keep.pk)

    def test_discord_merge_collision_and_dedupe(self) -> None:
        self.measure(
            MERGE_DISCORD_QUERIES,
            lambda: merge_discord_accounts(keep=self.keep, drop=self.drop),
        )
        self._assert_merged()

    def test_claim_approve_collision_and_dedupe(self) -> None:
        claim = ProfileClaimRequest.objects.create(
            claimer=self.keep,
            target_user=self.drop,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        response = self.measure(
            MERGE_CLAIM_QUERIES,
            lambda: self.client.post(reverse("claim-request-approve", args=[claim.pk])),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self._assert_merged()


class UserDeleteParityTest(_ParityBase):
    def setUp(self) -> None:
        super().setUp()
        self._complete()
        self.other_org = Organization.objects.create(
            name="Parity Other Org", owner=self.admin
        )
        self._entry(self.helper_a, "manual", 4, org=self.other_org)
        self._entry(self.helper_a, "manual", 6, org=self.other_org)
        self.admin_url = reverse("admin:app_customuser_delete", args=[self.helper_a.pk])

    def _assert_deleted(self) -> None:
        self.assertFalse(CustomUser.objects.filter(pk=self.helper_a.pk).exists())
        self.assertEqual(ledger(self.org), self._staff_rows(self.host, [self.helper_b]))
        self.assertEqual(ledger(self.other_org), [])
        for org, count in ((self.org, 1), (self.other_org, 2)):
            details = OrgLog.objects.get(
                organization=org, action="delete_user_contributions"
            ).details
            expected = {
                "user_id": self.helper_a.pk,
                "username": "parity_helper_a",
                "count": count,
            }
            self.assertEqual(details, expected)
            self.assertEqual(list(details), list(expected))

    def test_api_delete_logs_per_org(self) -> None:
        response = self.measure(
            DELETE_API_QUERIES,
            lambda: self.client.delete(
                reverse("users-detail", args=[self.helper_a.pk])
            ),
        )
        self.assertEqual(response.status_code, 204, response.content)
        self._assert_deleted()

    def test_admin_delete_model(self) -> None:
        self.client.force_login(self.admin)
        response = self.measure(
            DELETE_ADMIN_QUERIES,
            lambda: self.client.post(self.admin_url, {"post": "yes"}),
        )
        self.assertEqual(response.status_code, 302)
        self._assert_deleted()

    def test_admin_delete_confirmation_lists_entries(self) -> None:
        self.client.force_login(self.admin)
        org_user = OrgUser.objects.get(user=self.helper_a, organization=self.org)
        response = self.measure(
            DELETE_ADMIN_CONFIRM_QUERIES, lambda: self.client.get(self.admin_url)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f"Contribution entry: event_helper +5 for org_user {org_user.pk}"
        )
        self.assertNotContains(response, "protected related objects")
        self.assertNotContains(response, "would require deleting")
        self.assertEqual(response.context["perms_lacking"], set())


class PromoParityTest(_ParityBase):
    def setUp(self) -> None:
        super().setUp()
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=None)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)
        self.promoter = self._discord_user("parity_promoter")
        self.promoter_b = self._discord_user("parity_promoter_b")
        self.org.promoters.add(self.promoter, self.promoter_b)
        self.recipient = self._discord_user("parity_recipient")
        OrgUser.objects.create(user=self.recipient, organization=self.org)
        league = League.objects.create(
            name="Parity League", organization=self.org, steam_league_id=88471
        )
        past = Tournament.objects.create(
            name="Parity Past",
            date_played=timezone.now() - timedelta(days=4),
            league=league,
        )
        past.users.add(self.recipient)
        self.promo_event = Event.objects.create(
            organization=self.org,
            name="Promo Night",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.admin,
            state=EventState.UPCOMING,
        )

    def _discord_user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        user.discordId = str(884100000000000000 + user.pk)
        user.discordUsername = f"{username}_dc"
        user.save()
        return user

    def _send(self, sender: CustomUser) -> PromoSend:
        return record_promo_send(
            sender=sender,
            event=self.promo_event,
            recipient=self.recipient,
            template=None,
            text="Come play",
        )

    def _promo_row(self, send: PromoSend) -> Row:
        assert send.sender_id is not None
        return (
            send.sender_id,
            "promo_message",
            1,
            self.promo_event.pk,
            send.sent_at,
            "Promo Night",
        )

    def test_send_awards_and_view_returns_points(self) -> None:
        self.client.force_authenticate(self.promoter)
        url = reverse(
            "org-promotion-sends",
            kwargs={"org_id": self.org.pk, "event_id": self.promo_event.pk},
        )
        response = self.measure(
            PROMO_SEND_QUERIES,
            lambda: self.client.post(
                url, {"recipient_id": self.recipient.pk, "text": "Hi"}, format="json"
            ),
        )
        self.assertEqual(response.status_code, 201, response.content)
        send = PromoSend.objects.get()
        self.assertEqual(
            response.json(),
            {
                "id": send.pk,
                "earns_points": True,
                "points_awarded": 1,
                "sent_at": serializers.DateTimeField().to_representation(send.sent_at),
            },
        )
        self.assertEqual(ledger(self.org), [self._promo_row(send)])

    def test_undo_revokes_entry(self) -> None:
        send = self._send(self.promoter)
        self.assertEqual(ledger(self.org), [self._promo_row(send)])
        with capture_logs() as logs:
            self.measure(
                PROMO_UNDO_QUERIES, lambda: undo_promo_send(send, actor=self.admin)
            )
        self.assertEqual(ledger(self.org), [])
        undone = one_log(logs, "promo_send_undone")
        self.assertIs(undone["was_earning"], True)
        self.assertIsNone(undone["promoted_send_id"])

    def test_release_on_sender_delete_promotes_next_send(self) -> None:
        first = self._send(self.promoter)
        second = self._send(self.promoter_b)
        self.assertFalse(second.earns_points)
        response = self.measure(
            PROMO_RELEASE_QUERIES,
            lambda: self.client.delete(
                reverse("users-detail", args=[self.promoter.pk])
            ),
        )
        self.assertEqual(response.status_code, 204, response.content)
        second.refresh_from_db()
        self.assertTrue(second.earns_points)
        self.assertFalse(
            PromoSend.objects.filter(pk=first.pk, sender__isnull=False).exists()
        )
        self.assertEqual(ledger(self.org), [self._promo_row(second)])
        details = OrgLog.objects.get(
            organization=self.org, action="delete_user_contributions"
        ).details
        self.assertEqual(
            details,
            {"user_id": self.promoter.pk, "username": "parity_promoter", "count": 1},
        )


class LeaderboardParityTest(_ParityBase):
    def setUp(self) -> None:
        super().setUp()
        self._complete()
        self.viewer = CustomUser.objects.create_user(
            username="parity_viewer", password="x"
        )
        self.viewer_ou = OrgUser.objects.create(user=self.viewer, organization=self.org)

    def _ou(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=self.org)

    def _summary(self, user: CustomUser) -> dict[str, Any]:
        return {
            "org_user_pk": self._ou(user).pk,
            "user_pk": user.pk,
            "username": user.username,
            "nickname": None,
            "discordNickname": None,
            "guildNickname": None,
            "avatarUrl": user.avatarUrl,
        }

    def _row(self, user: CustomUser, points: int, entries: int) -> dict[str, Any]:
        return {**self._summary(user), "points": points, "entries": entries}

    def _board(self, client: APIClient, query: str = "") -> Any:
        url = reverse("org-contributions-leaderboard", kwargs={"org_id": self.org.pk})
        return client.get(url + query)

    def _viewer_client(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(self.viewer)
        return client

    def test_member_payload(self) -> None:
        client = self._viewer_client()
        response = self.measure(LEADERBOARD_MEMBER_QUERIES, lambda: self._board(client))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {
                "period": "all",
                "total": 20,
                "rows_visible": True,
                "rows": [
                    self._row(self.host, 10, 1),
                    self._row(self.helper_a, 5, 1),
                    self._row(self.helper_b, 5, 1),
                ],
                "own_row": None,
            },
        )

    def test_anonymous_sees_total_only(self) -> None:
        response = self.measure(
            LEADERBOARD_ANON_QUERIES, lambda: self._board(APIClient())
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {
                "period": "all",
                "total": 20,
                "rows_visible": False,
                "rows": [],
                "own_row": None,
            },
        )

    def test_own_row_for_member_with_zero_total(self) -> None:
        self._entry(self.viewer, "manual", 5)
        self._entry(self.viewer, "manual", -5)
        client = self._viewer_client()
        response = self.measure(
            LEADERBOARD_OWN_ROW_QUERIES, lambda: self._board(client)
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total"], 20)
        self.assertNotIn(self.viewer.pk, [row["user_pk"] for row in body["rows"]])
        self.assertEqual(body["own_row"], self._row(self.viewer, 0, 2))

    def test_member_detail_payload(self) -> None:
        now = timezone.now()
        manual = self._entry(self.host, "manual", 3, occurred_at=now)
        host_ou = self._ou(self.host)
        url = reverse(
            "org-contributions-member",
            kwargs={"org_id": self.org.pk, "org_user_pk": host_ou.pk},
        )
        response = self.measure(MEMBER_DETAIL_QUERIES, lambda: self.client.get(url))
        self.assertEqual(response.status_code, 200, response.content)
        staff = ContributionEntry.objects.nocache().get(
            org_user=host_ou, kind="event_host"
        )
        local = now.astimezone(ZoneInfo(self.org.timezone))
        index = local.year * 12 + local.month - 1
        months = [
            f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(index - 11, index + 1)
        ]
        to_rep = serializers.DateTimeField().to_representation
        self.assertEqual(
            response.json(),
            {
                "member": self._summary(self.host),
                "totals": {"all_time": 13, "this_month": 3},
                "monthly": [
                    {"month": month, "points": 3 if month == months[-1] else 0}
                    for month in months
                ],
                "entries": [
                    {
                        "pk": manual.pk,
                        "kind": "manual",
                        "points": 3,
                        "event": None,
                        "event_name": "",
                        "occurred_at": to_rep(manual.occurred_at),
                        "reason": "thanks",
                    },
                    {
                        "pk": staff.pk,
                        "kind": "event_host",
                        "points": 10,
                        "event": {"id": self.event.pk, "name": EVENT_NAME},
                        "event_name": EVENT_NAME,
                        "occurred_at": to_rep(END),
                        "reason": "",
                    },
                ],
            },
        )

    def test_locked_feature_beats_bad_period(self) -> None:
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=False, actor=None)
        client = self._viewer_client()
        response = self.measure(
            LOCKED_BAD_PERIOD_QUERIES, lambda: self._board(client, "?period=bogus")
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(
            response.json(),
            {
                "code": "feature_locked",
                "detail": "This feature is not enabled for this organization.",
            },
        )


class LockedCloseParityTest(CloseParityTest):
    locked = True


class LockedEventEditParityTest(EventEditParityTest):
    locked = True


class LockedMergeParityTest(MergeParityTest):
    locked = True


class LockedReopenParityTest(ReopenParityTest):
    locked = True
