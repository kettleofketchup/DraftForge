"""Test endpoints for the org locked features E2E specs (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- POST login-org-features/<role>/: log in as a locked features test user
  (tests.data.org_features.ORG_FEATURES_ROLE_USERS).
- GET org-features/data/: the seeded orgs, users, events and templates.
- POST org-features/reset/: rebuild the ledger, promo sends, point values,
  events, templates, switches and roles; returns the same body as data/.
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
from tests.data.org_features import ORG_FEATURES_ROLE_USERS
from tests.populate.org_features import (
    org_features_test_data,
    reset_org_features_data,
)


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_org_features(request: Request, role: str) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    data = ORG_FEATURES_ROLE_USERS.get(role)
    if data is None:
        return Response(
            {"detail": f"Unknown role. One of: {', '.join(ORG_FEATURES_ROLE_USERS)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        return Response(
            {"detail": "Test user not populated. Run db::populate first."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response(
        {"success": True, "user": {"pk": user.pk, "username": user.username}}
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def org_features_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(org_features_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_org_features(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(reset_org_features_data())
