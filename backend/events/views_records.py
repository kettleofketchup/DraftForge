from dataclasses import asdict
from typing import Any

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from events.ledger import purge_expired


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def internal_signup_records_purge(request: Request) -> Response:
    body: dict[str, Any] = asdict(purge_expired())
    body["per_org"] = {str(org_id): n for org_id, n in body["per_org"].items()}
    return Response(body)
