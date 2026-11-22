from pathlib import PurePosixPath

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from league.models import LeagueUser
from org.mmr_requests.permissions import can_review_mmr_request
from org.mmr_requests.screenshots import (
    SanitizerBusy,
    ScreenshotRejected,
    StorageFull,
)
from org.mmr_requests.serializers import (
    MmrChangeRequestSerializer,
    MmrRequestCreateSerializer,
    with_serializer_relations,
)
from org.mmr_requests.services import (
    NotPending,
    PendingExists,
    cancel_request,
    create_member_request,
)
from org.mmr_requests.upload_guard import upload_tripped
from org.models import MmrChangeRequest, OrgUser

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
        return MmrChangeRequestSerializer(obj, context={"request": self.request}).data

    def _fresh(self, pk: int) -> MmrChangeRequest:
        return with_serializer_relations(MmrChangeRequest.objects.all()).get(pk=pk)

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
        return Response(
            MmrChangeRequestSerializer(qs, many=True, context={"request": request}).data
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
