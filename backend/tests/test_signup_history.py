"""Test endpoint for the signup history E2E specs (TEST=true only).

GET /api/tests/signup-history/data/ (tests/urls.py) returns the seeded org,
event and user pks by role (tests.populate.signup_history).
"""

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
from tests.populate.signup_history import signup_history_test_data


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def signup_history_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(signup_history_test_data())
