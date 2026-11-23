"""Test endpoint for the signup history E2E specs (TEST=true only).

GET /api/tests/signup-history/data/ (tests/urls.py) returns the seeded org,
event and user pks by role (tests.populate.signup_history). POST
/api/tests/signup-history/reset/ rebuilds the event and its ledger, then
returns the same lookup.
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
from tests.populate.signup_history import (
    populate_signup_history_data,
    signup_history_test_data,
)


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def signup_history_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(signup_history_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_signup_history(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    populate_signup_history_data(force=True)
    return Response(signup_history_test_data())
