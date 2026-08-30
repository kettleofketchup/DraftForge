from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Create your views here.
from app.models import CustomUser, PositionsModel
from app.serializers import (
    PositionsSerializer,
    UserSerializer,
)
from telemetry.logging import get_logger

log = get_logger(__name__)


# This allows a user to update only for certain fields
class ProfileUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=True)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = (
            "nickname",
            "positions",
            "steam_account_id",
        )


class ProfileUpdateSerializer(serializers.Serializer):
    positions = PositionsSerializer(many=False, required=False)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)


@api_view(["post"])
@permission_classes([IsAuthenticated])
def profile_update(request):
    user = request.user
    if user.is_anonymous or not user.is_authenticated:
        return Response({"error": "Unauthorized"}, status=401)

    serializer = ProfileUpdateSerializer(data=request.data)
    log.debug(
        "profile_update_request", system="user", subsystem="functions", user_id=user.pk
    )
    if serializer.is_valid():
        positions = serializer.validated_data.get("positions", None)
        steam_account_id = serializer.validated_data.get("steam_account_id", None)
        nickname = serializer.validated_data.get("nickname", None)

    else:
        return Response(serializer.errors, status=400)
    log.debug(
        "profile_update_validated",
        system="user",
        subsystem="functions",
        user_id=user.pk,
    )

    # DotaUserProfile.positions is SET_NULL, so the shim getter can be None.
    # Create on demand to match the prior null=False behavior.
    if user.positions is None:
        user.positions = PositionsModel.objects.create()

    try:
        posObj = PositionsModel.objects.get(pk=user.positions.pk)

    except PositionsModel.DoesNotExist:
        return Response({"error": "Positions not found"}, status=404)

    if positions is not None:
        # Update the existing position object's fields
        for field, value in positions.items():
            setattr(posObj, field, value)
        user.positions = posObj
    if steam_account_id is not None:
        # steam_account_id is the 32-bit Friend ID (from Dotabuff URL)
        # save() auto-computes the 64-bit steamid
        if steam_account_id != user.steam_account_id:
            conflict = (
                CustomUser.objects.filter(steam_account_id=steam_account_id)
                .exclude(pk=user.pk)
                .first()
            )
            if conflict:
                return Response(
                    {"error": "This Friend ID is already linked to another account"},
                    status=409,
                )
            user.steam_account_id = steam_account_id
    if nickname is not None:
        user.nickname = nickname
    log.debug(
        "profile_update_fields",
        system="user",
        subsystem="functions",
        user_id=user.pk,
        has_positions=positions is not None,
        has_steam_account_id=steam_account_id is not None,
        has_nickname=nickname is not None,
    )
    with transaction.atomic():
        posObj.save()
        user.save()

    return Response(UserSerializer(user).data, status=201)
