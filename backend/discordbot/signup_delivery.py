from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Model, Q, QuerySet
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from discordbot.delivery_types import DeliveryFailure, DeliveryReceipt
from discordbot.models import (
    DiscordEvent,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)

MAX_AUTOMATIC_ATTEMPTS = 5
BACKOFF_MINUTES: tuple[int, ...] = (1, 2, 4, 8)
STALE_ACTIVE_AFTER = timedelta(minutes=5)
SIGNUP_SOURCE = "event_announcement"


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


class CompletionKind(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class CompletionReply:
    outcome: Literal["recorded", "idempotent", "stale"]
    persisted: bool
    next_attempt_at: datetime | None
    state: str


class ResetOutcome(StrEnum):
    RESET = "reset"
    ACTIVE = "active"


def _event_model() -> type[Model]:
    return SignupPostDeliveryState._meta.get_field("event").related_model


def _lock_state(event_id: int) -> SignupPostDeliveryState | None:
    _event_model().objects.nocache().select_for_update().get(pk=event_id)
    return (
        SignupPostDeliveryState.objects.select_for_update()
        .filter(event_id=event_id)
        .first()
    )


def _reply(
    state: SignupPostDeliveryState,
    outcome: Literal["recorded", "idempotent", "stale"],
    persisted: bool,
) -> CompletionReply:
    return CompletionReply(outcome, persisted, state.next_attempt_at, state.state)


def _stale(state: SignupPostDeliveryState | None) -> CompletionReply:
    if state is None:
        return CompletionReply("stale", False, None, SignupDeliveryStatus.READY)
    return _reply(state, "stale", False)


def _is_fresh_active(state: SignupPostDeliveryState, now: datetime) -> bool:
    return state.state in (
        SignupDeliveryStatus.RESERVED,
        SignupDeliveryStatus.SENDING,
    ) and (state.reserved_at is None or now - state.reserved_at < STALE_ACTIVE_AFTER)


def _owned_logs(event_id: int) -> QuerySet[DiscordMessageLog]:
    return DiscordMessageLog.objects.nocache().filter(
        source=SIGNUP_SOURCE, source_id=event_id
    )


def _record_failure(
    state: SignupPostDeliveryState, failure: DeliveryFailure | None
) -> None:
    state.last_failure_category = failure.category.value if failure else None
    state.last_failure_status = failure.status if failure else None
    state.last_failure_code = failure.code if failure else None


def _finalize_failed_log(
    log: DiscordMessageLog | None, failure: DeliveryFailure | None
) -> None:
    if log is None or log.success is not None:
        return
    log.success = False
    if failure is not None:
        log.status_code = failure.status
        log.response_data = failure.safe_json()
    log.save(update_fields=["success", "status_code", "response_data"])
    invalidate_after_commit(log)


def _persist_delivery(
    event_id: int, receipt: DeliveryReceipt, log: DiscordMessageLog, now: datetime
) -> None:
    log.success = True
    log.discord_message_id = receipt.message_id
    log.response_data = (
        {"id": receipt.thread_id, "message": {"id": receipt.message_id}}
        if receipt.thread_id is not None
        else {"id": receipt.message_id}
    )
    log.save(update_fields=["success", "discord_message_id", "response_data"])
    msg, _ = DiscordEventMsgSignup.objects.nocache().get_or_create(
        event_id=event_id, channel_id=receipt.parent_channel_id
    )
    msg.message_id = receipt.message_id
    msg.thread_id = receipt.thread_id
    msg.channel_type = receipt.storage_channel_type()
    msg.has_posted = True
    msg.message_last_updated = now
    msg.save()
    event = (
        _event_model().objects.nocache().select_related("organization").get(pk=event_id)
    )
    discord_event, _ = DiscordEvent.objects.nocache().get_or_create(
        event_id=event_id,
        defaults={"guild_id": event.organization.discord_server_id or ""},
    )
    discord_event.signup_message = msg
    discord_event.save(update_fields=["signup_message", "updated_at"])
    invalidate_after_commit(log, msg, discord_event)


def complete_signup_attempt(
    event_id: int,
    generation: int,
    attempt_token: UUID,
    kind: CompletionKind,
    *,
    receipt: DeliveryReceipt | None = None,
    failure: DeliveryFailure | None = None,
    log_id: int | None = None,
    now: datetime | None = None,
) -> CompletionReply:
    now = now if now is not None else timezone.now()
    kind = CompletionKind(kind)
    with transaction.atomic():
        state = _lock_state(event_id)
        if (
            state is None
            or state.generation != generation
            or state.attempt_token != attempt_token
        ):
            return _stale(state)
        if kind == CompletionKind.DELIVERED:
            if receipt is None:
                raise ValueError("Delivered completion requires a receipt")
            receipt = DeliveryReceipt.from_json(receipt.to_json())
        if log_id is not None and log_id != state.active_log_id:
            return _stale(state)
        log: DiscordMessageLog | None = None
        if state.active_log_id is not None:
            log = (
                _owned_logs(event_id)
                .select_for_update()
                .filter(pk=state.active_log_id)
                .first()
            )
            if log is None or (
                log.success is True and kind != CompletionKind.DELIVERED
            ):
                return _stale(state)

        if kind == CompletionKind.DELIVERED:
            if state.state == SignupDeliveryStatus.DELIVERED:
                same = state.receipt == receipt.to_json()
                return _reply(state, "idempotent" if same else "stale", same)
            if (
                state.state
                not in (SignupDeliveryStatus.SENDING, SignupDeliveryStatus.UNCERTAIN)
                or log is None
                or log.success is False
                or log.channel_id != receipt.parent_channel_id
            ):
                return _stale(state)
            _persist_delivery(event_id, receipt, log, now)
            state.state = SignupDeliveryStatus.DELIVERED
            state.receipt = receipt.to_json()
            state.next_attempt_at = None
            _record_failure(state, None)
            state.save()
            return _reply(state, "recorded", True)

        if kind == CompletionKind.UNCERTAIN:
            if state.state == SignupDeliveryStatus.UNCERTAIN:
                return _reply(state, "idempotent", True)
            if state.state not in (
                SignupDeliveryStatus.RESERVED,
                SignupDeliveryStatus.SENDING,
            ):
                return _stale(state)
            state.state = SignupDeliveryStatus.UNCERTAIN
            _record_failure(state, failure)
            state.save()
            return _reply(state, "recorded", True)

        if (
            state.state
            not in (
                SignupDeliveryStatus.RESERVED,
                SignupDeliveryStatus.SENDING,
            )
            or state.attempts < 1
        ):
            return _stale(state)
        _finalize_failed_log(log, failure)
        _record_failure(state, failure)
        if state.attempts >= MAX_AUTOMATIC_ATTEMPTS:
            state.state = SignupDeliveryStatus.EXHAUSTED
            state.next_attempt_at = None
        elif 1 <= state.attempts <= len(BACKOFF_MINUTES):
            state.state = SignupDeliveryStatus.READY
            state.next_attempt_at = now + timedelta(
                minutes=BACKOFF_MINUTES[state.attempts - 1]
            )
        else:
            state.state = SignupDeliveryStatus.EXHAUSTED
            state.next_attempt_at = None
        state.save()
        return _reply(state, "recorded", True)


def clear_signup_success_gates(event_id: int) -> dict[str, int]:
    """Flip the signup-posted and successful-log dedup gates for an event.

    `.update()` bypasses cacheops, so cached rows are invalidated after commit.
    """
    affected_signups = list(
        DiscordEventMsgSignup.objects.nocache().filter(
            event_id=event_id, has_posted=True
        )
    )
    DiscordEventMsgSignup.objects.filter(
        pk__in=[row.pk for row in affected_signups]
    ).update(has_posted=False)
    for row in affected_signups:
        row.refresh_from_db()
        invalidate_after_commit(row)

    affected_logs = list(_owned_logs(event_id).filter(success=True))
    message_log_rows_cleared = DiscordMessageLog.objects.filter(
        pk__in=[row.pk for row in affected_logs]
    ).update(success=False)
    for row in affected_logs:
        row.refresh_from_db()
        invalidate_after_commit(row)

    return {
        "signup_rows_cleared": len(affected_signups),
        "message_log_rows_cleared": message_log_rows_cleared,
    }


def _reset_state(state: SignupPostDeliveryState) -> None:
    state.generation += 1
    state.attempts = 0
    state.state = SignupDeliveryStatus.READY
    state.attempt_token = None
    state.reserved_at = None
    state.active_log_id = None
    state.next_attempt_at = None
    state.receipt = None
    _record_failure(state, None)
    state.save()


def reset_signup_delivery(event_id: int) -> tuple[ResetOutcome, int]:
    now = timezone.now()
    with transaction.atomic():
        _event_model().objects.nocache().select_for_update().get(pk=event_id)
        SignupPostDeliveryState.objects.get_or_create(event_id=event_id)
        state = SignupPostDeliveryState.objects.select_for_update().get(
            event_id=event_id
        )
        if (
            _is_fresh_active(state, now)
            or _owned_logs(event_id).filter(success__isnull=True).exists()
        ):
            return ResetOutcome.ACTIVE, state.generation
        _reset_state(state)
        clear_signup_success_gates(event_id)
        return ResetOutcome.RESET, state.generation


def _current_signup_message_ids(event_id: int) -> set[str]:
    linked = (
        DiscordEvent.objects.nocache()
        .filter(event_id=event_id, signup_message__isnull=False)
        .values_list("signup_message__message_id", "signup_message__has_posted")
        .first()
    )
    if linked is not None:
        message_id, has_posted = linked
        return {message_id} if has_posted and message_id else set()
    posted = list(
        DiscordEventMsgSignup.objects.nocache()
        .filter(event_id=event_id, has_posted=True)
        .values_list("message_id", flat=True)[:2]
    )
    return {posted[0]} if len(posted) == 1 and posted[0] else set()


def clear_signup_state_for_deleted_message(event_id: int, message_id: str) -> bool:
    with transaction.atomic():
        state = _lock_state(event_id)
        if (
            message_id not in _current_signup_message_ids(event_id)
            or (state is not None and _is_fresh_active(state, timezone.now()))
            or _owned_logs(event_id).filter(success__isnull=True).exists()
        ):
            return False
        if state is None:
            SignupPostDeliveryState.objects.create(event_id=event_id)
            state = SignupPostDeliveryState.objects.select_for_update().get(
                event_id=event_id
            )
        _reset_state(state)
        clear_signup_success_gates(event_id)
        return True


def blocked_signup_event_ids(
    event_ids: Iterable[int], *, now: datetime | None = None
) -> list[int]:
    ids = list(event_ids)
    if not ids:
        return []
    now = now if now is not None else timezone.now()
    fresh_since = now - STALE_ACTIVE_AFTER
    return list(
        SignupPostDeliveryState.objects.filter(event_id__in=ids)
        .filter(
            Q(state=SignupDeliveryStatus.READY, next_attempt_at__gt=now)
            | Q(
                state__in=(
                    SignupDeliveryStatus.EXHAUSTED,
                    SignupDeliveryStatus.UNCERTAIN,
                )
            )
            | Q(
                state__in=(
                    SignupDeliveryStatus.RESERVED,
                    SignupDeliveryStatus.SENDING,
                )
            )
            & (Q(reserved_at__isnull=True) | Q(reserved_at__gt=fresh_since))
        )
        .values_list("event_id", flat=True)
    )
