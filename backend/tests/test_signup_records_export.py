"""Test-only lazy fixture endpoints for the sign-up records export scenarios."""

from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.utils import isTestEnvironment
from tests.populate.signup_records_export import (
    populate_signup_records_export_data,
    signup_records_export_test_data,
)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def signup_records_export_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=404)
    return Response(signup_records_export_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_signup_records_export(request: Request) -> Response:
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=404)
    populate_signup_records_export_data(force=True)
    return Response(signup_records_export_test_data())
