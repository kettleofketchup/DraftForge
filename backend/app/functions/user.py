from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

# Create your views here.
from app.models import PositionsModel
from app.serializers import (
    PositionsSerializer,
    UserSerializer,
)
from events.eligibility import precheck_friend_id, validate_friend_id
from steam.services.account_lookup import steam_account_exists
from telemetry.logging import get_logger

log = get_logger(__name__)

DUPLICATE_FRIEND_ID_BODY: dict[str, str] = {
    "error": "This Friend ID is already linked to another account"
}


def _friend_id_error(exc: ValidationError) -> Response:
    if exc.code == "duplicate_friend_id":
        return Response(DUPLICATE_FRIEND_ID_BODY, status=status.HTTP_409_CONFLICT)
    http_status = (
        status.HTTP_429_TOO_MANY_REQUESTS
        if exc.code == "steam_lookup_rate_limited"
        else status.HTTP_400_BAD_REQUEST
    )
    return Response({"error": exc.messages[0], "code": exc.code}, status=http_status)


class ProfileUpdateSerializer(serializers.Serializer):
    positions = PositionsSerializer(many=False, required=False)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)


@api_view(["post"])
@permission_classes([IsAuthenticated])
def profile_update(request: Request) -> Response:
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
        try:
            precheck_friend_id(str(steam_account_id), user, allow_change=True)
        except ValidationError as exc:
            return _friend_id_error(exc)
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
    try:
        with transaction.atomic():
            if steam_account_id is not None:
                new_id = validate_friend_id(
                    str(steam_account_id), user, allow_change=True
                )
                if new_id is not None:
                    user.steam_account_id = new_id
                    if steam_account_exists(new_id, cache_only=True) is True:
                        user.steam_account_exists_checked_at = timezone.now()
            posObj.save()
            user.save()
    except ValidationError as exc:
        user.refresh_from_db()
        return _friend_id_error(exc)
    except IntegrityError:
        user.refresh_from_db()
        return Response(DUPLICATE_FRIEND_ID_BODY, status=status.HTTP_409_CONFLICT)

    return Response(UserSerializer(user).data, status=201)
