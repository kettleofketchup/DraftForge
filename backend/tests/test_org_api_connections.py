"""Test endpoints for the org API connections E2E spec (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- POST login-org-api-connections/<role>/: log in as a connections test user
  (tests.data.org_api_connections.API_CONNECTIONS_ROLE_USERS).
- POST org-api-connections/reset/: recreate the orgs, users, roles, switches
  and seed, drop every connection row, install the fake transport.
- POST org-api-connections/drive/: run the fixture orgs' due runs and
  deliveries through the real step services. Optional body
  {"edit_after_stage": {"user_pk": int, "mmr": int}}.
- GET org-api-connections/state/: fixture members' Dota 2 MMRs, the
  deliveries' states and the fake transport's call log (no credentials).
- POST org-api-connections/promotion-backlog/: seed an adopted promotion
  stream connection holding a backlog.

Every external call these flows make is answered by the fake transport in
tests.helpers.org_api_connections_transport, not by a real service.
"""

from typing import Any

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
from common.game import GameType
from common.utils import isTestEnvironment
from org.models import OrgApiMmrDelivery, OrgUserGameMmr
from tests.data.org_api_connections import (
    AC_ADMIN,
    API_CONNECTIONS_ORG,
    API_CONNECTIONS_ORGS,
    API_CONNECTIONS_ROLE_USERS,
)
from tests.helpers.org_api_connections_transport import (
    clear_fake_calls,
    drive_connection_work,
    fake_calls,
    install_fake_transport,
)
from tests.populate.org_api_connections import (
    reset_org_api_connections_data,
    seed_promotion_backlog,
)

FIXTURE_ORG_PKS = [o.pk for o in API_CONNECTIONS_ORGS if o.pk is not None]


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_org_api_connections(request: Request, role: str) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    data = API_CONNECTIONS_ROLE_USERS.get(role)
    if data is None:
        return Response(
            {
                "detail": f"Unknown role. One of: {', '.join(API_CONNECTIONS_ROLE_USERS)}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        return Response(
            {
                "detail": "Test user not populated. POST org-api-connections/reset/ first."
            },
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
def reset_org_api_connections(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    install_fake_transport()
    clear_fake_calls()
    return Response(reset_org_api_connections_data())


def _edit(data: Any) -> tuple[int, int] | None:
    edit = data.get("edit_after_stage") if isinstance(data, dict) else None
    if not isinstance(edit, dict):
        return None
    user_pk, mmr = edit.get("user_pk"), edit.get("mmr")
    if type(user_pk) is not int or type(mmr) is not int:
        return None
    return user_pk, mmr


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def drive_org_api_connections(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(
        drive_connection_work(FIXTURE_ORG_PKS, edit_after_stage=_edit(request.data))
    )


@csrf_exempt
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def org_api_connections_state(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    mmrs = {
        str(user_id): mmr
        for user_id, mmr in OrgUserGameMmr.objects.nocache()
        .filter(
            org_user__organization_id=API_CONNECTIONS_ORG.pk,
            game_type=GameType.DOTA2,
        )
        .values_list("org_user__user_id", "mmr")
    }
    deliveries = list(
        OrgApiMmrDelivery.objects.filter(
            connection__organization_id__in=FIXTURE_ORG_PKS
        )
        .order_by("pk")
        .values("connection_id", "state", "last_reason", "destination_origin")
    )
    return Response({"mmrs": mmrs, "deliveries": deliveries, "calls": fake_calls()})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def seed_org_api_promotion_backlog(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    connection = seed_promotion_backlog(CustomUser.objects.get(pk=AC_ADMIN.pk))
    return Response({"connection_id": connection.pk})
