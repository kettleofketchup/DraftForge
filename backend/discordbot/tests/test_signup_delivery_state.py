from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from discordbot.models import (
    DiscordEventMsgSignup,
    DiscordMessageLog,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)
from discordbot.signup_delivery import (
    BeginOutcome,
    begin_signup_attempt,
    mark_signup_sending,
)
from events.models import Event
from org.models import Organization

CHANNEL = "100000000000000001"


def create_event() -> Event:
    org = Organization.objects.create(name="Synthetic Organization")
    return Event.objects.create(
        organization=org,
        name="Synthetic Event",
        scheduled_at=timezone.now() + timedelta(days=1),
    )


def create_log(event_id: int, success: bool | None = None) -> DiscordMessageLog:
    return DiscordMessageLog.objects.create(
        source="event_announcement",
        source_id=event_id,
        channel_id=CHANNEL,
        embed_data={},
        success=success,
        claimed_at=timezone.now(),
    )


class SignupDeliveryStateTest(TestCase):
    def setUp(self) -> None:
        self.event: Event = create_event()
        self.now: datetime = timezone.now()

    def test_first_begin_creates_row_and_reserves(self) -> None:
        decision = begin_signup_attempt(self.event.pk, now=self.now)
        self.assertEqual(decision.outcome, BeginOutcome.RESERVED)
        self.assertEqual(decision.attempt, 1)
        self.assertEqual(decision.generation, 0)
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(state.state, SignupDeliveryStatus.RESERVED)
        self.assertEqual(state.attempts, 1)
        self.assertEqual(state.attempt_token, decision.attempt_token)
        self.assertIsNotNone(decision.attempt_token)
        self.assertEqual(state.reserved_at, self.now)

    def test_second_begin_while_reserved_is_in_flight(self) -> None:
        first = begin_signup_attempt(self.event.pk, now=self.now)
        second = begin_signup_attempt(self.event.pk, now=self.now)
        self.assertEqual(second.outcome, BeginOutcome.IN_FLIGHT)
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(state.attempts, 1)
        self.assertEqual(state.attempt_token, first.attempt_token)

    def test_pending_message_lease_is_in_flight(self) -> None:
        create_log(self.event.pk)
        decision = begin_signup_attempt(self.event.pk, now=self.now)
        self.assertEqual(decision.outcome, BeginOutcome.IN_FLIGHT)
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).attempts, 0
        )

    def test_legacy_signup_success_is_already_delivered(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id=CHANNEL, has_posted=True
        )
        self.assertEqual(
            begin_signup_attempt(self.event.pk).outcome, BeginOutcome.ALREADY_DELIVERED
        )

    def test_legacy_log_success_is_already_delivered(self) -> None:
        create_log(self.event.pk, success=True)
        self.assertEqual(
            begin_signup_attempt(self.event.pk).outcome, BeginOutcome.ALREADY_DELIVERED
        )

    def test_delivered_state_is_already_delivered_without_legacy_rows(self) -> None:
        SignupPostDeliveryState.objects.create(
            event=self.event, state=SignupDeliveryStatus.DELIVERED
        )
        self.assertEqual(
            begin_signup_attempt(self.event.pk).outcome, BeginOutcome.ALREADY_DELIVERED
        )

    def test_failed_historic_logs_do_not_seed_attempts(self) -> None:
        for _ in range(3):
            create_log(self.event.pk, success=False)
        decision = begin_signup_attempt(self.event.pk)
        self.assertEqual(decision.outcome, BeginOutcome.RESERVED)
        self.assertEqual(decision.attempt, 1)

    def test_stale_reserved_is_released_and_reserved_again(self) -> None:
        first = begin_signup_attempt(self.event.pk, now=self.now)
        second = begin_signup_attempt(
            self.event.pk, now=self.now + timedelta(minutes=6)
        )
        self.assertEqual(second.outcome, BeginOutcome.RESERVED)
        self.assertEqual(second.attempt, 2)
        self.assertNotEqual(first.attempt_token, second.attempt_token)
        self.assertFalse(
            mark_signup_sending(
                self.event.pk, 0, first.attempt_token, create_log(self.event.pk).pk
            )
        )

    def test_stale_fifth_reservation_exhausts_without_sixth_attempt(self) -> None:
        SignupPostDeliveryState.objects.create(event=self.event, attempts=4)
        fifth = begin_signup_attempt(self.event.pk, now=self.now)
        self.assertEqual(fifth.attempt, 5)
        self.assertEqual(
            begin_signup_attempt(self.event.pk, now=self.now).outcome,
            BeginOutcome.IN_FLIGHT,
        )
        for _ in range(3):
            decision = begin_signup_attempt(
                self.event.pk, now=self.now + timedelta(minutes=6)
            )
            self.assertEqual(decision.outcome, BeginOutcome.EXHAUSTED)
            self.assertIsNone(decision.attempt_token)
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(state.attempts, 5)
        self.assertEqual(state.state, SignupDeliveryStatus.EXHAUSTED)
        self.assertFalse(DiscordMessageLog.objects.exists())

    def test_stale_sending_becomes_uncertain_even_at_fifth_attempt(self) -> None:
        SignupPostDeliveryState.objects.create(event=self.event, attempts=4)
        fifth = begin_signup_attempt(self.event.pk, now=self.now)
        log = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, fifth.attempt_token, log.pk)
        )
        self.assertEqual(
            begin_signup_attempt(self.event.pk, now=self.now).outcome,
            BeginOutcome.IN_FLIGHT,
        )
        log.success = False
        log.save()
        self.assertEqual(
            begin_signup_attempt(
                self.event.pk, now=self.now + timedelta(minutes=6)
            ).outcome,
            BeginOutcome.UNCERTAIN,
        )
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(state.state, SignupDeliveryStatus.UNCERTAIN)
        self.assertEqual(state.attempts, 5)

    def test_stale_generation_does_not_reserve_or_change_success(self) -> None:
        SignupPostDeliveryState.objects.create(
            event=self.event, generation=1, state=SignupDeliveryStatus.DELIVERED
        )
        self.assertEqual(
            begin_signup_attempt(self.event.pk, generation=0).outcome,
            BeginOutcome.STALE_GENERATION,
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).attempts, 0
        )

    def test_cooldown_defers_without_reserving(self) -> None:
        due = self.now + timedelta(minutes=1)
        SignupPostDeliveryState.objects.create(
            event=self.event, attempts=1, next_attempt_at=due
        )
        decision = begin_signup_attempt(self.event.pk, now=self.now)
        self.assertEqual(decision.outcome, BeginOutcome.DEFERRED)
        self.assertEqual(decision.next_attempt_at, due)
        self.assertEqual(begin_signup_attempt(self.event.pk, now=due).attempt, 2)

    def test_mark_sending_requires_matching_token_generation_and_pending_owned_log(
        self,
    ) -> None:
        decision = begin_signup_attempt(self.event.pk)
        owned = create_log(self.event.pk)
        self.assertFalse(mark_signup_sending(self.event.pk, 0, uuid4(), owned.pk))
        self.assertFalse(
            mark_signup_sending(self.event.pk, 1, decision.attempt_token, owned.pk)
        )
        self.assertFalse(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, None)
        )
        other_event = create_event()
        other = create_log(other_event.pk)
        self.assertFalse(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, other.pk)
        )
        wrong_source = DiscordMessageLog.objects.create(
            source="event_notice",
            source_id=self.event.pk,
            channel_id=CHANNEL,
            embed_data={},
        )
        self.assertFalse(
            mark_signup_sending(
                self.event.pk, 0, decision.attempt_token, wrong_source.pk
            )
        )
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, owned.pk)
        )
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(state.state, SignupDeliveryStatus.SENDING)
        self.assertEqual(state.active_log_id, owned.pk)

    def test_mark_sending_rejects_finalized_log(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        for success in (False, True):
            with self.subTest(success=success):
                log = create_log(self.event.pk, success=success)
                self.assertFalse(
                    mark_signup_sending(
                        self.event.pk, 0, decision.attempt_token, log.pk
                    )
                )

    def test_fallback_sending_requires_known_failed_previous_log(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        primary = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, primary.pk)
        )
        self.assertFalse(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, primary.pk)
        )
        primary.success = False
        primary.save()
        fallback = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, fallback.pk)
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).active_log_id,
            fallback.pk,
        )

    def test_missing_previous_log_is_not_safe_for_fallback(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        primary = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, primary.pk)
        )
        primary.delete()
        fallback = create_log(self.event.pk)
        self.assertFalse(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, fallback.pk)
        )

    def test_model_not_cacheops_cached(self) -> None:
        self.assertNotIn("discordbot.signuppostdeliverystate", settings.CACHEOPS)


class SignupDeliveryConcurrencyTest(TransactionTestCase):
    def test_concurrent_first_begin_one_winner(self) -> None:
        if connection.vendor == "sqlite" and connection.is_in_memory_db():
            self.skipTest(
                "SQLite shared in-memory tests return SQLITE_LOCKED without busy-timeout waiting; "
                "run with a file-backed test database to exercise concurrent reservations."
            )
        event = create_event()
        barrier = Barrier(2)

        def begin() -> BeginOutcome:
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return begin_signup_attempt(event.pk).outcome
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: begin(), range(2)))
        self.assertCountEqual(outcomes, [BeginOutcome.RESERVED, BeginOutcome.IN_FLIGHT])
        self.assertEqual(SignupPostDeliveryState.objects.get(event=event).attempts, 1)
