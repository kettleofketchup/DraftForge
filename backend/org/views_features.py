from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import Organization
from app.permissions_org import is_site_admin
from org.feature_errors import not_permitted
from org.features import FeatureKey, set_org_feature
from org.models import OrgFeature


class OrgFeatureSerializer(serializers.Serializer):
    feature = serializers.ChoiceField(choices=FeatureKey.choices)
    enabled = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True)


def _feature_rows(org: Organization) -> list[dict[str, Any]]:
    rows = {
        row.feature: row
        for row in OrgFeature.objects.nocache()
        .filter(organization=org)
        .select_related("enabled_by")
    }
    result: list[dict[str, Any]] = []
    for key in sorted(FeatureKey.values):
        row = rows.get(key)
        enabled_by = row.enabled_by if row else None
        result.append(
            {
                "feature": key,
                "enabled": row.enabled if row else False,
                "notes": row.notes if row else "",
                "enabled_by": (
                    {"pk": enabled_by.pk, "username": enabled_by.username}
                    if enabled_by
                    else None
                ),
                "enabled_at": (
                    serializers.DateTimeField().to_representation(row.enabled_at)
                    if row and row.enabled_at
                    else None
                ),
            }
        )
    return result


@api_view(["GET", "PUT"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_features(request: Request, org_id: int) -> Response:
    if not is_site_admin(request.user):
        raise not_permitted()
    org = get_object_or_404(Organization, pk=org_id)

    if request.method == "PUT":
        serializer = OrgFeatureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        set_org_feature(
            org,
            FeatureKey(data["feature"]),
            enabled=data["enabled"],
            actor=request.user,
            notes=data.get("notes"),
        )

    return Response(_feature_rows(org))
