from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from discordbot import signup_delivery as delivery
from discordbot.delivery_types import (
    ChannelKind,
    DeliveryFailure,
    DeliveryReceipt,
    FailureCategory,
    FailurePhase,
)
from discordbot.models import (
    DiscordEvent,
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


class SignupCompletionTest(TestCase):
    def setUp(self) -> None:
        self.event: Event = create_event()
        self.now: datetime = timezone.now()
        self.failure: DeliveryFailure = DeliveryFailure(
            FailurePhase.CREATE, FailureCategory.HTTP_ERROR, status=403, code=50013
        )
        self.receipt: DeliveryReceipt = DeliveryReceipt(
            CHANNEL, "100000000000000002", None, ChannelKind.TEXT
        )

    def fail_attempt(self, now: datetime) -> delivery.CompletionReply:
        decision = begin_signup_attempt(self.event.pk, now=now)
        self.assertEqual(decision.outcome, BeginOutcome.RESERVED)
        log = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(
                self.event.pk, decision.generation, decision.attempt_token, log.pk
            )
        )
        return delivery.complete_signup_attempt(
            self.event.pk,
            decision.generation,
            decision.attempt_token,
            delivery.CompletionKind.FAILED,
            failure=self.failure,
            log_id=log.pk,
            now=now,
        )

    def deliver(
        self, receipt: DeliveryReceipt | None = None
    ) -> tuple[delivery.BeginDecision, DiscordMessageLog, delivery.CompletionReply]:
        decision = begin_signup_attempt(self.event.pk, now=self.now)
        log = create_log(self.event.pk)
        self.assertTrue(
            mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        )
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=receipt or self.receipt,
            log_id=log.pk,
            now=self.now,
        )
        return decision, log, result

    def test_backoff_progression_1_2_4_8_then_exhausted(self) -> None:
        now = self.now
        for delay in (1, 2, 4, 8):
            result = self.fail_attempt(now)
            due = now + timedelta(minutes=delay)
            self.assertEqual(result.next_attempt_at, due)
            self.assertEqual(result.outcome, "recorded")
            self.assertEqual(
                begin_signup_attempt(
                    self.event.pk, now=due - timedelta(seconds=1)
                ).outcome,
                BeginOutcome.DEFERRED,
            )
            now = due
        result = self.fail_attempt(now)
        self.assertEqual(result.state, SignupDeliveryStatus.EXHAUSTED)
        self.assertIsNone(result.next_attempt_at)
        self.assertEqual(
            begin_signup_attempt(self.event.pk, now=now).outcome, BeginOutcome.EXHAUSTED
        )
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(
            (
                state.last_failure_category,
                state.last_failure_status,
                state.last_failure_code,
            ),
            ("http_error", 403, 50013),
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(success__isnull=True).exists()
        )

    def test_four_failures_then_abandoned_fifth_stays_bounded(self) -> None:
        now = self.now
        for delay in (1, 2, 4, 8):
            self.fail_attempt(now)
            now += timedelta(minutes=delay)
        fifth = begin_signup_attempt(self.event.pk, now=now)
        self.assertEqual(fifth.attempt, 5)
        self.assertEqual(
            begin_signup_attempt(self.event.pk, now=now).outcome, BeginOutcome.IN_FLIGHT
        )
        later = now + timedelta(minutes=6)
        for _ in range(2):
            self.assertEqual(
                begin_signup_attempt(self.event.pk, now=later).outcome,
                BeginOutcome.EXHAUSTED,
            )
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            fifth.attempt_token,
            delivery.CompletionKind.FAILED,
            failure=self.failure,
            now=later,
        )
        self.assertEqual(result.outcome, "stale")
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(
            (state.attempts, state.state), (5, SignupDeliveryStatus.EXHAUSTED)
        )

    def test_failure_backoff_index_is_guarded(self) -> None:
        decision = begin_signup_attempt(self.event.pk, now=self.now)
        for attempts in (0, 5, 6, 100):
            with self.subTest(attempts=attempts):
                SignupPostDeliveryState.objects.filter(event=self.event).update(
                    attempts=attempts, state=SignupDeliveryStatus.RESERVED
                )
                result = delivery.complete_signup_attempt(
                    self.event.pk,
                    0,
                    decision.attempt_token,
                    delivery.CompletionKind.FAILED,
                    failure=self.failure,
                    now=self.now,
                )
                self.assertEqual(
                    result.outcome, "stale" if attempts == 0 else "recorded"
                )
                self.assertEqual(
                    result.state,
                    SignupDeliveryStatus.RESERVED
                    if attempts == 0
                    else SignupDeliveryStatus.EXHAUSTED,
                )
                self.assertIsNone(result.next_attempt_at)

    def test_sweep_does_not_reset_attempts(self) -> None:
        now = self.now
        for delay in (1, 2, 4):
            self.fail_attempt(now)
            now += timedelta(minutes=delay)
        with (
            self.settings(INTERNAL_SERVICE_TOKEN="synthetic-token"),
            patch("app.views.internal.tz.now", return_value=now + timedelta(hours=2)),
        ):
            response = APIClient().post(
                "/api/internal/discord/sweep-stale-leases/",
                {"pending_threshold_minutes": 5, "failed_threshold_hours": 1},
                format="json",
                HTTP_X_INTERNAL_TOKEN="synthetic-token",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["failed_swept"], 3)
        self.assertEqual(
            begin_signup_attempt(self.event.pk, now=now + timedelta(hours=2)).attempt, 4
        )

    def test_delivered_completion_persists_receipt_and_signup_row(self) -> None:
        for kind in (ChannelKind.TEXT, ChannelKind.ANNOUNCEMENT, ChannelKind.FORUM):
            with self.subTest(kind=kind):
                self.event = create_event()
                receipt = DeliveryReceipt(
                    CHANNEL,
                    "100000000000000002",
                    "100000000000000003" if kind == ChannelKind.FORUM else None,
                    kind,
                )
                _, log, result = self.deliver(receipt)
                self.assertTrue(result.persisted)
                msg = DiscordEventMsgSignup.objects.nocache().get(event=self.event)
                self.assertEqual(
                    (
                        msg.channel_id,
                        msg.message_id,
                        msg.thread_id,
                        msg.channel_type,
                        msg.has_posted,
                    ),
                    (
                        CHANNEL,
                        receipt.message_id,
                        receipt.thread_id,
                        receipt.storage_channel_type(),
                        True,
                    ),
                )
                self.assertEqual(
                    DiscordEvent.objects.nocache()
                    .get(event=self.event)
                    .signup_message_id,
                    msg.pk,
                )
                state = SignupPostDeliveryState.objects.get(event=self.event)
                self.assertEqual(state.receipt, receipt.to_json())
                self.assertEqual(state.state, SignupDeliveryStatus.DELIVERED)
                log.refresh_from_db()
                self.assertTrue(log.success)
                self.assertEqual(log.discord_message_id, receipt.message_id)

    def test_repeat_completion_is_idempotent(self) -> None:
        decision, log, _ = self.deliver()
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=self.receipt,
            log_id=log.pk,
        )
        self.assertEqual((result.outcome, result.persisted), ("idempotent", True))
        self.assertEqual(
            DiscordEventMsgSignup.objects.filter(event=self.event).count(), 1
        )
        changed = DeliveryReceipt(CHANNEL, "100000000000000004", None, ChannelKind.TEXT)
        self.assertEqual(
            delivery.complete_signup_attempt(
                self.event.pk,
                0,
                decision.attempt_token,
                delivery.CompletionKind.DELIVERED,
                receipt=changed,
                log_id=log.pk,
            ).outcome,
            "stale",
        )

    def test_stale_token_completion_is_noop(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        before = SignupPostDeliveryState.objects.filter(event=self.event).values().get()
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            uuid4(),
            delivery.CompletionKind.FAILED,
            failure=self.failure,
        )
        self.assertEqual(result.outcome, "stale")
        self.assertEqual(
            SignupPostDeliveryState.objects.filter(event=self.event).values().get(),
            before,
        )
        self.assertIsNotNone(decision.attempt_token)

    def test_completion_rejects_unowned_log_and_invalid_receipt(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        other_log = create_log(create_event().pk)
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=self.receipt,
            log_id=other_log.pk,
        )
        self.assertEqual(result.outcome, "stale")
        with self.assertRaises(ValueError):
            delivery.complete_signup_attempt(
                self.event.pk,
                0,
                decision.attempt_token,
                delivery.CompletionKind.DELIVERED,
                receipt=DeliveryReceipt(CHANNEL, "bad", None, ChannelKind.TEXT),
                log_id=log.pk,
            )
        self.assertFalse(DiscordEventMsgSignup.objects.exists())
        log.refresh_from_db()
        self.assertIsNone(log.success)

    def test_atomic_completion_rolls_back_all_success_gates(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        with (
            patch(
                "discordbot.signup_delivery.invalidate_after_commit",
                side_effect=RuntimeError("synthetic failure"),
            ),
            self.assertRaises(RuntimeError),
        ):
            delivery.complete_signup_attempt(
                self.event.pk,
                0,
                decision.attempt_token,
                delivery.CompletionKind.DELIVERED,
                receipt=self.receipt,
                log_id=log.pk,
            )
        log.refresh_from_db()
        self.assertIsNone(log.success)
        self.assertFalse(DiscordEventMsgSignup.objects.exists())
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.SENDING,
        )

    def test_receipt_channel_must_match_active_log(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        wrong = DeliveryReceipt(
            "100000000000000099", self.receipt.message_id, None, ChannelKind.TEXT
        )
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=wrong,
            log_id=log.pk,
        )
        self.assertEqual(result.outcome, "stale")
        self.assertFalse(DiscordEventMsgSignup.objects.exists())
        log.refresh_from_db()
        self.assertIsNone(log.success)

    def test_stale_completion_does_not_validate_or_persist_receipt(self) -> None:
        begin_signup_attempt(self.event.pk)
        result = delivery.complete_signup_attempt(
            self.event.pk, 0, uuid4(), delivery.CompletionKind.DELIVERED
        )
        self.assertEqual(result.outcome, "stale")
        self.assertFalse(result.persisted)

    def test_invalid_completion_kind_is_rejected_without_mutation(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        with self.assertRaises(ValueError):
            delivery.complete_signup_attempt(
                self.event.pk, 0, decision.attempt_token, "invalid"
            )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.RESERVED,
        )

    def test_completion_requires_active_owned_log(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        old = create_log(self.event.pk, success=False)
        active = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, active.pk)
        for log_id in (old.pk, active.pk + 100):
            result = delivery.complete_signup_attempt(
                self.event.pk,
                0,
                decision.attempt_token,
                delivery.CompletionKind.DELIVERED,
                receipt=self.receipt,
                log_id=log_id,
            )
            self.assertEqual(result.outcome, "stale")
        active.delete()
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=self.receipt,
        )
        self.assertEqual(result.outcome, "stale")
        self.assertFalse(DiscordEventMsgSignup.objects.exists())

    def test_current_link_not_historical_post_controls_deleted_recovery(self) -> None:
        self.deliver()
        DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id="100000000000000010",
            message_id="100000000000000011",
            has_posted=True,
        )
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, "100000000000000011"
            )
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.DELIVERED,
        )

    def test_deleted_recovery_preserves_pending_lease(self) -> None:
        self.deliver()
        DiscordMessageLog.objects.filter(source_id=self.event.pk).update(success=False)
        create_log(self.event.pk)
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).generation, 0
        )

    def test_uncertain_delivery_can_finish_without_resending(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.UNCERTAIN,
            failure=self.failure,
        )
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.DELIVERED,
            receipt=self.receipt,
            log_id=log.pk,
        )
        self.assertTrue(result.persisted)
        self.assertEqual(
            begin_signup_attempt(self.event.pk).outcome, BeginOutcome.ALREADY_DELIVERED
        )

    def test_failed_completion_does_not_demote_successful_log(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        log.success = True
        log.save()
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.FAILED,
            failure=self.failure,
        )
        self.assertEqual(result.outcome, "stale")
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.SENDING,
        )

    def test_text_completion_clears_old_thread(self) -> None:
        msg = DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id=CHANNEL,
            thread_id="100000000000000003",
            channel_type="forum",
        )
        DiscordEvent.objects.create(
            event=self.event, guild_id="100000000000000005", signup_message=msg
        )
        self.deliver()
        msg.refresh_from_db()
        self.assertIsNone(msg.thread_id)
        self.assertEqual(msg.channel_type, "text")

    def test_reset_while_active_returns_active_and_keeps_state(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        log = create_log(self.event.pk)
        mark_signup_sending(self.event.pk, 0, decision.attempt_token, log.pk)
        for state in (SignupDeliveryStatus.SENDING, SignupDeliveryStatus.UNCERTAIN):
            SignupPostDeliveryState.objects.filter(event=self.event).update(state=state)
            self.assertEqual(
                delivery.reset_signup_delivery(self.event.pk),
                (delivery.ResetOutcome.ACTIVE, 0),
            )
            self.assertEqual(
                SignupPostDeliveryState.objects.get(event=self.event).attempts, 1
            )
        log.success = False
        log.save()
        SignupPostDeliveryState.objects.filter(event=self.event).update(
            state=SignupDeliveryStatus.SENDING
        )
        self.assertEqual(
            delivery.reset_signup_delivery(self.event.pk),
            (delivery.ResetOutcome.ACTIVE, 0),
        )

    def test_old_generation_begin_rejected(self) -> None:
        self.assertEqual(
            delivery.reset_signup_delivery(self.event.pk),
            (delivery.ResetOutcome.RESET, 1),
        )
        decision = begin_signup_attempt(self.event.pk, generation=0)
        self.assertEqual(decision.outcome, BeginOutcome.STALE_GENERATION)
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).attempts, 0
        )

    def test_reset_uncertain_starts_fresh_generation(self) -> None:
        decision = begin_signup_attempt(self.event.pk)
        result = delivery.complete_signup_attempt(
            self.event.pk,
            0,
            decision.attempt_token,
            delivery.CompletionKind.UNCERTAIN,
            failure=self.failure,
        )
        self.assertEqual(result.state, SignupDeliveryStatus.UNCERTAIN)
        self.assertEqual(
            delivery.reset_signup_delivery(self.event.pk),
            (delivery.ResetOutcome.RESET, 1),
        )
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual((state.attempts, state.state), (0, SignupDeliveryStatus.READY))
        for field in (
            "attempt_token",
            "reserved_at",
            "active_log_id",
            "next_attempt_at",
            "receipt",
            "last_failure_category",
            "last_failure_status",
            "last_failure_code",
        ):
            self.assertIsNone(getattr(state, field), field)
        self.assertEqual(
            begin_signup_attempt(self.event.pk, generation=0).outcome,
            BeginOutcome.STALE_GENERATION,
        )
        self.assertEqual(
            delivery.complete_signup_attempt(
                self.event.pk,
                0,
                decision.attempt_token,
                delivery.CompletionKind.FAILED,
                failure=self.failure,
            ).outcome,
            "stale",
        )
        self.assertEqual(begin_signup_attempt(self.event.pk, generation=1).attempt, 1)

    def test_reset_clears_legacy_success_gates(self) -> None:
        self.deliver()
        self.assertEqual(
            delivery.reset_signup_delivery(self.event.pk),
            (delivery.ResetOutcome.RESET, 1),
        )
        self.assertFalse(
            DiscordEventMsgSignup.objects.nocache().get(event=self.event).has_posted
        )
        self.assertFalse(
            DiscordMessageLog.objects.nocache().get(source_id=self.event.pk).success
        )
        self.assertEqual(
            begin_signup_attempt(self.event.pk, generation=1).outcome,
            BeginOutcome.RESERVED,
        )

    def test_deleted_message_clear_matches_current_message_only(self) -> None:
        self.deliver()
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, "100000000000000099"
            )
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.DELIVERED,
        )
        self.assertTrue(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )
        state = SignupPostDeliveryState.objects.get(event=self.event)
        self.assertEqual(
            (state.state, state.generation), (SignupDeliveryStatus.READY, 1)
        )
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )

    def test_deleted_clear_missing_message_is_read_only(self) -> None:
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.event).exists()
        )

    def test_deleted_clear_rejects_ambiguous_legacy_messages(self) -> None:
        for channel, message in (
            (CHANNEL, self.receipt.message_id),
            ("100000000000000010", "100000000000000011"),
        ):
            DiscordEventMsgSignup.objects.create(
                event=self.event,
                channel_id=channel,
                message_id=message,
                has_posted=True,
            )
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.event).exists()
        )

    def test_deleted_clear_supports_unlinked_legacy_message(self) -> None:
        msg = DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id=CHANNEL,
            message_id=self.receipt.message_id,
            has_posted=True,
        )
        self.assertTrue(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, msg.message_id
            )
        )
        msg.refresh_from_db()
        self.assertFalse(msg.has_posted)
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).generation, 1
        )

    def test_deleted_message_cannot_clear_active_replacement(self) -> None:
        self.deliver()
        delivery.reset_signup_delivery(self.event.pk)
        begin_signup_attempt(self.event.pk)
        self.assertFalse(
            delivery.clear_signup_state_for_deleted_message(
                self.event.pk, self.receipt.message_id
            )
        )
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.RESERVED,
        )

    def test_blocked_ids_lists_deferred_exhausted_uncertain_active(self) -> None:
        blocked: list[int] = []
        allowed: list[int] = []
        for status, age, cooldown in (
            ("ready", 0, 1),
            ("exhausted", 0, 0),
            ("uncertain", 10, 0),
            ("reserved", 0, 0),
            ("sending", 0, 0),
            ("ready", 0, 0),
            ("reserved", 6, 0),
            ("sending", 6, 0),
            ("delivered", 0, 0),
        ):
            event = create_event()
            SignupPostDeliveryState.objects.create(
                event=event,
                state=status,
                reserved_at=self.now - timedelta(minutes=age),
                next_attempt_at=self.now + timedelta(minutes=cooldown)
                if cooldown
                else None,
            )
            (
                blocked
                if status in ("exhausted", "uncertain")
                or cooldown
                or (status in ("reserved", "sending") and not age)
                else allowed
            ).append(event.pk)
        self.assertCountEqual(
            delivery.blocked_signup_event_ids(iter(blocked + allowed), now=self.now),
            blocked,
        )
        self.assertEqual(delivery.blocked_signup_event_ids([], now=self.now), [])


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
