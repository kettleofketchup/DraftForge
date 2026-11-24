"""Internal API endpoints for the bot's voice presence feed.

Thin wrappers around ``events.voice_presence``: auth, pydantic validation,
delegation, counts-only logging. No business logic here.
"""

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
from discordbot.schemas import (
    VoicePresenceResponse,
    VoiceSnapshotRequest,
    VoiceStateRequest,
    WatchedChannelSchema,
    WatchedChannelsResponse,
)
from events.voice_presence import (
    PresenceOutcome,
    apply_voice_snapshot,
    apply_voice_state,
    watched_channels,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]
_LOG = {
    "system": "discord",
    "subsystem": "dispatch",
    "tags": ["events", "voice"],
    "tags_csv": "events,voice",
}


def _bad_request(exc: ValidationError) -> Response:
    return Response(
        {"error": "invalid_request", "detail": exc.errors()},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _response(outcome: PresenceOutcome) -> VoicePresenceResponse:
    return VoicePresenceResponse(
        success=True,
        detail=outcome.detail,
        events=outcome.events,
        joined=outcome.joined,
        left=outcome.left,
        confirmed=outcome.confirmed,
        unknown_users=outcome.unknown_users,
        not_signed_up=outcome.not_signed_up,
    )


def _counts(body: VoicePresenceResponse) -> dict[str, int | str]:
    return body.model_dump(exclude={"success"})


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def voice_watched_channels(request: Request) -> Response:
    channels = watched_channels()
    body = WatchedChannelsResponse(
        channels=[
            WatchedChannelSchema(
                guild_id=channel.guild_id,
                channel_id=channel.channel_id,
                event_ids=list(channel.event_ids),
            )
            for channel in channels
        ]
    )
    log.debug("internal_voice_watched_listed", **_LOG, channels=len(channels))
    return Response(body.model_dump())


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def voice_state(request: Request) -> Response:
    try:
        req = VoiceStateRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    body = _response(apply_voice_state(**req.model_dump()))
    log.info(
        "internal_voice_state_processed",
        **_LOG,
        guild_id=req.guild_id,
        discord_user_id=req.discord_user_id,
        **_counts(body),
    )
    return Response(body.model_dump())


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def voice_snapshot(request: Request) -> Response:
    try:
        req = VoiceSnapshotRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    channels: dict[str, list[str]] = {}
    for channel in req.channels:
        channels.setdefault(channel.channel_id, []).extend(channel.member_ids)
    body = _response(
        apply_voice_snapshot(
            guild_id=req.guild_id,
            channels=channels,
            missing_channel_ids=req.missing_channel_ids,
        )
    )
    log.info(
        "internal_voice_snapshot_processed",
        **_LOG,
        guild_id=req.guild_id,
        channels=len(channels),
        missing_channels=len(req.missing_channel_ids),
        **_counts(body),
    )
    return Response(body.model_dump())
