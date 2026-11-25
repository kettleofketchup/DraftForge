from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework.request import Request
from rest_framework.response import Response

from telemetry.logging import get_logger
from user.avatar import refresh_user_avatar
from user.tasks.avatar_refresh import refresh_avatars_batched

log = get_logger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_avatar(request: Request) -> Response:
    """
    Refresh the current user's Discord avatar by fetching the latest from Discord API.
    """
    try:
        user = request.user
        if not user.discordId:
            return Response(
                {"error": "User does not have a Discord ID associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = refresh_user_avatar(user.id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def refresh_user_avatar_admin(request: Request, user_id: int) -> Response:
    """
    Admin endpoint to refresh any user's Discord avatar.
    """
    try:
        result = refresh_user_avatar(user_id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_all_avatars(request: Request) -> Response:
    """Queue an asynchronous avatar refresh.

    Returns immediately (202 Accepted) and dispatches a Celery task that
    fetches Discord guild members in batched calls (1–3 paginated calls per
    org) and updates avatars in bulk. See `user.tasks.avatar_refresh
    .refresh_avatars_batched`.

    Public on purpose: every users-list page view fires it, so avatars stay
    fresh for everyone. One shared cache key caps it at one task per hour no
    matter who calls or how often. `cache.add` is an atomic set-if-absent, so
    concurrent callers can't both win and double-queue the task.
    """
    if not cache.add("avatar_refresh_last_run", timezone.now(), timeout=3600):
        return Response(
            {"message": "Avatar refresh can only be run once per hour."},
            status=status.HTTP_200_OK,
        )

    refresh_avatars_batched.delay()

    return Response(
        {"message": "Avatar refresh queued."},
        status=status.HTTP_202_ACCEPTED,
    )
