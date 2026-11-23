from collections.abc import Callable
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient, APIRequestFactory

from app.models import CustomUser
from events import line
from events.constants import Commitment, EventState, SignupStatus
from events.models import Event, EventSignup
from events.schemas import EventSignupSchema
from events.serializers import EventSignupSerializer
from events.services import cancel_signup, process_rsvp
from events.tests.actors import SYSTEM
from org.models import Organization
from tests.cache import flush_run_cache

NEW_FIELDS = [
    "signed_up_at",
    "commitment",
    "rsvp_class",
    "first_signed_up_at",
    "line_rank",
]


class SignupLineRankApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(name="Rank Org")
        cls.users = [
            CustomUser.objects.create_user(username=f"rank_user_{i}", password="x")
            for i in range(6)
        ]
        cls.staff = CustomUser.objects.create_user(username="rank_staff", password="x")
        cls.org.staff.add(cls.staff)

    def _event(self, max_players: int | None = 3, name: str = "Rank Event") -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            max_players=max_players,
        )

    def _list(self, event: Event | None = None) -> list[dict]:
        params = {"event": event.pk} if event else {}
        response = APIClient().get(reverse("event-signup-list"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _ranks(self, event: Event) -> dict[int, int | None]:
        return {row["id"]: row["line_rank"] for row in self._list(event)}

    def _filled_event(self) -> tuple[Event, list[EventSignup], EventSignup]:
        event = self._event()
        signups = [process_rsvp(event, u, actor=SYSTEM) for u in self.users[:5]]
        cancelled = cancel_signup(signups[1], actor=SYSTEM)
        return event, signups, cancelled

    def test_line_rank_main_and_waitlisted(self) -> None:
        event, signups, cancelled = self._filled_event()
        rows = self._list(event)
        in_line = [r for r in rows if r["line_rank"] is not None]
        self.assertEqual([r["line_rank"] for r in in_line], [1, 2, 3, 4])
        self.assertEqual(
            [r["id"] for r in in_line],
            [signups[i].pk for i in (0, 2, 3, 4)],
        )
        statuses = {r["id"]: r["status"] for r in rows}
        self.assertEqual(statuses[signups[4].pk], SignupStatus.WAITLISTED)
        self.assertIsNone(self._ranks(event)[cancelled.pk])

    def test_dropped_keeps_seq_without_rank(self) -> None:
        event = self._event(max_players=10)
        signups = [process_rsvp(event, u, actor=SYSTEM) for u in self.users[:3]]
        dropped = signups[1]
        seq = dropped.line_seq
        dropped.status = SignupStatus.DROPPED
        dropped.save(update_fields=["status", "updated_at"])
        dropped.refresh_from_db()
        self.assertEqual(dropped.line_seq, seq)
        self.assertEqual(
            self._ranks(event),
            {signups[0].pk: 1, dropped.pk: None, signups[2].pk: 2},
        )
        request = APIRequestFactory().get("/")
        request.user = AnonymousUser()
        data = EventSignupSerializer(dropped, context={"request": request}).data
        self.assertIsNone(data["line_rank"])
        self.assertEqual(data["status"], SignupStatus.DROPPED)
        data = EventSignupSerializer(signups[2], context={"request": request}).data
        self.assertEqual(data["line_rank"], 2)

    def test_line_rank_per_event(self) -> None:
        first = self._event(name="First")
        second = self._event(name="Second")
        a = [process_rsvp(first, u, actor=SYSTEM) for u in self.users[:2]]
        b = [process_rsvp(second, u, actor=SYSTEM) for u in self.users[2:5]]
        self.assertEqual(self._ranks(first), {a[0].pk: 1, a[1].pk: 2})
        self.assertEqual(self._ranks(second), {b[0].pk: 1, b[1].pk: 2, b[2].pk: 3})
        combined = {row["id"]: row["line_rank"] for row in self._list()}
        self.assertEqual(combined[a[0].pk], 1)
        self.assertEqual(combined[b[0].pk], 1)
        self.assertEqual(combined[b[2].pk], 3)

    def _count_list_queries(self) -> int:
        # QueryStatsMiddleware calls reset_queries(), which breaks CaptureQueriesContext.
        flush_run_cache()
        executed: list[str] = []

        def record(execute: Callable, sql: str, *args: object) -> object:
            executed.append(sql)
            return execute(sql, *args)

        with connection.execute_wrapper(record):
            rows = self._list()
        self.assertEqual(len(rows), 6)
        self.assertTrue(executed)
        return len(executed)

    def test_line_rank_adds_no_queries(self) -> None:
        for i in range(3):
            event = self._event(name=f"Q{i}")
            for u in self.users[2 * i : 2 * i + 2]:
                process_rsvp(event, u, actor=SYSTEM)
        with_rank = self._count_list_queries()
        with (
            mock.patch.object(
                line.EventSignupQuerySet, "annotate_line_rank", lambda self: self
            ),
            mock.patch.object(
                EventSignupSerializer, "get_line_rank", lambda self, obj: None
            ),
        ):
            without_rank = self._count_list_queries()
        self.assertEqual(with_rank, without_rank)

    def test_single_object_rank(self) -> None:
        event, signups, cancelled = self._filled_event()
        listed = self._ranks(event)
        request = APIRequestFactory().get("/")
        request.user = AnonymousUser()
        for s in (signups[3], signups[4]):
            data = EventSignupSerializer(
                EventSignup.objects.get(pk=s.pk), context={"request": request}
            ).data
            self.assertEqual(data["line_rank"], listed[s.pk])
        self.assertEqual(listed[signups[3].pk], 3)
        data = EventSignupSerializer(cancelled, context={"request": request}).data
        self.assertIsNone(data["line_rank"])

    def test_detail_routes_rank(self) -> None:
        event = self._event(max_players=10)
        signups = [process_rsvp(event, u, actor=SYSTEM) for u in self.users[:4]]
        third = signups[2]
        client = APIClient()
        response = client.get(reverse("event-signup-detail", args=[third.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["line_rank"], 3)

        client.force_authenticate(self.staff)
        response = client.post(reverse("event-signup-demote", args=[third.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], SignupStatus.WAITLISTED)
        self.assertEqual(response.json()["line_rank"], 3)
        self.assertEqual(self._ranks(event)[third.pk], 3)

        response = client.post(reverse("event-signup-reject", args=[signups[1].pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["line_rank"])

        owner = APIClient()
        owner.force_authenticate(self.users[3])
        response = owner.post(
            reverse("event-signup-cancel-signup", args=[signups[3].pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["line_rank"])
        self.assertEqual(self._ranks(event)[third.pk], 2)

    def test_new_fields_present(self) -> None:
        event = self._event()
        process_rsvp(event, self.users[0], actor=SYSTEM)
        row = self._list(event)[0]
        for name in NEW_FIELDS:
            self.assertIn(name, row)
        self.assertEqual(list(row)[-5:], NEW_FIELDS)
        self.assertEqual(row["commitment"], Commitment.MAIN)
        self.assertIsNotNone(row["signed_up_at"])
        self.assertIsNotNone(row["first_signed_up_at"])
        self.assertEqual(
            list(EventSignupSerializer.Meta.read_only_fields)[-5:], NEW_FIELDS
        )

    def test_pydantic_contract(self) -> None:
        event = self._event()
        signup = process_rsvp(event, self.users[0], actor=SYSTEM)
        request = APIRequestFactory().get("/")
        request.user = AnonymousUser()
        data = EventSignupSerializer(signup, context={"request": request}).data
        schema = EventSignupSchema.model_validate(data)
        self.assertEqual(schema.line_rank, 1)
        self.assertEqual(schema.commitment, Commitment.MAIN)
        self.assertEqual(schema.rsvp_class, data["rsvp_class"])
        self.assertIsNotNone(schema.signed_up_at)
        self.assertIsNotNone(schema.first_signed_up_at)
