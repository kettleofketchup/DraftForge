"""Test endpoints for the MMR update request E2E spec (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- GET mmr-requests/data/: the seeded org, league and users.
- POST mmr-requests/reset/?user=<pk>[&members_private=1]: delete that member's
  requests and screenshots and restore the 4200 unverified baseline (every
  member when `user` is omitted); the org member list is public unless
  `members_private=1`.
"""

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

from common.utils import isTestEnvironment
from tests.populate.mmr_requests import (
    MEMBER_PKS,
    mmr_requests_test_data,
    reset_mmr_requests,
)


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def mmr_requests_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(mmr_requests_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def mmr_requests_reset(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    raw = request.query_params.get("user")
    user_pk: int | None = None
    if raw is not None:
        if not raw.isdigit() or int(raw) not in MEMBER_PKS:
            return Response(
                {"user": ["not_an_mmr_request_member"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user_pk = int(raw)
    members_private = request.query_params.get("members_private") in {"1", "true"}
    reset_mmr_requests(user_pk, members_private=members_private)
    return Response(mmr_requests_test_data())
