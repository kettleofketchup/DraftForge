from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from discordbot.models import (
    DiscordEventMsgSignup,
    DiscordMessageLog,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)

MAX_AUTOMATIC_ATTEMPTS = 5
BACKOFF_MINUTES: tuple[int, ...] = (1, 2, 4, 8)
STALE_ACTIVE_AFTER = timedelta(minutes=5)


class BeginOutcome(StrEnum):
    RESERVED = "reserved"
    ALREADY_DELIVERED = "already_delivered"
    IN_FLIGHT = "in_flight"
    DEFERRED = "deferred"
    EXHAUSTED = "exhausted"
    UNCERTAIN = "uncertain"
    STALE_GENERATION = "stale_generation"


@dataclass(frozen=True)
class BeginDecision:
    outcome: BeginOutcome
    generation: int
    attempt_token: UUID | None = None
    attempt: int | None = None
    next_attempt_at: datetime | None = None


def begin_signup_attempt(
    event_id: int, generation: int | None = None, *, now: datetime | None = None
) -> BeginDecision:
    now = now if now is not None else timezone.now()
    event_model = SignupPostDeliveryState._meta.get_field("event").related_model
    with transaction.atomic():
        event_model.objects.nocache().select_for_update().get(pk=event_id)
        SignupPostDeliveryState.objects.get_or_create(event_id=event_id)
        state = SignupPostDeliveryState.objects.select_for_update().get(
            event_id=event_id
        )
        if generation is not None and generation != state.generation:
            return BeginDecision(BeginOutcome.STALE_GENERATION, state.generation)

        logs = DiscordMessageLog.objects.nocache().filter(
            source="event_announcement", source_id=event_id
        )
        if (
            state.state == SignupDeliveryStatus.DELIVERED
            or DiscordEventMsgSignup.objects.nocache()
            .filter(event_id=event_id, has_posted=True)
            .exists()
            or logs.filter(success=True).exists()
        ):
            return BeginDecision(BeginOutcome.ALREADY_DELIVERED, state.generation)

        if logs.filter(success__isnull=True).exists():
            return BeginDecision(BeginOutcome.IN_FLIGHT, state.generation)
        if state.state in (SignupDeliveryStatus.RESERVED, SignupDeliveryStatus.SENDING):
            if (
                state.reserved_at is None
                or now - state.reserved_at < STALE_ACTIVE_AFTER
            ):
                return BeginDecision(BeginOutcome.IN_FLIGHT, state.generation)
            if state.state == SignupDeliveryStatus.SENDING:
                state.state = SignupDeliveryStatus.UNCERTAIN
            else:
                state.state = SignupDeliveryStatus.READY
            state.save(update_fields=["state", "updated_at"])
        if state.state == SignupDeliveryStatus.UNCERTAIN:
            return BeginDecision(BeginOutcome.UNCERTAIN, state.generation)
        if (
            state.state == SignupDeliveryStatus.EXHAUSTED
            or state.attempts >= MAX_AUTOMATIC_ATTEMPTS
        ):
            state.state = SignupDeliveryStatus.EXHAUSTED
            state.save(update_fields=["state", "updated_at"])
            return BeginDecision(BeginOutcome.EXHAUSTED, state.generation)
        if state.next_attempt_at is not None and state.next_attempt_at > now:
            return BeginDecision(
                BeginOutcome.DEFERRED,
                state.generation,
                next_attempt_at=state.next_attempt_at,
            )

        state.attempts += 1
        state.state = SignupDeliveryStatus.RESERVED
        state.attempt_token = uuid4()
        state.reserved_at = now
        state.active_log_id = None
        state.next_attempt_at = None
        state.save(
            update_fields=[
                "attempts",
                "state",
                "attempt_token",
                "reserved_at",
                "active_log_id",
                "next_attempt_at",
                "updated_at",
            ]
        )
        return BeginDecision(
            BeginOutcome.RESERVED,
            state.generation,
            attempt_token=state.attempt_token,
            attempt=state.attempts,
        )


def mark_signup_sending(
    event_id: int, generation: int, attempt_token: UUID, log_id: int | None
) -> bool:
    event_model = SignupPostDeliveryState._meta.get_field("event").related_model
    with transaction.atomic():
        event_model.objects.nocache().select_for_update().get(pk=event_id)
        state = (
            SignupPostDeliveryState.objects.select_for_update()
            .filter(
                event_id=event_id, generation=generation, attempt_token=attempt_token
            )
            .first()
        )
        if state is None or log_id is None:
            return False
        logs = (
            DiscordMessageLog.objects.nocache()
            .select_for_update()
            .filter(source="event_announcement", source_id=event_id)
        )
        if not logs.filter(pk=log_id, success__isnull=True).exists():
            return False
        if state.state == SignupDeliveryStatus.SENDING:
            if not logs.filter(pk=state.active_log_id, success=False).exists():
                return False
        elif state.state != SignupDeliveryStatus.RESERVED:
            return False
        return bool(
            SignupPostDeliveryState.objects.filter(
                pk=state.pk,
                generation=generation,
                attempt_token=attempt_token,
                state=state.state,
                active_log_id=state.active_log_id,
            ).update(
                state=SignupDeliveryStatus.SENDING,
                active_log_id=log_id,
                updated_at=timezone.now(),
            )
        )
