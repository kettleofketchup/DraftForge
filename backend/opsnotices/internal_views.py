from typing import Any

from pydantic import BaseModel, ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.models import CustomUser, Organization
from events.models import Event
from opsnotices.schemas import EmitNoticeRequest, ResolveNoticeRequest
from opsnotices.services import (
    EventRef,
    NoticeEmitError,
    _emit,
    resolve_notice,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG: dict[str, str] = {"system": "opsnotices", "subsystem": "api"}
_TRANSIENT_CODES: frozenset[str] = frozenset({"database_error", "event_conflict"})


def _error(message: str, code: str, http_status: int) -> Response:
    return Response({"error": message, "code": code}, status=http_status)


def _invalid_request() -> Response:
    return _error("invalid request", "invalid_request", status.HTTP_400_BAD_REQUEST)


def _parse[M: BaseModel](request: Request, schema: type[M]) -> M | None:
    try:
        return schema.model_validate(request.data)
    except (ParseError, ValidationError):
        return None


def _user(field: str, user_id: int | None) -> CustomUser | None:
    if user_id is None:
        return None
    user = CustomUser.objects.filter(pk=user_id).first()
    if user is None:
        log.warning(
            "ops_notice_internal_user_missing", field=field, user_id=user_id, **_LOG
        )
    return user


def _event(body: EmitNoticeRequest) -> Event | EventRef | None:
    if body.event_id is None:
        return None
    event = Event.objects.filter(pk=body.event_id).first()
    if event is not None:
        return event
    return EventRef(
        id=body.event_id,
        name=body.event_name or "",
        event_repeater_id=body.event_repeater_id,
    )


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def emit(request: Request) -> Response:
    body = _parse(request, EmitNoticeRequest)
    if body is None:
        return _invalid_request()
    organization = Organization.objects.filter(pk=body.organization_id).first()
    if organization is None:
        return _error("organization not found", "not_found", status.HTTP_404_NOT_FOUND)
    try:
        notice, outcome = _emit(
            body.key,
            body.payload,
            organization=organization,
            event=_event(body),
            subject_user=_user("subject_user_id", body.subject_user_id),
            actor=_user("actor_id", body.actor_id),
            dedupe_key=body.dedupe_key,
            severity=body.severity,
            emit_id=body.emit_id,
        )
    except NoticeEmitError as exc:
        transient = exc.code in _TRANSIENT_CODES
        (log.error if transient else log.warning)(
            "ops_notice_internal_rejected",
            code=exc.code,
            notice_key=exc.notice_key,
            organization_id=organization.id,
            **_LOG,
        )
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if transient
            else status.HTTP_400_BAD_REQUEST
        )
        return _error("notice rejected", exc.code, http_status)
    created = outcome == "created"
    data: dict[str, Any] = {
        "id": notice.pk,
        "created": created,
        "occurrences": notice.occurrences,
    }
    return Response(
        data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def resolve(request: Request) -> Response:
    body = _parse(request, ResolveNoticeRequest)
    if body is None:
        return _invalid_request()
    organization = Organization.objects.filter(pk=body.organization_id).first()
    if organization is None:
        return _error("organization not found", "not_found", status.HTTP_404_NOT_FOUND)
    event = EventRef(id=body.event_id, name="") if body.event_id else None
    try:
        notice = resolve_notice(
            body.key,
            body.dedupe_key,
            organization=organization,
            event=event,
            reason=body.reason,
        )
    except ValueError:
        return _invalid_request()
    return Response({"id": getattr(notice, "pk", None), "resolved": notice is not None})
