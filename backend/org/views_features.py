from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization, OrgLog
from app.permissions_org import is_site_admin
from app.serializers import TournamentUserSerializer
from org.feature_errors import not_permitted, require_org_admin
from org.features import FeatureKey, set_org_feature
from org.models import OrgFeature, OrgUser
from telemetry.logging import get_logger
from user.querysets import with_user_profiles

log = get_logger(__name__)


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


class PromoterAddSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


def _promoter_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.PROMOTION)
    return org


def _is_promoter(org: Organization, user: CustomUser) -> bool:
    return Organization.promoters.through.objects.filter(
        organization_id=org.pk, customuser_id=user.pk
    ).exists()


@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_promoters(request: Request, org_id: int) -> Response:
    org = _promoter_org(request, org_id)

    if request.method == "GET":
        promoters = with_user_profiles(
            CustomUser.objects.filter(promoter_organizations=org), dota=True
        ).order_by("username", "pk")
        return Response(TournamentUserSerializer(promoters, many=True).data)

    serializer = PromoterAddSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = get_object_or_404(CustomUser, pk=serializer.validated_data["user_id"])

    with transaction.atomic():
        if _is_promoter(org, user):
            return Response(
                {"error": "already a promoter"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org.promoters.add(user)
        OrgUser.objects.get_or_create(user=user, organization=org)
        OrgLog.objects.create(
            organization=org,
            actor=request.user,
            action="add_promoter",
            target_user=user,
        )
        invalidate_after_commit(org)

    log.info(
        "org_promoter_added",
        system="org",
        subsystem="promoters",
        org_id=org.pk,
        user_id=user.pk,
        actor_id=request.user.pk,
    )
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_org_promoter(request: Request, org_id: int, user_id: int) -> Response:
    org = _promoter_org(request, org_id)
    user = get_object_or_404(CustomUser, pk=user_id)

    with transaction.atomic():
        if not _is_promoter(org, user):
            return Response(
                {"error": "not a promoter"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org.promoters.remove(user)
        OrgLog.objects.create(
            organization=org,
            actor=request.user,
            action="remove_promoter",
            target_user=user,
        )
        invalidate_after_commit(org)

    log.info(
        "org_promoter_removed",
        system="org",
        subsystem="promoters",
        org_id=org.pk,
        user_id=user.pk,
        actor_id=request.user.pk,
    )
    return Response({"status": "removed"})
