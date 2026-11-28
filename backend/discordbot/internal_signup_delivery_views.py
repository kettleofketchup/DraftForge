"""Internal API endpoints fencing signup post delivery attempts.

Thin wrappers around ``discordbot.signup_delivery``: auth, pydantic validation,
delegation. Attempt tokens are never logged.
"""

from django.core.exceptions import ObjectDoesNotExist
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot.delivery_types import valid_discord_id
from discordbot.schemas import (
    SignupDeliveryBeginReply,
    SignupDeliveryBeginRequest,
    SignupDeliveryBlockedReply,
    SignupDeliveryCompleteReply,
    SignupDeliveryCompleteRequest,
    SignupDeliverySendingReply,
    SignupDeliverySendingRequest,
)
from discordbot.signup_delivery import (
    BeginDecision,
    CompletionKind,
    CompletionReply,
    begin_signup_attempt,
    blocked_signup_event_ids,
    complete_signup_attempt,
    mark_signup_sending,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]
_LOG = {
    "system": "discord",
    "subsystem": "dispatch",
    "tags": ["events", "signup"],
    "tags_csv": "events,signup",
}


def _bad_request() -> Response:
    return Response(
        {"error": "invalid_request"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _not_found() -> Response:
    return Response({"error": "event_not_found"}, status=status.HTTP_404_NOT_FOUND)


def begin_reply(decision: BeginDecision) -> SignupDeliveryBeginReply:
    return SignupDeliveryBeginReply(
        outcome=decision.outcome.value,
        generation=decision.generation,
        attempt_token=(
            str(decision.attempt_token) if decision.attempt_token is not None else None
        ),
        attempt=decision.attempt,
        next_attempt_at=decision.next_attempt_at,
    )


def complete_reply(reply: CompletionReply) -> SignupDeliveryCompleteReply:
    return SignupDeliveryCompleteReply(
        outcome=reply.outcome,
        persisted=reply.persisted,
        next_attempt_at=reply.next_attempt_at,
        state=str(reply.state),
    )


def run_complete(body: SignupDeliveryCompleteRequest) -> CompletionReply:
    return complete_signup_attempt(
        body.event_id,
        body.generation,
        body.attempt_token,
        CompletionKind(body.outcome),
        receipt=body.receipt.to_receipt() if body.receipt is not None else None,
        failure=body.failure.to_failure() if body.failure is not None else None,
        log_id=body.log_id,
    )


def parse_event_ids(raw: str) -> list[int]:
    if not raw:
        return []
    parts = raw.split(",")
    if not all(valid_discord_id(part) and len(part) <= 19 for part in parts):
        raise ValueError("invalid event_ids")
    event_ids = [int(part) for part in parts]
    if any(event_id > 2**63 - 1 for event_id in event_ids):
        raise ValueError("invalid event_ids")
    return event_ids


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def begin_signup_delivery(request: Request) -> Response:
    try:
        body = SignupDeliveryBeginRequest.model_validate(request.data)
    except ValidationError:
        return _bad_request()
    try:
        decision = begin_signup_attempt(body.event_id, body.generation)
    except ObjectDoesNotExist:
        return _not_found()
    log.info(
        "signup_delivery_begin",
        **_LOG,
        event_id=body.event_id,
        outcome=decision.outcome.value,
        generation=decision.generation,
        attempt=decision.attempt,
    )
    return Response(begin_reply(decision).model_dump(mode="json"))


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def mark_signup_delivery_sending(request: Request) -> Response:
    try:
        body = SignupDeliverySendingRequest.model_validate(request.data)
    except ValidationError:
        return _bad_request()
    try:
        ok = mark_signup_sending(
            body.event_id, body.generation, body.attempt_token, body.log_id
        )
    except ObjectDoesNotExist:
        return _not_found()
    reply = SignupDeliverySendingReply(outcome="ok" if ok else "stale")
    log.info(
        "signup_delivery_sending",
        **_LOG,
        event_id=body.event_id,
        generation=body.generation,
        log_id=body.log_id,
        outcome=reply.outcome,
    )
    return Response(reply.model_dump(mode="json"))


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def complete_signup_delivery(request: Request) -> Response:
    try:
        body = SignupDeliveryCompleteRequest.model_validate(request.data)
        reply = run_complete(body)
    except ObjectDoesNotExist:
        return _not_found()
    except (ValidationError, ValueError):
        return _bad_request()
    log.info(
        "signup_delivery_completed",
        **_LOG,
        event_id=body.event_id,
        generation=body.generation,
        kind=body.outcome,
        outcome=reply.outcome,
        persisted=reply.persisted,
        state=str(reply.state),
        **(body.failure.to_failure().log_fields() if body.failure else {}),
    )
    return Response(complete_reply(reply).model_dump(mode="json"))


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def signup_delivery_blocked(request: Request) -> Response:
    try:
        event_ids = parse_event_ids(request.query_params.get("event_ids", ""))
    except ValueError:
        return _bad_request()
    reply = SignupDeliveryBlockedReply(
        event_ids=sorted(blocked_signup_event_ids(event_ids))
    )
    return Response(reply.model_dump(mode="json"))
