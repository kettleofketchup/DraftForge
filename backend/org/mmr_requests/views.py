from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.models import CustomUser
from league.models import League, LeagueUser
from league.permissions import has_league_staff_access
from org.mmr_requests.permissions import can_review_mmr_request, org_queue_filter
from org.mmr_requests.screenshots import (
    SanitizerBusy,
    ScreenshotRejected,
    StorageFull,
)
from org.mmr_requests.serializers import (
    MmrApproveSerializer,
    MmrChangeRequestSerializer,
    MmrRejectSerializer,
    MmrRequestCreateSerializer,
    MmrStaffSetSerializer,
    serialize_request,
    serialize_requests,
    with_serializer_relations,
)
from org.mmr_requests.services import (
    NotPending,
    PendingExists,
    SelfReview,
    approve_request,
    cancel_request,
    create_member_request,
    reject_request,
    staff_set_mmr,
)
from org.mmr_requests.summary import build_user_mmr_summary
from org.mmr_requests.upload_guard import upload_tripped
from org.models import MmrChangeRequest, Organization, OrgUser
from org.permissions import has_org_staff_access

SCREENSHOT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store",
    "Content-Security-Policy": "default-src 'none'; img-src 'self'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _validation_detail(exc: DjangoValidationError) -> dict[str, list[str]] | list[str]:
    if hasattr(exc, "error_dict"):
        return exc.message_dict
    return exc.messages


def _membership_or_400(
    model: type[OrgUser] | type[LeagueUser], field: str, pk: int | None
) -> OrgUser | LeagueUser | None:
    if pk is None:
        return None
    qs = model.objects.nocache()
    if model is LeagueUser:
        qs = qs.select_related("league", "org_user")
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise ValidationError({field: ["not_found"]})
    return obj


class MmrRequestViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MmrChangeRequestSerializer

    def _serialize(self, obj: MmrChangeRequest) -> dict:
        return serialize_request(obj, self.request)

    def _fresh(self, pk: int) -> MmrChangeRequest:
        return _fresh(pk)

    def create(self, request: Request) -> Response:
        payload = request.data
        if upload_tripped(request):
            return Response(
                {"screenshot": ["too_large"]}, status=status.HTTP_400_BAD_REQUEST
            )
        data = MmrRequestCreateSerializer(data=payload)
        data.is_valid(raise_exception=True)
        attrs = data.validated_data
        org_user = _membership_or_400(OrgUser, "org_user", attrs.get("org_user"))
        league_user = _membership_or_400(
            LeagueUser, "league_user", attrs.get("league_user")
        )
        try:
            row = create_member_request(
                user=request.user,
                target=attrs["target"],
                org_user=org_user,  # type: ignore[arg-type]
                league_user=league_user,  # type: ignore[arg-type]
                game_type=attrs.get("game_type", 0),
                requested_mmr=attrs["requested_mmr"],
                screenshot=attrs["screenshot"],
                note=attrs["note"],
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        except DjangoValidationError as exc:
            raise ValidationError(_validation_detail(exc)) from exc
        except PendingExists as exc:
            return Response(
                {"error": "pending_exists", "request_id": exc.request_id},
                status=status.HTTP_409_CONFLICT,
            )
        except ScreenshotRejected as exc:
            return Response(
                {"screenshot": [exc.code]}, status=status.HTTP_400_BAD_REQUEST
            )
        except SanitizerBusy:
            return Response(
                {"error": "busy"}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except StorageFull:
            return Response(
                {"error": "storage_full"}, status=status.HTTP_507_INSUFFICIENT_STORAGE
            )
        return Response(
            self._serialize(self._fresh(row.pk)), status=status.HTTP_201_CREATED
        )

    def mine(self, request: Request) -> Response:
        qs = with_serializer_relations(
            MmrChangeRequest.objects.filter(subject_user_id=request.user.pk)
        )
        return Response(serialize_requests(list(qs), request))

    def approve(self, request: Request, pk: int) -> Response:
        get_object_or_404(MmrChangeRequest, pk=pk)
        body = MmrApproveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        return _review_call(
            request,
            lambda: approve_request(pk, request.user, body.validated_data["mmr"]),
            status.HTTP_200_OK,
        )

    def reject(self, request: Request, pk: int) -> Response:
        get_object_or_404(MmrChangeRequest, pk=pk)
        body = MmrRejectSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        return _review_call(
            request,
            lambda: reject_request(pk, request.user, body.validated_data["reason"]),
            status.HTTP_200_OK,
        )

    def cancel(self, request: Request, pk: int) -> Response:
        get_object_or_404(MmrChangeRequest, pk=pk)
        try:
            row = cancel_request(pk, request.user)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        except NotPending as exc:
            return Response(
                {"error": "not_pending", "status": exc.status},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self._serialize(self._fresh(row.pk)))

    def screenshot(self, request: Request, pk: int) -> FileResponse:
        req = get_object_or_404(
            MmrChangeRequest.objects.select_related(
                "subject_user", "organization", "league"
            ),
            pk=pk,
        )
        if req.subject_user_id != request.user.pk and not can_review_mmr_request(
            request.user, req
        ):
            raise Http404
        name = req.screenshot.name
        if not name:
            raise Http404
        try:
            handle = req.screenshot.storage.open(name, "rb")
        except OSError as exc:
            raise Http404 from exc
        ext = PurePosixPath(name).suffix.lstrip(".") or "png"
        content_type = req.screenshot_content_type or f"image/{ext}"
        response = FileResponse(handle, content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="mmr-{req.pk}.{ext}"'
        for header, value in SCREENSHOT_HEADERS.items():
            response[header] = value
        return response


def _fresh(pk: int) -> MmrChangeRequest:
    return with_serializer_relations(MmrChangeRequest.objects.all()).get(pk=pk)


def _review_call(
    request: Request, fn: Callable[[], MmrChangeRequest], ok_status: int
) -> Response:
    try:
        row = fn()
    except SelfReview:
        return Response({"error": "self_review"}, status=status.HTTP_403_FORBIDDEN)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc) or None) from exc
    except DjangoValidationError as exc:
        raise ValidationError(_validation_detail(exc)) from exc
    except NotPending as exc:
        return Response(
            {"error": "not_pending", "status": exc.status},
            status=status.HTTP_409_CONFLICT,
        )
    except ScreenshotRejected as exc:
        return Response({"screenshot": [exc.code]}, status=status.HTTP_400_BAD_REQUEST)
    except SanitizerBusy:
        return Response({"error": "busy"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except StorageFull:
        return Response(
            {"error": "storage_full"}, status=status.HTTP_507_INSUFFICIENT_STORAGE
        )
    return Response(serialize_request(_fresh(row.pk), request), status=ok_status)


QUEUE_STATUSES = frozenset(MmrChangeRequest.Status.values) | {"all"}


def _queue_rows(request: Request, qs: Any) -> Response:
    wanted = request.query_params.get("status", MmrChangeRequest.Status.PENDING)
    if wanted not in QUEUE_STATUSES:
        raise ValidationError({"status": ["invalid"]})
    if wanted != "all":
        qs = qs.filter(status=wanted)
    league = request.query_params.get("league")
    if league:
        if not league.isdigit():
            raise ValidationError({"league": ["invalid"]})
        qs = qs.filter(league_id=int(league))
    rows = list(with_serializer_relations(qs).order_by("-created_at", "-pk"))
    return Response(serialize_requests(rows, request))


def _load_org_user(pk: int) -> OrgUser:
    row = (
        OrgUser.objects.nocache()
        .select_related("user", "organization")
        .filter(pk=pk)
        .first()
    )
    if row is None:
        raise ValidationError({"org_user": ["not_found"]})
    return row


def _load_league_user(pk: int) -> LeagueUser:
    row = (
        LeagueUser.objects.nocache()
        .select_related(
            "league",
            "league__organization",
            "org_user",
            "org_user__user",
            "org_user__organization",
        )
        .filter(pk=pk)
        .first()
    )
    if row is None:
        raise ValidationError({"league_user": ["not_found"]})
    return row


def _staff_set(
    request: Request, *, org_id: int | None = None, league_id: int | None = None
) -> Response:
    payload = request.data
    if upload_tripped(request):
        return Response(
            {"screenshot": ["too_large"]}, status=status.HTTP_400_BAD_REQUEST
        )
    body = MmrStaffSetSerializer(data=payload)
    body.is_valid(raise_exception=True)
    attrs = body.validated_data
    target = attrs["target"]
    org_user: OrgUser | None = None
    league_user: LeagueUser | None = None
    if target == MmrChangeRequest.Target.LEAGUE:
        league_user = _load_league_user(attrs["league_user"])
        in_scope = (
            league_user.league_id == league_id
            if league_id is not None
            else league_user.league.organization_id == org_id
        )
        if not in_scope:
            raise ValidationError({"league_user": ["not_found"]})
    else:
        if league_id is not None:
            raise ValidationError({"target": ["league_only"]})
        org_user = _load_org_user(attrs["org_user"])
        if org_user.organization_id != org_id:
            raise ValidationError({"org_user": ["not_found"]})
    return _review_call(
        request,
        lambda: staff_set_mmr(
            actor=request.user,
            target=target,
            org_user=org_user,
            league_user=league_user,
            game_type=attrs.get("game_type", 0),
            mmr=attrs["mmr"],
            screenshot=attrs["screenshot"],
            note=attrs["note"],
        ),
        status.HTTP_201_CREATED,
    )


class OrgMmrRequestViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MmrChangeRequestSerializer

    def _org(self, org_id: int) -> Organization:
        org = get_object_or_404(Organization, pk=org_id)
        if not has_org_staff_access(self.request.user, org):
            raise PermissionDenied()
        return org

    def _qs(self, org_id: int) -> Any:
        return MmrChangeRequest.objects.filter(org_queue_filter(org_id))

    def list(self, request: Request, org_id: int) -> Response:
        self._org(org_id)
        return _queue_rows(request, self._qs(org_id))

    def pending_count(self, request: Request, org_id: int) -> Response:
        self._org(org_id)
        count = self._qs(org_id).filter(status=MmrChangeRequest.Status.PENDING).count()
        return Response({"count": count})

    def staff_set(self, request: Request, org_id: int) -> Response:
        self._org(org_id)
        return _staff_set(request, org_id=org_id)


class LeagueMmrRequestViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MmrChangeRequestSerializer

    def _league(self, league_id: int) -> League:
        league = get_object_or_404(League, pk=league_id)
        if not has_league_staff_access(self.request.user, league):
            raise PermissionDenied()
        return league

    def _qs(self, league_id: int) -> Any:
        return MmrChangeRequest.objects.filter(
            league_id=league_id, target=MmrChangeRequest.Target.LEAGUE
        )

    def list(self, request: Request, league_id: int) -> Response:
        self._league(league_id)
        return _queue_rows(request, self._qs(league_id))

    def pending_count(self, request: Request, league_id: int) -> Response:
        self._league(league_id)
        count = (
            self._qs(league_id).filter(status=MmrChangeRequest.Status.PENDING).count()
        )
        return Response({"count": count})

    def staff_set(self, request: Request, league_id: int) -> Response:
        self._league(league_id)
        return _staff_set(request, league_id=league_id)


class UserMmrSummaryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, pk: int) -> Response:
        subject = get_object_or_404(CustomUser.objects.nocache(), pk=pk)
        summary = build_user_mmr_summary(subject, request.user)
        return Response(
            summary.model_dump(mode="json"),
            headers={"Cache-Control": "private, no-store"},
        )
