"""Public runtime configuration for the Discord embedded client.

Vite environment variables are fixed when frontend images are built. Serving
this public application ID from Django lets one image work in dev and prod.
Discord client secrets and bot tokens are deliberately never exposed here.
"""

from django.conf import settings
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from discordbot import activity_fake


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def activity_config(request: Request) -> Response:
    enabled = getattr(settings, "DISCORD_ACTIVITY_ENABLED", False)
    client_id = activity_fake.client_id() if enabled else None
    return Response(
        {"enabled": bool(enabled), "client_id": str(client_id) if client_id else None},
        headers={"Cache-Control": "no-store"},
    )
