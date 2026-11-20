from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from org.models import Organization
from org.feature_errors import feature_locked, not_permitted
from org.features import active_features
from org.standing import api as standing
from org.standing.periods import Period, parse_period
from org.standing.serializers import leaderboard_data


@api_view(["GET"])
@permission_classes([AllowAny])
def standing_tracks(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    tracks = standing.tracks_payload(
        org.pk,
        viewer=request.user,
        features=active_features(org.pk),
        roles=standing.viewer_roles(org, request.user),
    )
    return Response({"tracks": tracks})


def _period(request: Request, org: Organization, periodic: bool) -> Period:
    try:
        return parse_period(
            org, request.query_params.get("period") if periodic else None
        )
    except ValueError as exc:
        raise ValidationError({"period": str(exc)}) from exc


@api_view(["GET"])
@permission_classes([AllowAny])
def standing_leaderboard(request: Request, org_id: int, track: str) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    try:
        metrics = standing.track_metrics(track)
    except standing.UnknownTrack as exc:
        raise NotFound() from exc
    key = request.query_params.get("metric") or next(
        m.key for m in metrics if m.default
    )
    chosen = next((m for m in metrics if m.key == key), None)
    if chosen is None:
        raise ValidationError({"metric": f"Unknown metric {key!r}."})
    period = _period(request, org, chosen.periodic)
    try:
        board = standing.leaderboard(org, track, key, period, viewer=request.user)
    except standing.FeatureLocked as exc:
        raise feature_locked() from exc
    except standing.AccessDenied as exc:
        if not exc.authenticated:
            raise NotAuthenticated() from exc
        raise not_permitted() from exc
    return Response(leaderboard_data(board))
