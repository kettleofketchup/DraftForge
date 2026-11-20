from django.contrib.auth.models import AnonymousUser
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Organization
from app.permissions_org import (
    can_view_org_members,
    has_org_admin_access,
    has_org_staff_access,
)
from org.feature_errors import feature_locked, not_permitted
from org.features import active_features
from org.standing import api as standing
from org.standing.periods import parse_period
from org.standing.serializers import leaderboard_data, track_info_data
from org.standing.types import TrackInfo, ViewerRoles


def _roles(viewer: CustomUser | AnonymousUser, org: Organization) -> ViewerRoles:
    return ViewerRoles(
        is_admin=has_org_admin_access(viewer, org),
        is_staff=has_org_staff_access(viewer, org),
        can_view_members=can_view_org_members(viewer, org),
    )


def _tracks(request: Request, org: Organization) -> list[TrackInfo]:
    return standing.tracks_for(
        org.pk,
        viewer=request.user,
        features=active_features(org.pk),
        roles=_roles(request.user, org),
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def standing_tracks(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    return Response({"tracks": [track_info_data(t) for t in _tracks(request, org)]})


@api_view(["GET"])
@permission_classes([AllowAny])
def standing_leaderboard(request: Request, org_id: int, track: str) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    try:
        period = parse_period(org, request.query_params.get("period"))
    except ValueError as exc:
        raise ValidationError({"period": str(exc)}) from exc
    metric = request.query_params.get("metric")
    try:
        adapter_metrics = standing.track_metrics(track)
    except standing.UnknownTrack as exc:
        raise NotFound() from exc
    key = metric or next(m.key for m in adapter_metrics if m.default)
    try:
        board = standing.leaderboard(org, track, key, period, viewer=request.user)
    except standing.UnknownMetric as exc:
        raise ValidationError({"metric": f"Unknown metric {key!r}."}) from exc
    except standing.FeatureLocked as exc:
        raise feature_locked() from exc
    info = next(t for t in _tracks(request, org) if t.key == track)
    if not info.can_view_rows and not info.can_view_own and board.total is None:
        if not request.user.is_authenticated:
            raise NotAuthenticated()
        raise not_permitted()
    return Response(leaderboard_data(board))
