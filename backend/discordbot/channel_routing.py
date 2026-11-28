from __future__ import annotations

import requests

from . import utils
from .delivery_types import (
    ChannelKind,
    DeliveryFailure,
    DeliveryReceipt,
    FailureCategory,
    FailurePhase,
    ResolvedChannel,
    valid_discord_id,
)
from .http_evidence import (
    decode_response_json,
    failure_from_exception,
    failure_from_response,
)

_CHANNEL_KINDS = {
    0: ChannelKind.TEXT,
    5: ChannelKind.ANNOUNCEMENT,
    15: ChannelKind.FORUM,
}


def resolve_guild_channel(
    channel_id: str, expected_guild_id: str
) -> ResolvedChannel | DeliveryFailure:
    phase = FailurePhase.CHANNEL_LOOKUP
    if not valid_discord_id(channel_id) or not valid_discord_id(expected_guild_id):
        return DeliveryFailure(phase, FailureCategory.CHANNEL_MISMATCH)
    try:
        response = utils._rate_limited_request(
            "GET",
            f"{utils.DISCORD_API_BASE}/channels/{channel_id}",
            headers=utils._get_headers(),
        )
        if not 200 <= response.status_code < 300:
            return failure_from_response(response, phase)
        data = decode_response_json(response)
    except requests.RequestException as exc:
        return failure_from_exception(exc, phase)
    if not isinstance(data, dict):
        return DeliveryFailure(
            phase, FailureCategory.MALFORMED_RESPONSE, response.status_code
        )
    if data.get("id") != channel_id or data.get("guild_id") != expected_guild_id:
        return DeliveryFailure(
            phase, FailureCategory.CHANNEL_MISMATCH, response.status_code
        )
    channel_type = data.get("type")
    if type(channel_type) is not int or channel_type not in _CHANNEL_KINDS:
        return DeliveryFailure(
            phase, FailureCategory.UNSUPPORTED_CHANNEL, response.status_code
        )
    return ResolvedChannel(channel_id, expected_guild_id, _CHANNEL_KINDS[channel_type])


def build_create_request(
    channel: ResolvedChannel, message_payload: dict, title: str | None
) -> tuple[str, dict]:
    base = f"{utils.DISCORD_API_BASE}/channels/{channel.channel_id}"
    if channel.kind == ChannelKind.FORUM:
        if title is None or not title.strip():
            raise ValueError("Forum posts require a title")
        return f"{base}/threads", {"name": title[:100], "message": message_payload}
    return f"{base}/messages", message_payload


def normalize_receipt(channel: ResolvedChannel, data: object) -> DeliveryReceipt | None:
    if not isinstance(data, dict):
        return None
    thread_id = None
    message_id = data.get("id")
    if channel.kind == ChannelKind.FORUM:
        thread_id = message_id
        message = data.get("message")
        if not isinstance(message, dict):
            return None
        message_id = message.get("id")
    try:
        return DeliveryReceipt.from_json(
            {
                "parent_channel_id": channel.channel_id,
                "message_id": message_id,
                "thread_id": thread_id,
                "kind": channel.kind.value,
            }
        )
    except ValueError:
        return None
