import json
from base64 import urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import connection
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import Commitment, SignupAction, SignupStatus
from events.history import HistoryCursor
from events.ledger import (
    ActorRole,
    SignupActor,
    SignupMeans,
    record_signup_change,
)
from events.models import Event, SignupLedgerEntry
from events.schemas import SignupSnapshot
from events.services import cancel_signup, process_rsvp
from events.tests.base import EventTestCase
from league.models import League
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache

FIXTURE_PATH = Path(__file__).parent / "signup_history_page.json"
BASE_TIME = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
QUERY_BUDGET = 4


def _b64(raw: str) -> str:
    return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    if value is None:
        return "null"
    return type(value).__name__


def _snap(status: str, *, line_seq: int = 1, **extra: Any) -> SignupSnapshot:
    return SignupSnapshot(
        status=status,
        commitment=Commitment.MAIN,
        rsvp_class="standard",
        signed_up_at=BASE_TIME - timedelta(days=1),
        line_seq=line_seq,
        waitlist_position=1 if status == SignupStatus.WAITLISTED else None,
        extra=extra,
    )


class SignupHistoryApiTest(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.other_org_staff = CustomUser.objects.create_user(
            username="hist_other_org_staff", password="x"
        )
        other_org = Organization.objects.create(
            name="Other History Org", owner=cls.other_org_staff
        )
        other_org.staff.add(cls.other_org_staff)
        cls.other_league_staff = CustomUser.objects.create_user(
            username="hist_other_league_staff", password="x"
        )
        other_league = League.objects.create(
            name="Other History League", organization=other_org, steam_league_id=88888
        )
        other_league.staff.add(cls.other_league_staff)

    def setUp(self) -> None:
        self._tick = 0

    def _url(self, event: Event | int | None = None) -> str:
        pk = event if isinstance(event, int) else (event or self.event).pk
        return reverse("event-signup-history", args=[pk])

    def _get(
        self,
        user: CustomUser | None,
        params: dict[str, Any] | None = None,
        event: Event | int | None = None,
    ) -> Response:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(self._url(event), params or {})

    def _entry(
        self,
        *,
        subject: CustomUser | None = None,
        actor: SignupActor | None = None,
        action: SignupAction = SignupAction.SIGNED_UP,
        occurred_at: datetime | None = None,
        event: Event | None = None,
        **kwargs: Any,
    ) -> SignupLedgerEntry:
        if occurred_at is None:
            self._tick += 1
            occurred_at = BASE_TIME + timedelta(minutes=self._tick)
        return record_signup_change(
            event=event or self.event,
            subject=subject or self.user,
            actor=actor or SignupActor.system(),
            action=action,
            occurred_at=occurred_at,
            **kwargs,
        )

    def _ids(self, response: Response) -> list[int]:
        return [row["id"] for row in response.data["results"]]

    def _walk(self, params: dict[str, Any]) -> list[Response]:
        pages = [self._get(self.admin, params)]
        while pages[-1].data["next"]:
            cursor = pages[-1].data["next"].split("cursor=")[1].split("&")[0]
            pages.append(self._get(self.admin, {**params, "cursor": cursor}))
            self.assertLess(len(pages), 20)
        return pages

    # Permissions

    def test_anonymous_forbidden(self) -> None:
        self.assertEqual(self._get(None).status_code, 403)

    def test_member_forbidden(self) -> None:
        self.assertEqual(self._get(self.user).status_code, 403)

    def test_unrelated_user_forbidden(self) -> None:
        self.assertEqual(self._get(self.unrelated_user).status_code, 403)

    def test_other_org_staff_forbidden(self) -> None:
        self.assertEqual(self._get(self.other_org_staff).status_code, 403)

    def test_other_league_staff_forbidden(self) -> None:
        self.assertEqual(self._get(self.other_league_staff).status_code, 403)

    def test_org_staff_allowed(self) -> None:
        self.assertEqual(self._get(self.admin).status_code, 200)

    def test_league_staff_allowed(self) -> None:
        self.assertEqual(self._get(self.league_staff).status_code, 200)

    def test_missing_event_404(self) -> None:
        self.assertEqual(self._get(self.admin, event=987654321).status_code, 404)
        self.assertEqual(self._get(None, event=987654321).status_code, 404)

    def test_non_staff_bad_params_still_403(self) -> None:
        for params in ({"action": "bogus"}, {"user": "abc"}, {"cursor": "!!"}):
            with self.subTest(params=params):
                self.assertEqual(self._get(self.user, params).status_code, 403)

    def test_denied_and_viewed_logged(self) -> None:
        with capture_logs() as logs:
            self._get(self.user)
            self._get(self.admin, {"action": "withdrew", "page_size": 5})
        denied = [e for e in logs if e["event"] == "signup_history_denied"]
        viewed = [e for e in logs if e["event"] == "signup_history_viewed"]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0]["user_id"], self.user.pk)
        self.assertEqual(denied[0]["system"], "events")
        self.assertEqual(denied[0]["subsystem"], "ledger")
        self.assertEqual(len(viewed), 1)
        self.assertEqual(viewed[0]["event_id"], self.event.pk)
        self.assertEqual(viewed[0]["filter_action"], "withdrew")
        self.assertEqual(viewed[0]["page_size"], 5)
        self.assertFalse(viewed[0]["has_cursor"])

    # Ordering

    def test_newest_first(self) -> None:
        first = self._entry()
        second = self._entry()
        third = self._entry(occurred_at=BASE_TIME - timedelta(days=1))
        response = self._get(self.admin)
        self.assertEqual(self._ids(response), [second.pk, first.pk, third.pk])
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_identical_timestamps_pk_desc(self) -> None:
        rows = [self._entry(occurred_at=BASE_TIME) for _ in range(3)]
        response = self._get(self.admin)
        self.assertEqual(self._ids(response), [r.pk for r in reversed(rows)])

    def test_other_event_excluded(self) -> None:
        mine = self._entry()
        self._entry(event=self.make_event())
        self.assertEqual(self._ids(self._get(self.admin)), [mine.pk])

    # Pagination

    def test_pagination_walk(self) -> None:
        rows = [self._entry() for _ in range(5)]
        pages = self._walk({"page_size": 2})
        self.assertEqual(len(pages), 3)
        ids = [i for page in pages for i in self._ids(page)]
        self.assertEqual(ids, [r.pk for r in reversed(rows)])
        for page in pages:
            self.assertEqual(page.data["count"], 5)
            self.assertIsNone(page.data["previous"])
        self.assertIsNone(pages[-1].data["next"])
        self.assertIn("page_size=2", pages[0].data["next"])

    def test_pagination_walk_identical_timestamps(self) -> None:
        rows = [self._entry(occurred_at=BASE_TIME) for _ in range(5)]
        ids = [i for page in self._walk({"page_size": 2}) for i in self._ids(page)]
        self.assertEqual(ids, [r.pk for r in reversed(rows)])

    def test_pagination_stable_under_inserts(self) -> None:
        rows = [self._entry() for _ in range(5)]
        first = self._get(self.admin, {"page_size": 2})
        cursor = first.data["next"].split("cursor=")[1].split("&")[0]
        self._entry()
        self._entry()
        second = self._get(self.admin, {"page_size": 2, "cursor": cursor})
        self.assertEqual(self._ids(second), [rows[2].pk, rows[1].pk])
        self.assertEqual(first.data["count"], 5)
        self.assertEqual(second.data["count"], 7)

    def test_default_page_size(self) -> None:
        for _ in range(51):
            self._entry()
        response = self._get(self.admin)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertIsNotNone(response.data["next"])

    # Filters

    @mock.patch("events.services.notify_signup_changed")
    def test_user_filter_spans_resignup(self, _notify: mock.Mock) -> None:
        event = self.make_event()
        member = self.make_user()
        other = self.make_user()
        actor = SignupActor(user=member, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        signup = process_rsvp(event, member, actor=actor)
        cancel_signup(signup, actor=actor)
        process_rsvp(event, member, actor=actor)
        process_rsvp(event, other, actor=SignupActor.system())
        response = self._get(self.admin, {"user": member.pk}, event=event)
        self.assertEqual(response.status_code, 200)
        expected = list(
            SignupLedgerEntry.objects.filter(event=event, subject_user=member)
            .order_by("-occurred_at", "-pk")
            .values_list("pk", flat=True)
        )
        self.assertGreaterEqual(len(expected), 3)
        self.assertEqual(self._ids(response), expected)
        self.assertEqual(response.data["count"], len(expected))
        self.assertTrue(
            {"withdrew", "resigned_up"}
            <= {row["action"] for row in response.data["results"]}
        )
        self.assertEqual(
            {row["subject"]["user_id"] for row in response.data["results"]},
            {member.pk},
        )

    def test_action_filter(self) -> None:
        withdrew = self._entry(action=SignupAction.WITHDREW)
        self._entry(action=SignupAction.SIGNED_UP)
        response = self._get(self.admin, {"action": "withdrew"})
        self.assertEqual(self._ids(response), [withdrew.pk])

    def test_user_and_action_combined(self) -> None:
        other = self.make_user()
        target = self._entry(subject=other, action=SignupAction.WITHDREW)
        self._entry(subject=other, action=SignupAction.SIGNED_UP)
        self._entry(subject=self.user, action=SignupAction.WITHDREW)
        response = self._get(self.admin, {"user": other.pk, "action": "withdrew"})
        self.assertEqual(self._ids(response), [target.pk])
        self.assertEqual(response.data["count"], 1)

    def test_empty_params_ignored(self) -> None:
        row = self._entry()
        response = self._get(self.admin, {"user": "", "action": "", "cursor": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [row.pk])

    # Validation

    def test_bad_params_400(self) -> None:
        cases: list[tuple[dict[str, Any], dict[str, list[str]]]] = [
            ({"action": "bogus"}, {"action": ["Invalid action."]}),
            ({"user": "abc"}, {"user": ["Invalid user."]}),
            ({"user": "0"}, {"user": ["Invalid user."]}),
            ({"user": "-3"}, {"user": ["Invalid user."]}),
            ({"user": "99999999999999999999"}, {"user": ["Invalid user."]}),
            ({"cursor": "garbage!"}, {"cursor": ["Invalid cursor."]}),
            (
                {"cursor": _b64("2026-01-01T00:00:00+00:00|9223372036854775808")},
                {"cursor": ["Invalid cursor."]},
            ),
            ({"page_size": "0"}, {"page_size": ["Invalid page size."]}),
            ({"page_size": "101"}, {"page_size": ["Invalid page size."]}),
            ({"page_size": "x"}, {"page_size": ["Invalid page size."]}),
        ]
        for params, body in cases:
            with self.subTest(params=params):
                response = self._get(self.admin, params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, body)

    def test_max_page_size_ok(self) -> None:
        self.assertEqual(self._get(self.admin, {"page_size": 100}).status_code, 200)

    def test_valid_cursor_past_everything_is_empty(self) -> None:
        self._entry()
        token = HistoryCursor(BASE_TIME - timedelta(days=30), 1).token
        response = self._get(self.admin, {"cursor": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["count"], 1)

    # Query count

    def _count_queries(self, expected_rows: int) -> int:
        flush_run_cache()
        executed: list[str] = []

        def record(execute: Callable, sql: str, *args: object) -> object:
            executed.append(sql)
            return execute(sql, *args)

        with connection.execute_wrapper(record):
            response = self._get(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), expected_rows)
        return len(executed)

    def _staff_entries(self, n: int) -> None:
        for _ in range(n):
            subject = self.make_user()
            staff = self.make_user()
            OrgUser.objects.filter(user=subject, organization=self.org).update(
                guild_nickname="Guild Nick"
            )
            self._entry(
                subject=subject,
                actor=SignupActor(
                    user=staff, role=ActorRole.STAFF, means=SignupMeans.WEB
                ),
            )

    def test_query_count_constant(self) -> None:
        self._staff_entries(2)
        small = self._count_queries(2)
        self._staff_entries(10)
        large = self._count_queries(12)
        self.assertEqual(small, large)
        self.assertLessEqual(large, QUERY_BUDGET)

    # Shared frontend fixture

    def test_matches_shared_fixture(self) -> None:
        event = self.make_event(name="Signup History Fixture Event")
        cara = self.make_user()
        cara.username = "hist_cara"
        cara.nickname = "Cara"
        cara.discordId = "100000000000009003"
        cara.discordNickname = "cara"
        cara.avatar = "abc123"
        cara.save()
        OrgUser.objects.filter(user=cara, organization=self.org).update(
            guild_nickname="Cara (guild)"
        )
        withdraw = self._entry(
            event=event,
            subject=cara,
            actor=SignupActor(
                user=cara, role=ActorRole.MEMBER, means=SignupMeans.DISCORD_BUTTON
            ),
            action=SignupAction.WITHDREW,
            before=_snap(SignupStatus.APPROVED),
            after=_snap(SignupStatus.CANCELLED),
        )
        self._entry(
            event=event,
            subject=cara,
            actor=SignupActor(
                user=self.admin,
                role=ActorRole.STAFF,
                means=SignupMeans.WEB,
                staff_power=True,
            ),
            action=SignupAction.STAFF_ADDED,
            after=_snap(SignupStatus.WAITLISTED, line_seq=3),
            reason="Vouched for by staff",
        )
        self._entry(
            event=event,
            subject=cara,
            action=SignupAction.PROMOTED,
            before=_snap(SignupStatus.WAITLISTED, line_seq=3),
            after=_snap(SignupStatus.APPROVED, line_seq=3),
            caused_by=withdraw,
        )
        response = self._get(self.admin, {"page_size": 2}, event=event)
        self.assertEqual(response.status_code, 200)
        actual = json.loads(json.dumps(response.data))
        fixture = json.loads(FIXTURE_PATH.read_text())
        self.assertEqual(_shape(actual), _shape(fixture))
        for got, want in zip(actual["results"], fixture["results"], strict=True):
            for key in ("action", "means", "on_behalf", "reason"):
                self.assertEqual(got[key], want[key])
            self.assertEqual(got["actor"]["role"], want["actor"]["role"])
            self.assertEqual(got["before"], want["before"])
            self.assertEqual(got["after"], want["after"])
        self.assertEqual(actual["results"][0]["caused_by"], withdraw.pk)
