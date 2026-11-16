"""Activity switcher endpoints authenticated by the Activity credential."""

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from discordbot.activity_auth import ActivityAuthentication, ActivityIdentity
from discordbot.activity_menu import list_drafts


class HasActivityIdentity(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.auth, ActivityIdentity)


@api_view(["GET"])
@authentication_classes([ActivityAuthentication])
@permission_classes([HasActivityIdentity])
def activity_drafts(request: Request) -> Response:
    identity: ActivityIdentity = request.auth
    discord_user_id = str(identity.user.discordId or "")
    return Response(
        list_drafts(identity, discord_user_id),
        headers={"Cache-Control": "no-store"},
    )
