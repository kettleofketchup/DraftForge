from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from common.game import GameType
from org.api_connections.mutations import MmrMutationContext
from org.api_tokens.auth import OrgApiTokenAuthentication, gate_token_request
from org.api_tokens.operations import (
    Operation,
    default_operations,
    entitlements_for,
    parse_operations,
)
from org.api_tokens.sync import MAX_ENTRIES, member_rows, sync_mmrs
from org.api_tokens.throttle import limits_for
from org.api_tokens.tokens import issue_token, revoke_token
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.models import (
    Organization,
    OrgApiLimits,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgLog,
)
from telemetry.logging import get_logger
from user.permissions import is_site_admin

log = get_logger(__name__)

MAX_USAGE_DAYS = 90


class CreateTokenSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64, trim_whitespace=True)
    # Omitted operations default to the MMR pair.
    operations = serializers.JSONField(required=False)

    def validate_operations(self, value: Any) -> list[str]:
        try:
            return parse_operations(value)
        except ValueError:
            known = ", ".join(op.value for op in Operation)
            raise serializers.ValidationError(
                f"Give a nonempty list of operations from: {known}."
            ) from None


class LimitsSerializer(serializers.Serializer):
    per_minute = serializers.IntegerField(min_value=1, max_value=10_000)
    per_day = serializers.IntegerField(min_value=1, max_value=1_000_000)


class SyncSerializer(serializers.Serializer):
    game_type = serializers.ChoiceField(
        choices=GameType.choices, default=GameType.DOTA2
    )
    mark_verified = serializers.BooleanField(default=True)
    entries = serializers.ListField(
        child=serializers.JSONField(), allow_empty=False, max_length=MAX_ENTRIES
    )


def _user_ref(user: CustomUser | None) -> dict[str, Any] | None:
    return {"pk": user.pk, "username": user.username} if user else None


def _dt(value: Any) -> str | None:
    return serializers.DateTimeField().to_representation(value) if value else None


def _token_row(token: OrgApiToken) -> dict[str, Any]:
    return {
        "id": token.pk,
        "name": token.name,
        "prefix": token.prefix,
        "operations": token.operations,
        "user": _user_ref(token.user),
        "created_at": _dt(token.created_at),
        "last_used_at": _dt(token.last_used_at),
        "revoked_at": _dt(token.revoked_at),
        "revoked_by": _user_ref(token.revoked_by),
    }


def _org_tokens(org: Organization) -> QuerySet[OrgApiToken]:
    return OrgApiToken.objects.filter(organization=org).select_related(
        "user", "revoked_by"
    )


@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_api_tokens(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    if request.method == "GET":
        require_org_admin(request.user, org, None)
        return Response([_token_row(t) for t in _org_tokens(org)])

    require_org_admin(request.user, org, None)
    serializer = CreateTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    operations = serializer.validated_data.get("operations") or default_operations()
    for feature in entitlements_for(operations):
        require_feature(org, feature)
    issued = issue_token(
        org, request.user, serializer.validated_data["name"], operations=operations
    )
    response = Response(
        {**_token_row(issued.token), "token": issued.raw},
        status=status.HTTP_201_CREATED,
    )
    response["Cache-Control"] = "no-store"
    return response


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def revoke_org_api_token(request: Request, org_id: int, token_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, None)
    token = get_object_or_404(_org_tokens(org), pk=token_id)
    revoke_token(token, request.user)
    return Response(_token_row(token))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def org_api_usage(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, None)
    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, MAX_USAGE_DAYS))
    since = timezone.now().date() - timedelta(days=days - 1)

    qs = OrgApiTokenUsage.objects.filter(organization=org, date__gte=since)
    daily = (
        qs.values("user_id", "user__username", "date")
        .annotate(requests=Sum("request_count"), throttled=Sum("throttled_count"))
        .order_by("-date", "user__username")
    )
    by_user: dict[int, dict[str, Any]] = {}
    for row in daily:
        entry = by_user.setdefault(
            row["user_id"],
            {
                "user": {"pk": row["user_id"], "username": row["user__username"]},
                "requests": 0,
                "throttled": 0,
                "days": [],
            },
        )
        entry["requests"] += row["requests"]
        entry["throttled"] += row["throttled"]
        entry["days"].append(
            {
                "date": row["date"].isoformat(),
                "requests": row["requests"],
                "throttled": row["throttled"],
            }
        )
    limits = limits_for(org.pk)
    connection_usage: dict[str, Any] = {}
    if request.query_params.get("by_connection") == "true":
        totals = (
            qs.filter(token__connection__isnull=False)
            .values("token__connection_id")
            .annotate(requests=Sum("request_count"), throttled=Sum("throttled_count"))
            .order_by("token__connection_id")
        )
        connection_usage["connections"] = [
            {
                "connection_id": row["token__connection_id"],
                "requests": row["requests"],
                "throttled": row["throttled"],
            }
            for row in totals
        ]
    return Response(
        {
            **connection_usage,
            "since": since.isoformat(),
            "days": days,
            "limits": {"per_minute": limits.per_minute, "per_day": limits.per_day},
            "users": sorted(
                by_user.values(), key=lambda u: (-u["requests"], u["user"]["pk"])
            ),
        }
    )


@api_view(["GET", "PUT"])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_api_limits(request: Request, org_id: int) -> Response:
    org = get_object_or_404(Organization, pk=org_id)
    if request.method == "GET":
        require_org_admin(request.user, org, None)
        limits = limits_for(org.pk)
        return Response({"per_minute": limits.per_minute, "per_day": limits.per_day})

    if not is_site_admin(request.user):
        raise not_permitted()
    serializer = LimitsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        OrgApiLimits.objects.update_or_create(
            organization=org,
            defaults={**data, "updated_by": request.user},
        )
        OrgLog.objects.create(
            organization=org,
            actor=request.user,
            action="set_api_limits",
            details=dict(data),
        )
    log.info(
        "org_api_limits_set",
        system="org",
        subsystem="api_tokens",
        org_id=org.pk,
        actor_id=request.user.pk,
        **data,
    )
    return Response(dict(data))


@api_view(["GET", "POST"])
@authentication_classes([OrgApiTokenAuthentication])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def org_mmr_sync(request: Request, org_id: int) -> Response:
    operation = Operation.MMR_READ if request.method == "GET" else Operation.MMR_WRITE
    org = gate_token_request(request, org_id, operation=operation)
    if request.method == "GET":
        game_type = request.query_params.get("game_type", str(GameType.DOTA2))
        if not game_type.isdigit() or int(game_type) not in GameType.values:
            return Response(
                {"detail": "Unknown game_type."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {"game_type": int(game_type), "members": member_rows(org, int(game_type))}
        )

    serializer = SyncSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    result = sync_mmrs(
        org,
        request.user,
        data["entries"],
        game_type=int(data["game_type"]),
        mark_verified=data["mark_verified"],
        sync_context=MmrMutationContext(
            origin_connection_id=request.auth.connection_id
        ),
    )
    return Response(result.as_dict())
