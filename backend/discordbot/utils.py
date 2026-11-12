# backend/discordbot/utils.py
"""Admin utility functions for sending Discord messages."""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING, Any

import redis as _redis
import requests
from django.conf import settings

from app import internal_client
from app.redis_keys import namespaced_key
from telemetry.logging import get_logger

from .embeds import (
    draft_ready_embed,
    event_announcement_embed,
    results_posted_embed,
    tournament_created_embed,
)
from .services.discord_members import DISCORD_HTTP_TIMEOUT_S

if TYPE_CHECKING:
    from app.models import Draft, Tournament
    from discordbot.models import EventTemplate

JSONDict = dict[str, Any]
Snowflake = int | str

log = get_logger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

# Discord error code for "Unknown Message" — the target message was deleted
# (by the operator, an automod bot, or any external actor). Surfacing this as
# a typed exception lets callers like send_signup_update flip the dedup state
# so the next sync recreates the post instead of retrying an edit on a ghost.
DISCORD_CODE_UNKNOWN_MESSAGE = 10008


class MessageDeletedError(Exception):
    """Raised when Discord reports the target message no longer exists (404 / 10008)."""

    def __init__(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        self.channel_id = str(channel_id)
        self.message_id = str(message_id)
        super().__init__(
            f"Discord message {self.message_id} in channel {self.channel_id} was deleted"
        )


_REDIS_HOST = getattr(settings, "REDIS_HOST", "redis")
redis_client = _redis.Redis(host=_REDIS_HOST, port=6379, db=2, socket_timeout=2)

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local bucket = redis.call('hmget', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])
if tokens == nil then
    tokens = burst
    last_refill = now
end
local elapsed = now - last_refill
tokens = math.min(burst, tokens + elapsed * rate)
if tokens >= 1 then
    tokens = tokens - 1
    redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, 10)
    return 1
else
    redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, 10)
    return 0
end
"""
_RATE_LIMIT_KEY = "discord:rate_limit:global"


def rate_limit_key() -> str:
    return namespaced_key(_RATE_LIMIT_KEY)


def _acquire_rate_limit_token(max_wait: float = 10.0) -> bool:
    """Acquire a token from the Redis rate limit bucket.

    Blocks up to max_wait seconds waiting for a token. Falls back to allowing
    the request if Redis is unavailable.

    Raises RuntimeError if no token is acquired within max_wait.
    """
    rate = getattr(settings, "DISCORD_RATE_LIMIT", 40)
    burst = getattr(settings, "DISCORD_RATE_LIMIT_BURST", 40)
    deadline = _time.monotonic() + max_wait
    while True:
        try:
            result = redis_client.eval(
                _TOKEN_BUCKET_LUA, 1, rate_limit_key(), rate, burst, _time.time()
            )
            if result == 1:
                return True
        except _redis.RedisError:
            log.warning(
                "rate_limiter_redis_unavailable", system="discord", subsystem="utils"
            )
            return True
        if _time.monotonic() >= deadline:
            raise RuntimeError(f"Discord rate limit: no token within {max_wait}s")
        _time.sleep(0.05)


def _rate_limited_request(
    method: str, url: str, max_retries: int = 3, **kwargs: Any
) -> requests.Response:
    """Make a rate-limited HTTP request to the Discord API.

    Acquires a token before each attempt and retries on 429 responses.
    Applies DISCORD_HTTP_TIMEOUT_S unless the caller passes its own timeout.
    """
    kwargs.setdefault("timeout", DISCORD_HTTP_TIMEOUT_S)
    for attempt in range(max_retries):
        _acquire_rate_limit_token()
        response = requests.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1.0)
            log.warning(
                "discord_rate_limited",
                system="discord",
                subsystem="utils",
                method=method,
                url=url,
                retry_after=retry_after,
            )
            _time.sleep(retry_after)
            continue
        return response
    return response


def _get_headers() -> dict[str, str]:
    """Get authorization headers for Discord API."""
    return {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def _log_discord_message(
    channel_id: Snowflake,
    embed_data: JSONDict,
    source: str | None,
    source_id: int | None,
    status_code: int | None = None,
    response_data: JSONDict | None = None,
    discord_message_id: str | None = None,
    success: bool = False,
    fired_by_user_id: int | None = None,
    tournament_log_id: int | None = None,
) -> int | None:
    """Log a Discord message send via the internal API (HTTP, not direct DB).

    Retries once on failure. No direct DB fallback — all writes must go through
    the internal API to prevent SQLite lock contention.
    """
    for attempt in range(2):
        kwargs: dict[str, Any] = dict(
            channel_id=str(channel_id),
            embed_data=embed_data,
            source=source or "unknown",
            source_id=source_id,
            status_code=status_code,
            response_data=response_data,
            discord_message_id=discord_message_id,
            success=success,
        )
        if fired_by_user_id:
            kwargs["fired_by_user_id"] = fired_by_user_id
        if tournament_log_id:
            kwargs["tournament_log_id"] = tournament_log_id
        resp = internal_client.create_message_log(**kwargs)
        if resp and resp.ok:
            return resp.json().get("id")
        if attempt == 0:
            _time.sleep(1)  # Brief retry delay

    log.error(
        "message_log_failed",
        system="discord",
        subsystem="utils",
        source=source,
        source_id=source_id,
    )
    return None


def sync_send_embed(
    channel_id: Snowflake,
    title: str,
    description: str,
    color: int,
    fields: list[JSONDict] | None = None,
    footer: JSONDict | None = None,
    source: str = "unknown",
    source_id: int | None = None,
) -> JSONDict | None:
    """
    Send a rich embed to a Discord channel and log via internal API.

    Args:
        channel_id: Discord channel ID
        title: Embed title
        description: Embed description
        color: Integer color value (e.g., 0x00FF00)
        fields: Optional list of field dicts with 'name', 'value', 'inline'
        footer: Optional footer dict with 'text'
        source: Descriptive label for what triggered this send
        source_id: Optional ID of the source object (e.g., tournament pk)

    Returns:
        dict: API response or None on error
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"

    embed: JSONDict = {
        "title": title,
        "description": description,
        "color": color,
    }

    if fields:
        embed["fields"] = fields

    if footer:
        embed["footer"] = footer

    payload = {"embeds": [embed]}

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response_data = response.json()
        response.raise_for_status()
        _log_discord_message(
            channel_id=channel_id,
            embed_data=embed,
            source=source,
            source_id=source_id,
            status_code=response.status_code,
            response_data=response_data,
            discord_message_id=response_data.get("id"),
            success=True,
        )
        log.info(
            "embed_sent",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            title=title,
            source=source,
            source_id=source_id,
        )
        return response_data
    except requests.RequestException as e:
        status_code = (
            getattr(e.response, "status_code", None)
            if hasattr(e, "response") and e.response
            else None
        )
        resp_data = None
        try:
            resp_data = (
                e.response.json() if hasattr(e, "response") and e.response else None
            )
        except Exception:
            pass
        _log_discord_message(
            channel_id=channel_id,
            embed_data=embed,
            source=source,
            source_id=source_id,
            status_code=status_code,
            response_data=resp_data,
            success=False,
        )
        log.error(
            "embed_send_failed",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            source=source,
            source_id=source_id,
            error=str(e),
        )
        return None


def sync_send_templated_embed(template: EventTemplate) -> JSONDict | None:
    """
    Send an embed using an EventTemplate.

    Args:
        template: EventTemplate instance

    Returns:
        dict: API response or None on error
    """
    embed = event_announcement_embed(template)
    return sync_send_embed(
        channel_id=template.channel_id,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        footer=embed.get("footer"),
    )


def sync_send_tournament_created(
    tournament: Tournament, channel_id: Snowflake | None = None
) -> JSONDict | None:
    """
    Notify Discord when a tournament is created.

    Args:
        tournament: Tournament model instance
        channel_id: Override channel (defaults to DISCORD_ADMIN_CHANNEL_ID)
    """
    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("admin_channel_not_configured", system="discord", subsystem="utils")
        return None

    embed = tournament_created_embed(tournament)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        fields=embed.get("fields"),
        source="tournament_created",
        source_id=tournament.pk,
    )


def sync_send_draft_ready(
    draft: Draft, channel_id: Snowflake | None = None
) -> JSONDict | None:
    """Notify Discord when a draft is ready to start."""
    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("admin_channel_not_configured", system="discord", subsystem="utils")
        return None

    embed = draft_ready_embed(draft)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        source="draft_ready",
        source_id=draft.pk,
    )


def sync_send_results_posted(
    tournament: Tournament, channel_id: Snowflake | None = None
) -> JSONDict | None:
    """Notify Discord when tournament results are posted."""
    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("admin_channel_not_configured", system="discord", subsystem="utils")
        return None

    embed = results_posted_embed(tournament)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        source="results_posted",
        source_id=tournament.pk,
    )


def sync_send_embed_with_components_no_log(
    channel_id: Snowflake,
    embed: JSONDict | list[JSONDict],
    components: list[JSONDict] | None = None,
    forum_thread_name: str | None = None,
    content: str | None = None,
    allowed_mentions: JSONDict | None = None,
) -> tuple[JSONDict, int]:
    """Discord HTTP send only — no logging side effect.

    Caller is responsible for the lease (claim before, finalize after).
    Returns (response_data, status_code) on success; raises RequestException
    on Discord error so caller can finalize with success=False.
    """
    embeds = embed if isinstance(embed, list) else [embed]
    message_content: JSONDict = {"embeds": embeds}
    if components:
        message_content["components"] = components
    if content:
        message_content["content"] = content
    if allowed_mentions:
        message_content["allowed_mentions"] = allowed_mentions

    # Build payload — forum thread wraps message in a "message" key
    if forum_thread_name:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/threads"
        payload = {
            "name": forum_thread_name[:100],
            "message": message_content,
        }
    else:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
        payload = message_content

    response = _rate_limited_request("POST", url, json=payload, headers=_get_headers())
    response_data = response.json()
    response.raise_for_status()
    return response_data, response.status_code


def sync_send_embed_with_components(
    channel_id: Snowflake,
    embed: JSONDict | list[JSONDict],
    components: list[JSONDict] | None = None,
    source: str | None = None,
    source_id: int | None = None,
    forum_thread_name: str | None = None,
    content: str | None = None,
    allowed_mentions: JSONDict | None = None,
    fired_by_user_id: int | None = None,
) -> JSONDict | None:
    """Lease-wrapped Discord embed send.

    Acquires a pre-send lease via claim_discord_message_log (which writes a
    success=None row to DiscordMessageLog). The partial unique index on
    (source, source_id) WHERE success IS NOT FALSE serializes claim attempts
    so only one worker reaches the Discord HTTP send. After the send,
    finalize_discord_message_log flips success to True/False.

    For source_id=None (anonymous sends, no dedup target), uses the
    post-send logging path instead — the lease pattern requires both source
    and source_id to be meaningful for the partial unique constraint.

    Returns:
        dict: API response with _message_log_id key on success
        None: lease held by another worker, OR Discord send failed
    """
    embeds = embed if isinstance(embed, list) else [embed]
    embed_data = embeds[0] if embeds else {}

    # source_id=None can't participate in the lease — SQL NULL != NULL
    # makes multiple NULL source_id rows allowed by the unique constraint,
    # so dedup is meaningless.
    if source_id is None:
        return _send_with_post_log(
            channel_id,
            embed,
            components,
            source,
            source_id,
            forum_thread_name,
            content,
            allowed_mentions,
            fired_by_user_id,
        )

    log_pk = internal_client.claim_discord_message_log(
        source=source or "unknown",
        source_id=source_id,
        channel_id=str(channel_id),
        embed_data=embed_data,
        fired_by_user_id=fired_by_user_id,
    )
    if log_pk is None:
        log.info(
            "send_lease_held",
            system="discord",
            subsystem="utils",
            source=source,
            source_id=source_id,
        )
        return None

    try:
        response_data, status_code = sync_send_embed_with_components_no_log(
            channel_id=channel_id,
            embed=embed,
            components=components,
            forum_thread_name=forum_thread_name,
            content=content,
            allowed_mentions=allowed_mentions,
        )
        if forum_thread_name and response_data.get("message"):
            msg_id = response_data["message"].get("id")
            log.info(
                "forum_thread_created",
                system="discord",
                subsystem="utils",
                forum_thread_name=forum_thread_name,
                channel_id=str(channel_id),
                source=source,
                thread_id=response_data.get("id"),
            )
        else:
            msg_id = response_data.get("id")
            log.info(
                "embed_sent",
                system="discord",
                subsystem="utils",
                channel_id=str(channel_id),
                source=source,
                source_id=source_id,
            )

        internal_client.finalize_discord_message_log(
            log_pk,
            success=True,
            discord_message_id=msg_id,
            status_code=status_code,
            response_data=response_data,
        )
        response_data["_message_log_id"] = log_pk
        return response_data
    except requests.RequestException as e:
        status_code = (
            getattr(e.response, "status_code", None)
            if hasattr(e, "response") and e.response
            else None
        )
        resp_data = None
        try:
            resp_data = (
                e.response.json() if hasattr(e, "response") and e.response else None
            )
        except Exception:
            pass
        internal_client.finalize_discord_message_log(
            log_pk,
            success=False,
            status_code=status_code,
            response_data=resp_data,
        )
        log.error(
            "embed_send_failed",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            error=str(e),
        )
        return None


def _send_with_post_log(
    channel_id: Snowflake,
    embed: JSONDict | list[JSONDict],
    components: list[JSONDict] | None,
    source: str | None,
    source_id: int | None,
    forum_thread_name: str | None,
    content: str | None,
    allowed_mentions: JSONDict | None,
    fired_by_user_id: int | None,
) -> JSONDict | None:
    """Send + post-log path for callers without a meaningful source_id.

    Used by anonymous/admin sends that can't participate in the lease
    pattern (NULL source_id can't be dedup'd by the partial unique
    constraint). The log row is written AFTER the Discord HTTP send.
    """
    embeds = embed if isinstance(embed, list) else [embed]
    embed_data = embeds[0] if embeds else {}
    try:
        response_data, status_code = sync_send_embed_with_components_no_log(
            channel_id=channel_id,
            embed=embed,
            components=components,
            forum_thread_name=forum_thread_name,
            content=content,
            allowed_mentions=allowed_mentions,
        )
        if forum_thread_name and response_data.get("message"):
            msg_id = response_data["message"].get("id")
        else:
            msg_id = response_data.get("id")
        log_pk = _log_discord_message(
            channel_id=channel_id,
            embed_data=embed_data,
            source=source,
            source_id=source_id,
            status_code=status_code,
            response_data=response_data,
            discord_message_id=msg_id,
            success=True,
            fired_by_user_id=fired_by_user_id,
        )
        response_data["_message_log_id"] = log_pk
        return response_data
    except requests.RequestException as e:
        status_code = (
            getattr(e.response, "status_code", None)
            if hasattr(e, "response") and e.response
            else None
        )
        resp_data = None
        try:
            resp_data = (
                e.response.json() if hasattr(e, "response") and e.response else None
            )
        except Exception:
            pass
        _log_discord_message(
            channel_id=channel_id,
            embed_data=embed_data,
            source=source,
            source_id=source_id,
            status_code=status_code,
            response_data=resp_data,
            success=False,
            fired_by_user_id=fired_by_user_id,
        )
        log.error(
            "embed_send_failed",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            error=str(e),
        )
        return None


def sync_send_v2_message(
    channel_id: Snowflake,
    v2_payload: JSONDict,
    source: str | None = None,
    source_id: int | None = None,
    forum_thread_name: str | None = None,
) -> JSONDict | None:
    """Send a Components V2 message (no embeds, full component layout).

    Args:
        channel_id: Discord channel ID (text or forum)
        v2_payload: Dict with 'flags' and 'components' keys
        source: Log source identifier
        source_id: Log source PK
        forum_thread_name: If set, create a forum thread

    Returns:
        dict: API response or None on error
    """
    if forum_thread_name:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/threads"
        payload = {
            "name": forum_thread_name[:100],
            "message": v2_payload,
        }
    else:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
        payload = v2_payload

    embed_data = {
        "v2": True,
        "component_count": len(v2_payload.get("components", [])),
    }

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response_data = response.json()
        response.raise_for_status()

        if forum_thread_name and response_data.get("message"):
            msg_id = response_data["message"].get("id")
            log.info(
                "v2_forum_thread_created",
                system="discord",
                subsystem="utils",
                forum_thread_name=forum_thread_name,
                channel_id=str(channel_id),
                thread_id=response_data.get("id"),
            )
        else:
            msg_id = response_data.get("id")
            log.info(
                "v2_message_sent",
                system="discord",
                subsystem="utils",
                channel_id=str(channel_id),
            )

        _log_discord_message(
            channel_id=channel_id,
            embed_data=embed_data,
            source=source,
            source_id=source_id,
            status_code=response.status_code,
            response_data=response_data,
            discord_message_id=msg_id,
            success=True,
        )
        return response_data
    except requests.RequestException as e:
        status_code = (
            getattr(e.response, "status_code", None)
            if hasattr(e, "response") and e.response
            else None
        )
        resp_data = None
        try:
            resp_data = (
                e.response.json() if hasattr(e, "response") and e.response else None
            )
        except Exception:
            pass
        _log_discord_message(
            channel_id=channel_id,
            embed_data=embed_data,
            source=source,
            source_id=source_id,
            status_code=status_code,
            response_data=resp_data,
            success=False,
        )
        log.error(
            "v2_message_send_failed",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            error=str(e),
        )
        return None


def sync_edit_v2_message(
    channel_id: Snowflake, message_id: Snowflake, v2_payload: JSONDict
) -> JSONDict | None:
    """Edit a Components V2 message.

    Args:
        channel_id: Channel or thread ID where the message lives
        message_id: Message ID to edit
        v2_payload: Dict with 'flags' and 'components' keys
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    try:
        response = _rate_limited_request(
            "PATCH", url, json=v2_payload, headers=_get_headers()
        )
        response.raise_for_status()
        log.info(
            "v2_message_edited",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            message_id=str(message_id),
        )
        return response.json()
    except requests.RequestException as e:
        log.error(
            "v2_message_edit_failed",
            system="discord",
            subsystem="utils",
            message_id=str(message_id),
            error=str(e),
        )
        return None


def sync_edit_message(
    channel_id: Snowflake,
    message_id: Snowflake,
    embed: JSONDict | list[JSONDict] | None = None,
    components: list[JSONDict] | None = None,
) -> JSONDict | None:
    """Edit an existing Discord message (embed and/or components).

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID
        embed: Optional embed dict or list of embed dicts
        components: Optional components list to replace

    Returns:
        dict: API response or None on error
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"

    payload: JSONDict = {}
    if embed:
        payload["embeds"] = embed if isinstance(embed, list) else [embed]
    if components is not None:
        payload["components"] = components

    log.info(
        "discord_message_edit_attempt",
        system="discord",
        subsystem="utils",
        channel_id=str(channel_id),
        message_id=str(message_id),
        embed_count=len(payload.get("embeds", []) or []),
        component_count=len(payload.get("components", []) or []),
    )
    try:
        response = _rate_limited_request(
            "PATCH", url, json=payload, headers=_get_headers()
        )
        if not (200 <= response.status_code < 300):
            # Capture Discord's response body so 4xx errors (e.g. 404 Unknown
            # Message — the channel/message pair the bot tries to edit no
            # longer exists; this is the most likely "message got deleted"
            # scenario) are visible in Grafana without a DB dive.
            body: Any = None
            try:
                body = response.json()
            except Exception:
                body = (response.text or "")[:500]
            discord_code = body.get("code") if isinstance(body, dict) else None
            discord_msg = body.get("message") if isinstance(body, dict) else None
            log.error(
                "discord_message_edit_failed",
                system="discord",
                subsystem="utils",
                channel_id=str(channel_id),
                message_id=str(message_id),
                status_code=response.status_code,
                discord_code=discord_code,
                discord_message=discord_msg,
            )
            # Distinguish "the message is gone, recreate it" (404 + code 10008)
            # from generic transient errors. Callers handle the former by
            # clearing dedup; the latter still just gets swallowed (return None).
            if (
                response.status_code == 404
                and discord_code == DISCORD_CODE_UNKNOWN_MESSAGE
            ):
                raise MessageDeletedError(channel_id, message_id)
            response.raise_for_status()
        log.info(
            "discord_message_edit_success",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            message_id=str(message_id),
        )
        return response.json()
    except requests.RequestException as e:
        # Already logged the structured failure above when status_code was bad;
        # this branch also catches network errors (timeouts, DNS, etc.).
        log.error(
            "discord_message_edit_exception",
            system="discord",
            subsystem="utils",
            channel_id=str(channel_id),
            message_id=str(message_id),
            error=str(e),
        )
        return None


def sync_create_dm_channel(user_id: Snowflake) -> str | None:
    """Create a DM channel with a Discord user.

    Args:
        user_id: Discord user ID

    Returns:
        str: DM channel ID, or None on error
    """
    url = f"{DISCORD_API_BASE}/users/@me/channels"
    payload = {"recipient_id": str(user_id)}

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response.raise_for_status()
        data = response.json()
        return data.get("id")
    except requests.RequestException as e:
        log.error(
            "dm_channel_create_failed",
            system="discord",
            subsystem="utils",
            discord_user_id=str(user_id),
            error=str(e),
        )
        return None


def sync_send_dm(
    user_id: Snowflake,
    embed: JSONDict | None = None,
    content: str | None = None,
    components: list[JSONDict] | None = None,
    tournament_log_id: int | None = None,
) -> JSONDict | None:
    """Send a DM to a Discord user.

    Creates a DM channel then sends a message with optional embed.

    In test environments (TEST=true), only DMs to TEST_DISCORD_USER_ID
    are sent. All other DMs return a fake success response.

    Args:
        user_id: Discord user ID
        embed: Optional embed dict
        content: Optional text content
        components: Optional components list (action rows)
        tournament_log_id: Optional FK to link message log to tournament log

    Returns:
        dict: API response with message data, or None on error
    """
    # Test environment safety: only DM the designated test user
    if getattr(settings, "TEST", False):
        test_user_id = getattr(settings, "TEST_DISCORD_USER_ID", "")
        if test_user_id and str(user_id) != str(test_user_id):
            log.info(
                "dm_skipped_test_mode",
                system="discord",
                subsystem="utils",
                discord_user_id=str(user_id),
                test_user_id=str(test_user_id),
            )
            return {"id": "test-fake-message-id", "test_skipped": True}

    dm_channel_id = sync_create_dm_channel(user_id)
    if not dm_channel_id:
        return None

    url = f"{DISCORD_API_BASE}/channels/{dm_channel_id}/messages"
    payload: JSONDict = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    if components:
        payload["components"] = components

    if not payload:
        log.warning(
            "dm_empty_payload",
            system="discord",
            subsystem="utils",
            discord_user_id=str(user_id),
        )
        return None

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response.raise_for_status()
        data = response.json()
        log.info(
            "dm_sent",
            system="discord",
            subsystem="utils",
            discord_user_id=str(user_id),
            message_id=data.get("id"),
        )
        if tournament_log_id:
            _log_discord_message(
                channel_id=dm_channel_id,
                embed_data=embed or {},
                source="tournament_dm",
                source_id=None,
                status_code=response.status_code,
                response_data=data,
                discord_message_id=data.get("id"),
                success=True,
                tournament_log_id=tournament_log_id,
            )
        return data
    except requests.RequestException as e:
        log.error(
            "dm_send_failed",
            system="discord",
            subsystem="utils",
            discord_user_id=str(user_id),
            error=str(e),
        )
        if tournament_log_id:
            _log_discord_message(
                channel_id=dm_channel_id,
                embed_data=embed or {},
                source="tournament_dm",
                source_id=None,
                success=False,
                tournament_log_id=tournament_log_id,
            )
        return None


def sync_add_reactions(
    channel_id: Snowflake, message_id: Snowflake, emojis: list[str] | None = None
) -> None:
    """
    Add reaction emojis to a message for RSVP.

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID
        emojis: List of emoji strings (defaults to RSVP emojis)
    """
    if emojis is None:
        emojis = ["\u2705", "\u2753", "\u274c"]  # checkmark, question, x

    for emoji in emojis:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        try:
            response = _rate_limited_request("PUT", url, headers=_get_headers())
            response.raise_for_status()
        except requests.RequestException as e:
            log.error(
                "reaction_add_failed",
                system="discord",
                subsystem="utils",
                channel_id=str(channel_id),
                message_id=str(message_id),
                emoji=emoji,
                error=str(e),
            )
