from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import Organization
from org.feature_errors import require_org_admin
from org.serializers import OrgSettingsSerializer
from org.settings_service import get_org_settings, update_org_settings


@api_view(["GET", "PATCH"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_settings_view(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, None)
    instance = get_org_settings(org)

    if request.method == "PATCH":
        serializer = OrgSettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = update_org_settings(
            org, actor=request.user, changes=serializer.validated_data
        )

    return Response(OrgSettingsSerializer(instance).data)
