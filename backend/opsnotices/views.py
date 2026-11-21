from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.permissions_tournament import has_event_staff_access
from events.models import Event
from opsnotices.models import OPEN_STATES, OpsNotice
from opsnotices.registry import NoticeCategory
from opsnotices.serializers import OpsNoticeSerializer
from opsnotices.services import CLOSE_NOTE_MAX, resolve_notice_by_id
from org.models import Organization
from org.permissions import has_org_staff_access
from telemetry.logging import get_logger

log = get_logger(__name__)

LIST_LIMIT_DEFAULT: int = 50
LIST_LIMIT_MAX: int = 200
STAFF_RESOLVE_REASON: str = "resolved by staff"
_STATES: dict[str, list[str]] = {
    "open": list(OPEN_STATES),
    "resolved": [OpsNotice.State.RESOLVED.value],
    "all": [choice.value for choice in OpsNotice.State],
}
_CATEGORIES: frozenset[str] = frozenset(c.value for c in NoticeCategory)


def _parse_list_params(request: Request) -> tuple[list[str], list[str] | None, int]:
    params = request.query_params
    state = params.get("state", "open")
    if state not in _STATES:
        raise ValidationError({"state": "must be open, resolved or all"})

    categories: list[str] | None = None
    raw_categories = params.get("category")
    if raw_categories is not None:
        categories = [part.strip() for part in raw_categories.split(",")]
        if not categories or not set(categories) <= _CATEGORIES:
            raise ValidationError({"category": "must be a list of log, urgent, task"})

    raw_limit = params.get("limit")
    limit = LIST_LIMIT_DEFAULT
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except ValueError:
            raise ValidationError({"limit": "must be an integer"}) from None
        if limit < 1:
            raise ValidationError({"limit": "must be at least 1"})
    return _STATES[state], categories, min(limit, LIST_LIMIT_MAX)


def _notices() -> QuerySet[OpsNotice]:
    return OpsNotice.objects.select_related(
        "event", "subject_user__base_profile", "actor__base_profile", "closed_by"
    ).nocache()


def _list(request: Request, notices: QuerySet[OpsNotice]) -> Response:
    states, categories, limit = _parse_list_params(request)
    notices = notices.filter(state__in=states)
    if categories is not None:
        notices = notices.filter(category__in=categories)
    rows = notices.order_by("-last_seen_at", "-id")[:limit]
    return Response(OpsNoticeSerializer(rows, many=True).data)


def _reason(request: Request) -> str:
    data: Any = request.data
    reason = data.get("reason") if isinstance(data, dict) else None
    if reason is None or (isinstance(reason, str) and not reason.strip()):
        return STAFF_RESOLVE_REASON
    if not isinstance(reason, str) or len(reason) > CLOSE_NOTE_MAX:
        raise ValidationError(
            {"reason": f"must be text of at most {CLOSE_NOTE_MAX} characters"}
        )
    return reason


def _resolve(
    request: Request, notices: QuerySet[OpsNotice], notice_id: int
) -> Response:
    notice = get_object_or_404(notices, pk=notice_id)
    if notice.category == NoticeCategory.TASK:
        return Response(
            {"code": "task_resolve_unsupported"}, status=status.HTTP_400_BAD_REQUEST
        )
    reason = _reason(request)
    was_open = notice.closed_at is None
    resolved = resolve_notice_by_id(notice, reason=reason, closed_by=request.user)
    if resolved is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if was_open and resolved.closed_by_id == request.user.pk:
        log.info(
            "ops_notice_staff_resolved",
            system="opsnotices",
            subsystem="api",
            notice_id=resolved.pk,
            user_id=request.user.pk,
        )
    return Response(OpsNoticeSerializer(resolved).data)


def _org(request: Request, org_id: int) -> Organization:
    organization = get_object_or_404(Organization, pk=org_id)
    if not has_org_staff_access(request.user, organization):
        raise PermissionDenied()
    return organization


def _event(request: Request, event_id: int) -> Event:
    event = get_object_or_404(
        Event.objects.select_related("organization", "tournament_league"),
        pk=event_id,
    )
    if not has_event_staff_access(request.user, event):
        raise PermissionDenied()
    return event


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def org_ops_notices(request: Request, org_id: int) -> Response:
    organization = _org(request, org_id)
    return _list(request, _notices().filter(organization=organization))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def event_ops_notices(request: Request, event_id: int) -> Response:
    event = _event(request, event_id)
    return _list(request, _notices().filter(event=event))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def org_ops_notice_resolve(request: Request, org_id: int, notice_id: int) -> Response:
    organization = _org(request, org_id)
    return _resolve(request, _notices().filter(organization=organization), notice_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def event_ops_notice_resolve(
    request: Request, event_id: int, notice_id: int
) -> Response:
    event = _event(request, event_id)
    return _resolve(request, _notices().filter(event=event), notice_id)
