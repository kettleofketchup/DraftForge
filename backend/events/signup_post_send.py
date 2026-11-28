from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as tz
from enum import StrEnum
from typing import Literal

from app import internal_client
from app.internal_client import InternalAPIUnavailable
from discordbot.delivery_types import (
    DeliveryFailure,
    DeliveryReceipt,
    FailureCategory,
    FailurePhase,
    SendOutcome,
    SendResult,
)
from discordbot.utils import send_to_configured_channel
from events.discord.embeds import build_announcement_notice, build_announcement_v2
from events.discord.gates import announcement_branch, signup_post_gate
from events.schemas import EventTaskSchema
from telemetry.logging import get_logger

log = get_logger(__name__)

SIGNUP_SOURCE = "event_announcement"

Destination = Literal["signup", "announcement"]


class SignupRunOutcome(StrEnum):
    DELIVERED = "delivered"
    ALREADY_DELIVERED = "already_delivered"
    IN_FLIGHT = "in_flight"
    DEFERRED = "deferred"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"
    STALE_GENERATION = "stale_generation"


@dataclass(frozen=True)
class SignupPostResult:
    outcome: SignupRunOutcome
    event_id: int
    destination: Destination | None = None
    persisted: bool = False
    notice: SendOutcome | None = None
    failure: DeliveryFailure | None = None

    def newly_delivered(self) -> bool:
        return self.outcome == SignupRunOutcome.DELIVERED

    def summary(self) -> str:
        parts = [f"Signup post for event {self.event_id}: {self.outcome.value}"]
        if self.destination is not None:
            parts.append(f"destination={self.destination}")
        if self.outcome == SignupRunOutcome.DELIVERED and not self.persisted:
            parts.append("unrecorded")
        if self.notice is not None:
            parts.append(f"notice={self.notice.value}")
        if self.failure is not None:
            parts.append(f"phase={self.failure.phase.value}")
            parts.append(f"category={self.failure.category.value}")
            if self.failure.status is not None:
                parts.append(f"status={self.failure.status}")
        return " ".join(parts)


_BEGIN_OUTCOMES: dict[str, SignupRunOutcome] = {
    "already_delivered": SignupRunOutcome.ALREADY_DELIVERED,
    "in_flight": SignupRunOutcome.IN_FLIGHT,
    "deferred": SignupRunOutcome.DEFERRED,
    "exhausted": SignupRunOutcome.EXHAUSTED,
    "uncertain": SignupRunOutcome.UNCERTAIN,
    "stale_generation": SignupRunOutcome.STALE_GENERATION,
}

_SEND_OUTCOMES: dict[SendOutcome, SignupRunOutcome] = {
    SendOutcome.ALREADY_SENT: SignupRunOutcome.ALREADY_DELIVERED,
    SendOutcome.IN_FLIGHT: SignupRunOutcome.IN_FLIGHT,
    SendOutcome.UNAVAILABLE: SignupRunOutcome.UNAVAILABLE,
}


def _finish(
    result: SignupPostResult, *, manual: bool, attempt: int | None = None
) -> SignupPostResult:
    failure_fields = result.failure.log_fields() if result.failure else {}
    log.info(
        "signup_post_outcome",
        system="events",
        subsystem="discord",
        event_id=result.event_id,
        outcome=result.outcome.value,
        destination=result.destination,
        persisted=result.persisted,
        notice=result.notice.value if result.notice else None,
        manual=manual,
        attempt=attempt,
        **failure_fields,
    )
    return result


def _message_link(guild_id: str, receipt: DeliveryReceipt) -> str | None:
    if not guild_id:
        return None
    channel = receipt.thread_id or receipt.parent_channel_id
    return f"https://discord.com/channels/{guild_id}/{channel}/{receipt.message_id}"


def _complete_delivery(
    event_id: int,
    generation: int,
    token: str,
    receipt: DeliveryReceipt,
    log_id: int | None,
) -> bool:
    for _ in range(2):
        reply = internal_client.complete_signup_delivery(
            event_id=event_id,
            generation=generation,
            attempt_token=token,
            outcome="delivered",
            receipt=receipt.to_json(),
            log_id=log_id,
        )
        if reply is not None and reply.persisted:
            return True
    log.error(
        "signup_post_delivered_unrecorded",
        system="events",
        subsystem="discord",
        event_id=event_id,
        message_log_id=log_id,
    )
    return False


def _discord_event_pk(event_id: int, guild_id: str) -> int | None:
    response = internal_client.get_or_create_discord_event(
        event_id=event_id, guild_id=guild_id
    )
    if not response or not response.ok:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    pk = data.get("id") if isinstance(data, dict) else None
    if isinstance(pk, bool) or not isinstance(pk, int) or pk < 1:
        return None
    return pk


def _record_signup_action(
    event_id: int, discord_event_pk: int, receipt: DeliveryReceipt
) -> None:
    try:
        internal_client.create_event_log(
            discord_event_id=discord_event_pk,
            action="send_signup_post",
            target_type="DiscordEventMsgSignup",
            message_id=receipt.message_id,
            success=True,
        )
    except Exception as exc:
        log.warning(
            "signup_post_action_log_failed",
            system="events",
            subsystem="discord",
            event_id=event_id,
            error_type=type(exc).__name__,
        )


def _built_payload(event: EventTaskSchema) -> dict | None:
    try:
        built = build_announcement_v2(event)
    except InternalAPIUnavailable:
        log.warning(
            "signup_list_unavailable",
            system="discord",
            subsystem="celery",
            tags=["events", "signup"],
            tags_csv="events,signup",
            task="send_event_announcement",
            event_id=event.pk,
        )
        return None
    except Exception as exc:
        log.error(
            "signup_post_build_failed",
            system="events",
            subsystem="discord",
            event_id=event.pk,
            error_type=type(exc).__name__,
        )
        return None
    if not (
        isinstance(built, dict)
        and isinstance(built.get("embeds"), list)
        and built["embeds"]
        and isinstance(built.get("components"), list)
    ):
        log.error(
            "signup_post_build_failed",
            system="events",
            subsystem="discord",
            event_id=event.pk,
            error_type="invalid_payload",
        )
        return None
    return built


def _send_notice(
    event: EventTaskSchema,
    guild_id: str,
    title: str,
    receipt: DeliveryReceipt,
    discord_event_pk: int,
    fired_by_user_id: int | None,
) -> SendOutcome:
    notice = build_announcement_notice(event, _message_link(guild_id, receipt))
    delivery = send_to_configured_channel(
        channel_id=event.discord_announcement_channel_id,
        expected_guild_id=guild_id,
        title=title,
        embed=notice["embed"],
        source="event_notice",
        source_id=event.pk,
        content=notice.get("content"),
        allowed_mentions=notice.get("allowed_mentions"),
        fired_by_user_id=fired_by_user_id,
    )
    if delivery.receipt is None:
        return delivery.outcome
    message_id = delivery.receipt.message_id
    ann_resp = internal_client.create_or_update_announcement(
        event_id=event.pk,
        channel_id=event.discord_announcement_channel_id,
        has_posted=True,
        message_id=message_id,
        message_last_updated=datetime.now(tz.utc).isoformat(),
    )
    ann_pk = ann_resp.json().get("id") if ann_resp and ann_resp.ok else None
    if ann_pk:
        internal_client.update_discord_event(discord_event_pk, announcement_id=ann_pk)
        internal_client.create_event_log(
            discord_event_id=discord_event_pk,
            action="send_announcement_notice",
            target_type="DiscordEventMsgAnnouncement",
            message_id=message_id,
            success=True,
        )
    return delivery.outcome


def run_signup_post(
    event_id: int,
    *,
    generation: int | None = None,
    manual: bool = False,
    fired_by_user_id: int | None = None,
) -> SignupPostResult:
    def done(result: SignupPostResult, attempt: int | None = None) -> SignupPostResult:
        return _finish(result, manual=manual, attempt=attempt)

    try:
        event = internal_client.get_event_for_task(event_id)
    except (ValueError, InternalAPIUnavailable):
        return done(SignupPostResult(SignupRunOutcome.UNAVAILABLE, event_id))
    if not event or "state_not_signups_open" in signup_post_gate(event).reasons:
        return done(SignupPostResult(SignupRunOutcome.SKIPPED, event_id))
    branch = announcement_branch(event)
    if branch == "none":
        return done(SignupPostResult(SignupRunOutcome.SKIPPED, event_id))
    signup_available = branch in ("signup_post_only", "signup_post_and_notice")
    announcement_available = branch in (
        "signup_post_and_notice",
        "fallback_signup_post",
    )

    built = _built_payload(event)
    if built is None:
        return done(SignupPostResult(SignupRunOutcome.UNAVAILABLE, event_id))
    guild_id = event.organization.discord_server_id or ""
    title = event.discord_event_title or event.name

    discord_event_pk = _discord_event_pk(event.pk, guild_id)
    if discord_event_pk is None:
        return done(SignupPostResult(SignupRunOutcome.UNAVAILABLE, event_id))

    begin = internal_client.begin_signup_delivery(event_id, generation)
    if begin is None:
        return done(SignupPostResult(SignupRunOutcome.UNAVAILABLE, event_id))
    if begin.outcome != "reserved" or begin.attempt_token is None:
        return done(SignupPostResult(_BEGIN_OUTCOMES[begin.outcome], event_id))
    token = begin.attempt_token
    current_generation = begin.generation
    active_log_id: int | None = None

    def before_post(log_id: int) -> bool:
        nonlocal active_log_id
        marked = internal_client.mark_signup_delivery_sending(
            event_id, current_generation, token, log_id
        )
        if marked:
            active_log_id = log_id
        return marked

    def send(channel_id: str) -> SendResult:
        return send_to_configured_channel(
            channel_id=channel_id,
            expected_guild_id=guild_id,
            embed=built["embeds"],
            components=built["components"],
            title=title,
            source=SIGNUP_SOURCE,
            source_id=event_id,
            content=built.get("content") if destination == "signup" else None,
            allowed_mentions=(
                built.get("allowed_mentions") if destination == "signup" else None
            ),
            fired_by_user_id=fired_by_user_id,
            before_post=before_post,
            defer_success_finalization=True,
            create_max_retries=1,
        )

    destination: Destination = "signup" if signup_available else "announcement"
    primary_channel = (
        event.discord_post_signups_channel_id
        if signup_available
        else event.discord_announcement_channel_id
    )
    sent = send(primary_channel)
    if (
        sent.outcome == SendOutcome.FAILED
        and sent.fallback_safe
        and destination == "signup"
        and announcement_available
        and event.discord_announcement_channel_id != primary_channel
    ):
        destination = "announcement"
        sent = send(event.discord_announcement_channel_id)

    def result(outcome: SignupRunOutcome, **fields: object) -> SignupPostResult:
        return done(
            SignupPostResult(
                outcome,
                event_id,
                destination=destination,
                failure=sent.failure,
                **fields,
            ),
            begin.attempt,
        )

    if sent.outcome == SendOutcome.DELIVERED and sent.receipt is not None:
        persisted = _complete_delivery(
            event_id, current_generation, token, sent.receipt, sent.message_log_id
        )
        if persisted:
            _record_signup_action(event_id, discord_event_pk, sent.receipt)
        notice = None
        if destination == "signup" and announcement_available:
            try:
                notice = _send_notice(
                    event,
                    guild_id,
                    title,
                    sent.receipt,
                    discord_event_pk,
                    fired_by_user_id,
                )
            except Exception as exc:
                log.error(
                    "signup_notice_failed",
                    system="events",
                    subsystem="discord",
                    event_id=event_id,
                    error_type=type(exc).__name__,
                )
                notice = SendOutcome.FAILED
        return result(SignupRunOutcome.DELIVERED, persisted=persisted, notice=notice)

    if sent.outcome == SendOutcome.FAILED:
        if not sent.fallback_safe:
            return result(SignupRunOutcome.UNAVAILABLE)
        failure = sent.failure or DeliveryFailure(
            FailurePhase.CREATE, FailureCategory.HTTP_ERROR
        )
        reply = internal_client.complete_signup_delivery(
            event_id=event_id,
            generation=current_generation,
            attempt_token=token,
            outcome="failed",
            failure=failure.safe_json(),
            log_id=active_log_id,
        )
        return result(
            SignupRunOutcome.FAILED, persisted=reply is not None and reply.persisted
        )

    if sent.outcome == SendOutcome.UNCERTAIN:
        reply = internal_client.complete_signup_delivery(
            event_id=event_id,
            generation=current_generation,
            attempt_token=token,
            outcome="uncertain",
            failure=sent.failure.safe_json() if sent.failure else None,
            log_id=active_log_id,
        )
        return result(
            SignupRunOutcome.UNCERTAIN, persisted=reply is not None and reply.persisted
        )

    return result(_SEND_OUTCOMES.get(sent.outcome, SignupRunOutcome.UNAVAILABLE))
