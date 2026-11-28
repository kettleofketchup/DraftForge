import csv
import io
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

from django.db.models import Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from app.auth import InternalServiceAuth, IsInternalService
from events.history import (
    CURSOR_MESSAGE,
    HISTORY_MAX_PAGE_SIZE,
    HISTORY_PAGE_SIZE,
    MAX_DB_INT,
    LedgerCursor,
    decode_ledger_cursor,
)
from events.ledger import (
    LedgerEvent,
    RecordsWindow,
    purge_expired,
    resolve_ledger_events,
)
from events.models import SignupLedgerEntry
from events.records import (
    RECORD_COLUMNS,
    RecordsFilter,
    SignupRecord,
    TooManyRecords,
    build_signup_records,
    flatten_record,
    guard_csv_cell,
    record_to_json,
)
from events.serializers import OrgSignupLedgerEntrySerializer
from org.display_names import guild_nicknames
from org.feature_errors import require_org_staff
from org.models import Organization
from org.standing.api import local_day_start_utc
from telemetry.logging import get_logger
from tournament.listing import build_cursor_envelope

log = get_logger(__name__)

TOO_MANY_RECORDS_BODY: dict[str, str] = {
    "detail": "Too many records; narrow the date range.",
    "code": "too_many_records",
}


class SignupRecordsThrottle(UserRateThrottle):
    scope = "signup_records"
    rate = "10/min"


class SignupRecordsCSVRenderer(BaseRenderer):
    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> str:
        records: list[SignupRecord] = (renderer_context or {})["signup_records"]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(RECORD_COLUMNS)
        for record in records:
            writer.writerow([guard_csv_cell(v) for v in flatten_record(record)])
        return out.getvalue()


class JSONErrorsMixin(APIView):
    def finalize_response(
        self, request: Request, response: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if response.status_code >= 400:
            request.accepted_renderer = JSONRenderer()
            request.accepted_media_type = "application/json"
        return super().finalize_response(request, response, *args, **kwargs)


def _bounded_int(text: str, low: int, high: int) -> int | None:
    try:
        value = int(text)
    except ValueError:
        return None
    return value if low <= value <= high else None


def _parse_bound(text: str, org: Organization) -> datetime | None:
    try:
        return local_day_start_utc(org, date.fromisoformat(text))
    except ValueError:
        pass
    except OverflowError:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        return None
    try:
        return value.astimezone(UTC)
    except OverflowError:
        return None


def _records_params(
    params: QueryDict, org: Organization
) -> tuple[RecordsFilter | None, dict[str, list[str]]]:
    errors: dict[str, list[str]] = {}
    bounds: dict[str, datetime | None] = {"since": None, "until": None}
    for name in bounds:
        if text := params.get(name):
            bounds[name] = _parse_bound(text, org)
            if bounds[name] is None:
                errors[name] = ["Use an ISO date or a datetime with a UTC offset."]
    ints: dict[str, int | None] = {"series": None, "event": None, "user": None}
    for name in ints:
        if text := params.get(name):
            ints[name] = _bounded_int(text, 1, MAX_DB_INT)
            if ints[name] is None:
                errors[name] = [f"Invalid {name}."]
    since, until = bounds["since"], bounds["until"]
    if since is not None and until is not None and since > until:
        errors["until"] = ["Must not be before since."]
    if errors:
        return None, errors
    window = RecordsWindow(
        since=since, until=until, series_id=ints["series"], event_id=ints["event"]
    )
    return RecordsFilter(window=window, user_id=ints["user"]), {}


def _staff_org(request: Request, org_id: int, endpoint: str) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    try:
        require_org_staff(request.user, org, None)
    except PermissionDenied:
        log.warning(
            "signup_records_denied",
            system="events",
            subsystem="ledger",
            org_id=org.pk,
            user_id=request.user.pk,
            endpoint=endpoint,
        )
        raise
    return org


def _internal_org(request: Request) -> Organization | Response:
    text = request.query_params.get("organization")
    if not text:
        return Response(
            {"organization": ["This field is required."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    org_id = _bounded_int(text, 1, MAX_DB_INT)
    if org_id is None:
        return Response(
            {"organization": ["Invalid organization."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return get_object_or_404(Organization, pk=org_id)


class _SignupRecordsBase(JSONErrorsMixin):
    renderer_classes = [JSONRenderer, SignupRecordsCSVRenderer]
    via = ""
    signup_records: list[SignupRecord] | None = None

    def get_renderer_context(self) -> dict[str, Any]:
        context = super().get_renderer_context()
        context["signup_records"] = self.signup_records or []
        return context

    def _respond(self, request: Request, org: Organization) -> Response:
        flt, errors = _records_params(request.query_params, org)
        if flt is None:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            records = build_signup_records(org.pk, flt)
        except TooManyRecords:
            return Response(TOO_MANY_RECORDS_BODY, status=status.HTTP_400_BAD_REQUEST)
        self.signup_records = records
        fmt = request.accepted_renderer.format
        log.info(
            "signup_records_viewed",
            system="events",
            subsystem="ledger",
            org_id=org.pk,
            format=fmt,
            row_count=len(records),
            has_since=flt.window.since is not None,
            has_until=flt.window.until is not None,
            filter_series=flt.window.series_id is not None,
            filter_event=flt.window.event_id is not None,
            filter_user=flt.user_id is not None,
            via=self.via,
        )
        response = Response(
            {
                "organization": org.pk,
                "count": len(records),
                "results": [record_to_json(r) for r in records],
            }
        )
        if fmt == SignupRecordsCSVRenderer.format:
            stamp = timezone.now().strftime("%Y%m%d")
            response["Content-Disposition"] = (
                f'attachment; filename="signup-records-{org.pk}-{stamp}.csv"'
            )
        return response


class OrgSignupRecordsView(_SignupRecordsBase):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SignupRecordsThrottle]
    via = "org"

    def get(self, request: Request, org_id: int) -> Response:
        return self._respond(request, _staff_org(request, org_id, "records"))


class InternalSignupRecordsView(_SignupRecordsBase):
    authentication_classes = [InternalServiceAuth]
    permission_classes = [IsInternalService]
    via = "internal"

    def get(self, request: Request) -> Response:
        org = _internal_org(request)
        return org if isinstance(org, Response) else self._respond(request, org)


def _ledger_page_params(
    params: QueryDict,
) -> tuple[LedgerCursor | None, int | None, dict[str, list[str]]]:
    errors: dict[str, list[str]] = {}
    cursor: LedgerCursor | None = None
    size: int | None = HISTORY_PAGE_SIZE
    if token := params.get("cursor"):
        try:
            cursor = decode_ledger_cursor(token)
        except ValueError:
            errors["cursor"] = [CURSOR_MESSAGE]
    if text := params.get("page_size"):
        size = _bounded_int(text, 1, HISTORY_MAX_PAGE_SIZE)
        if size is None:
            errors["page_size"] = ["Invalid page size."]
    return cursor, size, errors


class _SignupLedgerBase(APIView):
    renderer_classes = [JSONRenderer]
    via = ""

    def _respond(self, request: Request, org: Organization) -> Response:
        flt, errors = _records_params(request.query_params, org)
        cursor, size, page_errors = _ledger_page_params(request.query_params)
        errors.update(page_errors)
        if flt is None or size is None or errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        window = flt.window
        qs = SignupLedgerEntry.objects.nocache().filter(organization_id=org.pk)
        windowed: dict[int, LedgerEvent] | None = None
        if window.has_time_bounds or window.series_id is not None:
            windowed = resolve_ledger_events(org.pk, window=window)
            qs = qs.filter(event_id__in=list(windowed))
        elif window.event_id is not None:
            qs = qs.filter(event_id=window.event_id)
        if flt.user_id is not None:
            qs = qs.filter(
                Q(subject_user_id=flt.user_id)
                | Q(subject_user__isnull=True, subject_snapshot__user_id=flt.user_id)
            )
        count = qs.count()
        if cursor is not None:
            qs = qs.filter(pk__gt=cursor.pk)
        rows = list(
            qs.select_related("subject_user__base_profile", "actor_user__base_profile")
            .nocache()
            .order_by("pk")[: size + 1]
        )
        next_token = LedgerCursor(rows[size - 1].pk).token if len(rows) > size else None
        rows = rows[:size]
        page_events = {row.event_id for row in rows}
        if windowed is not None:
            events = {k: v for k, v in windowed.items() if k in page_events}
        elif page_events:
            events = resolve_ledger_events(org.pk, event_ids=page_events)
        else:
            events = {}
        user_ids = {
            uid
            for row in rows
            for uid in (row.subject_user_id, row.actor_user_id)
            if uid
        }
        serializer = OrgSignupLedgerEntrySerializer(
            rows,
            many=True,
            context={
                "request": request,
                "ledger_events": events,
                "_history_guild_nicknames": guild_nicknames(org.pk, user_ids),
            },
        )
        log.info(
            "signup_ledger_viewed",
            system="events",
            subsystem="ledger",
            org_id=org.pk,
            row_count=len(rows),
            has_since=window.since is not None,
            has_until=window.until is not None,
            filter_series=window.series_id is not None,
            filter_event=window.event_id is not None,
            filter_user=flt.user_id is not None,
            page_size=size,
            has_cursor=cursor is not None,
            via=self.via,
        )
        return Response(
            build_cursor_envelope(
                request, count=count, next_cursor=next_token, results=serializer.data
            )
        )


class OrgSignupLedgerView(_SignupLedgerBase):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SignupRecordsThrottle]
    via = "org"

    def get(self, request: Request, org_id: int) -> Response:
        return self._respond(request, _staff_org(request, org_id, "ledger"))


class InternalSignupLedgerView(_SignupLedgerBase):
    authentication_classes = [InternalServiceAuth]
    permission_classes = [IsInternalService]
    via = "internal"

    def get(self, request: Request) -> Response:
        org = _internal_org(request)
        return org if isinstance(org, Response) else self._respond(request, org)


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def internal_signup_records_purge(request: Request) -> Response:
    resume = request.data.get("resume_org_id")
    if resume is not None and (
        not isinstance(resume, int)
        or isinstance(resume, bool)
        or not 1 <= resume <= MAX_DB_INT
    ):
        return Response(
            {"resume_org_id": ["Invalid organization."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    body: dict[str, Any] = asdict(purge_expired(resume_org_id=resume))
    body["per_org"] = {str(org_id): n for org_id, n in body["per_org"].items()}
    return Response(body)
