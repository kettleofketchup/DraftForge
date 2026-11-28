"""Internal leadership API, mounted under ``api/internal/leadership/`` (X-Internal-Token)."""

from django.utils import timezone
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot.schemas import ReviewDMPlanBody
from org.leadership import review_dm


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def review_dms_plan(request: Request) -> Response:
    try:
        body = ReviewDMPlanBody.model_validate(request.data)
    except ValidationError:
        return Response(
            {"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST
        )
    messages = review_dm.plan(body.event_id, body.snapshot_ids, now=timezone.now())
    return Response({"messages": [m.model_dump(mode="json") for m in messages]})
