"""GET/POST /api/users/<pk>/steam-verification/: staff vouch for a Friend ID."""

from typing import Any

from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from app.permissions_steam import can_verify_steam_account, can_view_steam_verification
from app.steam_accounts import (
    clear_steam_account_verification,
    mark_steam_account_verified,
    steam_verification_payload,
)
from app.steam_verification_schemas import SteamVerificationIn, SteamVerificationOut

NO_ID_BODY: dict[str, str] = {
    "error": "User has no Friend ID",
    "code": "no_steam_account_id",
}
INVALID_BODY_MESSAGE = "Send verified (true or false) and the Friend ID you saw."


def _load(pk: int) -> CustomUser:
    return get_object_or_404(
        CustomUser.objects.nocache().select_related("steam_account_verified_org"),
        pk=pk,
    )


def _payload(user: CustomUser, viewer: CustomUser) -> dict[str, Any]:
    return SteamVerificationOut.model_validate(
        steam_verification_payload(user, viewer=viewer)
    ).model_dump(mode="json")


def _current_id(pk: int) -> int | None:
    return (
        CustomUser.objects.nocache()
        .filter(pk=pk)
        .values_list("steam_account_id", flat=True)
        .first()
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def steam_verification(request: Request, pk: int) -> Response:
    target = _load(pk)
    actor: CustomUser = request.user

    if request.method == "GET":
        if not can_view_steam_verification(actor, target):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(_payload(target, actor))

    grant = can_verify_steam_account(actor, target)
    if grant is None:
        return Response(status=status.HTTP_403_FORBIDDEN)
    try:
        body = SteamVerificationIn.model_validate(request.data)
    except ValidationError as exc:
        return Response(
            {
                "error": INVALID_BODY_MESSAGE,
                "detail": exc.errors(include_url=False, include_context=False),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.steam_account_id is None:
        return Response(NO_ID_BODY, status=status.HTTP_400_BAD_REQUEST)

    if body.verified:
        applied = mark_steam_account_verified(
            target, actor, org_id=grant.org_id, expected_id=body.steam_account_id
        )
    else:
        applied = clear_steam_account_verification(
            target, expected_id=body.steam_account_id, actor=actor
        )
    if not applied:
        return Response(
            {
                "error": "The Friend ID changed since you loaded it",
                "code": "id_changed",
                "steam_account_id": _current_id(pk),
            },
            status=status.HTTP_409_CONFLICT,
        )
    return Response(_payload(target, actor))
