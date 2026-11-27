from typing import Any

from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from discordbot.permissions import service
from discordbot.permissions.actions import PUBLIC_PREVIEW_ACTIONS
from discordbot.permissions.schemas import PermissionChecksRequest
from org.models import Organization
from org.permissions import has_org_staff_access


class DiscordPermissionRefreshThrottle(UserRateThrottle):
    scope: str = "discord_permission_refresh"


def validation_error_details(exc: ValidationError) -> list[dict[str, Any]]:
    return exc.errors(include_context=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def organization_permission_checks(request: Request, pk: int) -> Response:
    org = get_object_or_404(Organization, pk=pk)
    if not has_org_staff_access(request.user, org):
        return Response({"error": "Permission denied"}, status=403)
    try:
        body = PermissionChecksRequest.model_validate(request.data)
    except ValidationError as exc:
        return Response(
            {
                "error": "Invalid permission check request",
                "detail": validation_error_details(exc),
            },
            status=400,
        )
    if any(check.action not in PUBLIC_PREVIEW_ACTIONS for check in body.checks):
        return Response({"error": "Unsupported preview action"}, status=400)
    throttled = body.refresh and not DiscordPermissionRefreshThrottle().allow_request(
        request, None
    )
    result = service.run_checks(
        org.discord_server_id or None,
        service.preview_checks(body.checks),
        refresh=body.refresh and not throttled,
    )
    if throttled:
        for check in result.checks:
            check.refresh_state = "throttled"
    return Response(result.model_dump(mode="json"))
