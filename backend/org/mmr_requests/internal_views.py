from dataclasses import asdict

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from org.mmr_requests.retention import purge_expired_screenshots


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def purge_screenshots(request: Request) -> Response:
    return Response(asdict(purge_expired_screenshots()))
