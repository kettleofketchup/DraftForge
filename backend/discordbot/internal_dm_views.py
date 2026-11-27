"""Internal API for the DM ledger: claim, mark sending, finalize, record clicks.

Thin wrappers around ``discordbot.dm_ledger``. Responses never carry Discord
channel or message ids.
"""

from django.utils import timezone
from pydantic import BaseModel, ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot import dm_ledger
from discordbot.internal_signup_views import _bind_interaction
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import (
    DMClaimBody,
    DMClickBody,
    DMFinalizeBody,
    DMSendingBody,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]
_LOG = {"system": "discord", "subsystem": "dm"}


def _invalid() -> Response:
    return Response({"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)


def _claim(body: DMClaimBody) -> dm_ledger.DMClaim:
    return dm_ledger.DMClaim(
        kind=DMKind(body.kind),
        idempotency_key=body.idempotency_key,
        claim_token=body.claim_token,
        discord_user_id=body.discord_user_id,
        recipient_user_id=body.recipient_user_id,
        organization_id=body.organization_id,
        subject_type=DMSubject(body.subject_type) if body.subject_type else None,
        subject_id=body.subject_id,
        tournament_log_id=body.tournament_log_id,
        context=body.context,
        has_components=body.has_components,
        initial_status=DMStatus(body.initial_status) if body.initial_status else None,
    )


def _final(body: DMFinalizeBody) -> dm_ledger.DMFinal:
    return dm_ledger.DMFinal(
        status=DMStatus(body.status),
        error_class=body.error_class,
        discord_channel_id=body.discord_channel_id,
        discord_message_id=body.discord_message_id,
        http_status=body.http_status,
        error_code=body.error_code,
        error=body.error,
    )


def _parse[T: BaseModel](schema: type[T], request: Request) -> T | None:
    try:
        return schema.model_validate(request.data)
    except ValidationError:
        return None


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def dm_claim(request: Request) -> Response:
    _bind_interaction(request)
    body = _parse(DMClaimBody, request)
    if body is None:
        return _invalid()
    try:
        result = dm_ledger.claim(_claim(body), now=timezone.now())
    except ValueError:
        log.warning("dm_claim_rejected", **_LOG, dm_kind=body.kind)
        return _invalid()
    if not result.granted:
        return Response(
            {"id": result.id, "status": result.status.value},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(
        {"id": result.id, "status": result.status.value, "attempts": result.attempts},
        status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def dm_sending(request: Request, dm_id: int) -> Response:
    _bind_interaction(request)
    body = _parse(DMSendingBody, request)
    if body is None:
        return _invalid()
    if dm_ledger.mark_sending(dm_id, claim_token=body.claim_token, now=timezone.now()):
        return Response(status=status.HTTP_204_NO_CONTENT)
    log.warning("dm_sending_refused", **_LOG, ledger_id=dm_id)
    return Response({"error": "conflict"}, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def dm_finalize(request: Request, dm_id: int) -> Response:
    _bind_interaction(request)
    body = _parse(DMFinalizeBody, request)
    if body is None:
        return _invalid()
    try:
        row = dm_ledger.finalize(
            dm_id, _final(body), claim_token=body.claim_token, now=timezone.now()
        )
    except ValueError:
        return _invalid()
    except dm_ledger.LedgerNotFound:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    except dm_ledger.LedgerConflict:
        log.warning("dm_finalize_refused", **_LOG, ledger_id=dm_id, status=body.status)
        return Response({"error": "conflict"}, status=status.HTTP_409_CONFLICT)
    return Response({"id": row.pk, "status": row.status})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def dm_click(request: Request) -> Response:
    _bind_interaction(request)
    body = _parse(DMClickBody, request)
    if body is None:
        return _invalid()
    dm_ledger.record_click(
        discord_message_id=body.discord_message_id,
        discord_user_id=body.discord_user_id,
        now=timezone.now(),
    )
    return Response(status=status.HTTP_204_NO_CONTENT)
