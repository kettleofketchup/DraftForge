"""Test endpoints for the MMR sync API E2E spec (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- POST login-mmr-sync/<role>/: log in as an MMR sync test user
  (tests.data.mmr_sync.MMR_SYNC_ROLE_USERS).
- POST mmr-sync/reset/: recreate the orgs, users, roles and switches, drop
  every token, usage row and limits override; returns the lookup.
"""

from django.contrib.auth import login
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from common.utils import isTestEnvironment
from tests.data.mmr_sync import MMR_SYNC_ROLE_USERS
from tests.populate.mmr_sync import reset_mmr_sync_data


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_mmr_sync(request: Request, role: str) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    data = MMR_SYNC_ROLE_USERS.get(role)
    if data is None:
        return Response(
            {"detail": f"Unknown role. One of: {', '.join(MMR_SYNC_ROLE_USERS)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        return Response(
            {"detail": "Test user not populated. POST mmr-sync/reset/ first."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response(
        {"success": True, "user": {"pk": user.pk, "username": user.username}}
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_mmr_sync(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(reset_mmr_sync_data())
