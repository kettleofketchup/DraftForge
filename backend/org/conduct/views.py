from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import Organization
from org.conduct.gate import get_conduct_settings
from org.conduct.serializers import ConductSettingsUpdateSerializer, settings_data
from org.conduct.services import update_conduct_settings
from org.feature_errors import require_org_admin
from org.features import FeatureKey


def _admin_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.CONDUCT)
    return org


@api_view(["GET", "PATCH"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def conduct_settings(request: Request, org_id: int) -> Response:
    org = _admin_org(request, org_id)
    row = get_conduct_settings(org)
    if request.method == "PATCH":
        body = ConductSettingsUpdateSerializer(
            data=request.data, context={"current": row}
        )
        body.is_valid(raise_exception=True)
        try:
            row = update_conduct_settings(
                org, actor=request.user, changes=body.validated_data
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
    return Response(settings_data(row))
