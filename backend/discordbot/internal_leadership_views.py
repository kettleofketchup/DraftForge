"""Internal API for leadership review DM button clicks (spec §7.4)."""

from django.utils import timezone
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from app.auth import InternalServiceAuth, IsInternalService
from discordbot.internal_signup_views import _bind_interaction
from discordbot.schemas import ReviewClickBody
from org.leadership.review_dm import apply_click


class LeadershipReviewClickThrottle(SimpleRateThrottle):
    scope = "leadership_review_click"
    rate = "30/min"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        data = request.data if isinstance(request.data, dict) else {}
        ident = str(data.get("discord_user_id") or "")
        if not ident.isdigit():
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
@throttle_classes([LeadershipReviewClickThrottle])
def review_click(request: Request) -> Response:
    _bind_interaction(request)
    try:
        body = ReviewClickBody.model_validate(request.data)
    except ValidationError:
        return Response(
            {"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST
        )
    result = apply_click(
        discord_user_id=body.discord_user_id,
        discord_message_id=body.discord_message_id,
        discord_channel_id=body.discord_channel_id,
        snapshot_id=body.snapshot_id,
        trait_id=body.trait_id,
        score=body.score,
        now=timezone.now(),
    )
    return Response(result.model_dump(mode="json"))
