"""Authenticated worker interface to the backend's durable Discord edit queue."""

from pydantic import ValidationError
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot import live_messages
from discordbot.schemas import (
    LIVE_EDIT_SCAN_HEADER,
    LiveEditClaimRequest,
    LiveEditFinish,
    LiveEditScan,
)


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def claim(request: Request) -> Response:
    try:
        body = LiveEditClaimRequest.model_validate(request.data)
    except ValidationError:
        return Response({"error": "invalid_request"}, status=400)
    work = live_messages.claim_live_edit(discord_user_id=body.discord_user_id)
    if isinstance(work, LiveEditScan):
        return Response(status=204, headers={LIVE_EDIT_SCAN_HEADER: work.value})
    if work is None:
        return Response(status=204)
    return Response(work)


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def finish(request: Request, pk: int) -> Response:
    try:
        body = LiveEditFinish.model_validate(request.data)
    except ValidationError:
        return Response({"error": "invalid_request"}, status=400)
    accepted = live_messages.finish_live_edit(
        pk,
        str(body.token),
        body.outcome,
        error_code=body.error_code,
        retry_after=body.retry_after,
    )
    return Response(status=204 if accepted else 409)
