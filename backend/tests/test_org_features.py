"""Test endpoints for the org locked features E2E specs (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- POST login-org-features/<role>/: log in as a locked features test user
  (tests.data.org_features.ORG_FEATURES_ROLE_USERS).
- GET org-features/data/: the seeded orgs, users, events and templates.
- POST org-features/reset/: rebuild the ledger, promo sends, point values,
  events, templates, switches and roles; returns the same body as data/.
  An optional JSON body {"release_gate": true} turns the leadership staff
  release gate on with the closed snapshots left pending;
  {"captain_feedback_private": true} hides captain feedback from captains;
  {"external_contacts": true} seeds audiences and imported external contacts.
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
    release_gate = request.data.get("release_gate", False)
    if not isinstance(release_gate, bool):
        return Response(
            {"detail": "release_gate must be true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    audiences = request.data.get("audiences", False)
    if not isinstance(audiences, bool):
        return Response(
            {"detail": "audiences must be true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    captain_feedback_private = request.data.get("captain_feedback_private", False)
    if not isinstance(captain_feedback_private, bool):
        return Response(
            {"detail": "captain_feedback_private must be true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    external_contacts = request.data.get("external_contacts", False)
    if not isinstance(external_contacts, bool):
        return Response(
            {"detail": "external_contacts must be true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        reset_org_features_data(
            release_gate=release_gate,
            audiences=audiences,
            captain_feedback_private=captain_feedback_private,
            external_contacts=external_contacts,
        )
    )
