import csv
import io
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

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
from events.history import MAX_DB_INT
from events.ledger import RecordsWindow, purge_expired
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
from org.feature_errors import require_org_staff
from org.models import Organization
from org.standing.periods import local_day_start_utc
from telemetry.logging import get_logger

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
    return value if value.tzinfo is not None else None


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
                endpoint="records",
            )
            raise
        return self._respond(request, org)


class InternalSignupRecordsView(_SignupRecordsBase):
    authentication_classes = [InternalServiceAuth]
    permission_classes = [IsInternalService]
    via = "internal"

    def get(self, request: Request) -> Response:
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
        return self._respond(request, get_object_or_404(Organization, pk=org_id))


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def internal_signup_records_purge(request: Request) -> Response:
    body: dict[str, Any] = asdict(purge_expired())
    body["per_org"] = {str(org_id): n for org_id, n in body["per_org"].items()}
    return Response(body)
