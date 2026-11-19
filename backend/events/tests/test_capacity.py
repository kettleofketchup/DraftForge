from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone as tz
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization
from events.capacity import (
    count_seats,
    free_seats,
    has_free_seat,
    with_signup_counts,
)
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.schemas import EventTaskSchema
from events.serializers import EventSignupSerializer
from events.services import (
    _promote_from_waitlist,
    cancel_signup,
    create_tentative_signup,
    process_rsvp,
)
from events.tasks import _sync_discord_event_signups_impl
from events.tests.base import EventTestCase
from events.views import EventSignupViewSet

INTERNAL_TOKEN = "test-internal-token"


class SeatCapacityTests(EventTestCase):
    def _waitlist(self, event: Event, user: CustomUser, position: int) -> EventSignup:
        return EventSignup.objects.create(
            event=event,
            user=user,
            status=SignupStatus.WAITLISTED,
            waitlist_position=position,
        )

    def test_tentative_does_not_take_a_seat(self) -> None:
        event = self.make_event(max_players=2)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        create_tentative_signup(event, a)
        process_rsvp(event, b)
        self.assertEqual(process_rsvp(event, c).status, SignupStatus.APPROVED)

    def test_cancel_promotes_past_tentative(self) -> None:
        event = self.make_event(max_players=1)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        b_signup = process_rsvp(event, b)
        c_signup = process_rsvp(event, c)
        self.assertEqual(c_signup.status, SignupStatus.WAITLISTED)
        create_tentative_signup(event, a)

        cancel_signup(b_signup)

        c_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.APPROVED)
        self.assertIsNone(c_signup.waitlist_position)

    def test_tentative_upgrade_when_full_waitlists(self) -> None:
        event = self.make_event(max_players=1)
        a, b = self.make_user(), self.make_user()
        process_rsvp(event, b)
        create_tentative_signup(event, a)
        self.assertEqual(process_rsvp(event, a).status, SignupStatus.WAITLISTED)

    def test_cancel_tentative_promotes_nobody(self) -> None:
        event = self.make_event(max_players=2)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        process_rsvp(event, b)
        a_signup = create_tentative_signup(event, a)
        c_signup = self._waitlist(event, c, 1)

        cancel_signup(a_signup)

        c_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.WAITLISTED)

    def test_one_cancel_fills_every_free_seat(self) -> None:
        event = self.make_event(max_players=1)
        b, c, d = self.make_user(), self.make_user(), self.make_user()
        b_signup = process_rsvp(event, b)
        c_signup = self._waitlist(event, c, 1)
        d_signup = self._waitlist(event, d, 2)
        Event.objects.filter(pk=event.pk).update(max_players=3)
        self.assertEqual(b_signup.event.max_players, 1)

        cancel_signup(b_signup)

        c_signup.refresh_from_db()
        d_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.APPROVED)
        self.assertEqual(d_signup.status, SignupStatus.APPROVED)

    def test_lowered_max_players_promotes_nobody(self) -> None:
        event = self.make_event(max_players=3)
        users = [self.make_user() for _ in range(4)]
        signups = [process_rsvp(event, u) for u in users[:3]]
        waitlisted = self._waitlist(event, users[3], 1)
        Event.objects.filter(pk=event.pk).update(max_players=1)
        self.assertEqual(signups[0].event.max_players, 3)

        cancel_signup(signups[0])

        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, SignupStatus.WAITLISTED)
        self.assertFalse(has_free_seat(Event.objects.get(pk=event.pk)))

    def test_count_seats_allow_list(self) -> None:
        event = self.make_event()
        for status in SignupStatus.values:
            EventSignup.objects.create(
                event=event, user=self.make_user(), status=status
            )
        self.assertEqual(count_seats(event), 4)

    def test_free_seats(self) -> None:
        unlimited = self.make_event(max_players=0)
        self.assertIsNone(free_seats(unlimited))
        self.assertIsNone(free_seats(self.make_event(max_players=None)))

        event = self.make_event(max_players=2)
        process_rsvp(event, self.make_user())
        self.assertEqual(free_seats(event), 1)

        overfull = self.make_event(max_players=1)
        for _ in range(2):
            EventSignup.objects.create(
                event=overfull, user=self.make_user(), status=SignupStatus.APPROVED
            )
        self.assertEqual(free_seats(overfull), 0)


class SeatCountSurfacesTests(EventTestCase):
    def _one_signup_per_status(self) -> Event:
        event = self.make_event()
        for status in SignupStatus.values:
            EventSignup.objects.create(
                event=event, user=self.make_user(), status=status
            )
        return event

    def test_counts_agree_for_every_status(self) -> None:
        event = self._one_signup_per_status()

        annotated = with_signup_counts(Event.objects.filter(pk=event.pk)).get()
        rows = self.client.get("/api/events/signups/", {"event": event.pk}).json()

        self.assertEqual(annotated.signup_count, count_seats(event))
        self.assertEqual(sum(r["holds_seat"] for r in rows), count_seats(event))

    def _internal_full(self, event_id: int) -> dict:
        return self.client.get(
            f"/api/internal/events/{event_id}/full/",
            HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN,
        ).json()

    @override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
    def test_internal_full_event_carries_seat_counts(self) -> None:
        event = self._one_signup_per_status()

        data = self._internal_full(event.pk)

        self.assertEqual(data["signup_count"], count_seats(event))
        self.assertEqual(
            data["confirmed_count"],
            event.signups.filter(status=SignupStatus.CONFIRMED).count(),
        )

    @override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
    def test_discord_scheduled_event_description_uses_seat_count(self) -> None:
        event = self._one_signup_per_status()
        Event.objects.filter(pk=event.pk).update(
            discord_sync_signups=True, max_players=10
        )
        response = MagicMock(status_code=200)
        response.json.return_value = {}

        with (
            patch(
                "events.tasks.get_event_for_task",
                side_effect=lambda pk: EventTaskSchema.model_validate(
                    self._internal_full(pk)
                ),
            ),
            patch(
                "events.tasks.get_first_message_log",
                return_value=MagicMock(discord_message_id="555"),
            ),
            patch("events.tasks.create_message_log"),
            patch("events.tasks.req.patch", return_value=response) as patch_call,
        ):
            _sync_discord_event_signups_impl(event.pk)

        description = patch_call.call_args.kwargs["json"]["description"]
        self.assertIn(f"Signups: {count_seats(event)}/10", description)

    @override_settings(CACHEOPS_ENABLED=False)
    def test_signup_list_holds_seat_no_extra_queries(self) -> None:
        event = self._one_signup_per_status()
        view = EventSignupViewSet()
        view.action = "list"
        view.request = Request(
            APIRequestFactory().get("/api/events/signups/", {"event": event.pk})
        )
        signups = list(view.get_queryset())
        serializer = EventSignupSerializer()

        with self.assertNumQueries(0):
            flags = [serializer.get_holds_seat(s) for s in signups]

        self.assertEqual(sum(flags), count_seats(event))


class PromoteRequiresAtomicTests(TransactionTestCase):
    def setUp(self) -> None:
        owner = CustomUser.objects.create_user(username="atomic_owner", password="x")
        org = Organization.objects.create(name="Atomic Org", owner=owner)
        self.event = Event.objects.create(
            organization=org,
            name="Atomic Event",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=owner,
            max_players=2,
        )

    def test_promote_requires_atomic(self) -> None:
        with self.assertRaises(AssertionError):
            _promote_from_waitlist(self.event)


NOTIFY_PATH = (
    "events.management.commands.rebalance_event_waitlists.notify_signup_changed"
)
INVALIDATE_PATH = (
    "events.management.commands.rebalance_event_waitlists.invalidate_after_commit"
)


class RebalanceCommandTests(EventTestCase):
    def setUp(self) -> None:
        self.phantom = self.make_event(max_players=2)
        for _ in range(2):
            EventSignup.objects.create(
                event=self.phantom, user=self.make_user(), status=SignupStatus.TENTATIVE
            )
        self.waitlisted = EventSignup.objects.create(
            event=self.phantom,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        self.empty_waitlist = self.make_event(max_players=5)
        self.roll_call = self.make_event(max_players=2, state=EventState.ROLL_CALL)
        for _ in range(2):
            EventSignup.objects.create(
                event=self.roll_call,
                user=self.make_user(),
                status=SignupStatus.TENTATIVE,
            )
        self.roll_call_waitlisted = EventSignup.objects.create(
            event=self.roll_call,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )

    def _run(self, *args: str) -> str:
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("rebalance_event_waitlists", *args, stdout=out)
        return out.getvalue()

    def _notified_pks(self, notify: MagicMock) -> list[int]:
        return [c.args[0].pk for c in notify.call_args_list]

    def test_dry_run_changes_nothing(self) -> None:
        with patch(NOTIFY_PATH) as notify:
            output = self._run("--dry-run")

        self.waitlisted.refresh_from_db()
        self.assertEqual(self.waitlisted.status, SignupStatus.WAITLISTED)
        self.assertEqual(self.waitlisted.waitlist_position, 1)
        self.assertIn(self.phantom.name, output)
        self.assertIn("would promote 1", output)
        notify.assert_not_called()

    def test_promotes_invalidates_and_notifies_once(self) -> None:
        with (
            patch(NOTIFY_PATH) as notify,
            patch(INVALIDATE_PATH, wraps=invalidate_after_commit) as invalidate,
        ):
            self._run()

        self.waitlisted.refresh_from_db()
        self.assertEqual(self.waitlisted.status, SignupStatus.APPROVED)
        self.assertIsNone(self.waitlisted.waitlist_position)
        self.assertEqual(self._notified_pks(notify), [self.phantom.pk])
        invalidated = [
            obj.pk
            for c in invalidate.call_args_list
            for obj in c.args
            if isinstance(obj, Event)
        ]
        self.assertIn(self.phantom.pk, invalidated)

    def test_skips_events_not_open_for_signups(self) -> None:
        with patch(NOTIFY_PATH) as notify:
            dry_output = self._run("--dry-run")
            self._run()

        self.roll_call_waitlisted.refresh_from_db()
        self.assertEqual(self.roll_call_waitlisted.status, SignupStatus.WAITLISTED)
        self.assertEqual(self.roll_call_waitlisted.waitlist_position, 1)
        self.assertNotIn(self.roll_call.name, dry_output)
        self.assertNotIn(self.roll_call.pk, self._notified_pks(notify))

    def test_dry_run_matches_real_run_for_unlimited_capacity(self) -> None:
        unlimited = self.make_event(max_players=0)
        for position in (1, 2):
            EventSignup.objects.create(
                event=unlimited,
                user=self.make_user(),
                status=SignupStatus.WAITLISTED,
                waitlist_position=position,
            )

        with patch(NOTIFY_PATH):
            dry_output = self._run("--dry-run")
            real_output = self._run()

        self.assertIn(f"(#{unlimited.pk}): would promote 2", dry_output)
        self.assertIn(f"(#{unlimited.pk}): promoted 2", real_output)
        self.assertFalse(
            EventSignup.objects.filter(
                event=unlimited, status=SignupStatus.WAITLISTED
            ).exists()
        )

    def test_idempotent(self) -> None:
        with patch(NOTIFY_PATH) as notify:
            self._run()
            notify.reset_mock()
            self._run()

        notify.assert_not_called()
        self.assertEqual(count_seats(self.phantom), 1)
