import requests

from discordbot import utils
from telemetry.logging import get_logger

log = get_logger(__name__)


def resolve_signup_channel_type(channel_id: str, guild_id: str) -> int | None:
    reason = "invalid_metadata"
    if guild_id:
        try:
            response = utils._rate_limited_request(
                "GET",
                f"{utils.DISCORD_API_BASE}/channels/{channel_id}",
                headers=utils._get_headers(),
            )
            response.raise_for_status()
            metadata = response.json()
        except requests.RequestException:
            reason = "request_failed"
        else:
            if (
                isinstance(metadata, dict)
                and metadata.get("id") == channel_id
                and metadata.get("guild_id") == guild_id
                and type(metadata.get("type")) is int
                and metadata["type"] in (0, 5, 15)
            ):
                return metadata["type"]
    log.warning(
        "signup_destination_unavailable",
        system="events",
        subsystem="discord",
        channel_id=channel_id,
        reason=reason,
    )
    return None
