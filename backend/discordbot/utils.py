# backend/discordbot/utils.py
"""Admin utility functions for sending Discord messages."""

import logging
import time as _time

import redis as _redis
import requests
from django.conf import settings

from .embeds import event_announcement_embed

log = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

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


def _acquire_rate_limit_token(max_wait=10.0):
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
                _TOKEN_BUCKET_LUA, 1, _RATE_LIMIT_KEY, rate, burst, _time.time()
            )
            if result == 1:
                return True
        except _redis.RedisError:
            log.warning("Rate limiter Redis unavailable, allowing request")
            return True
        if _time.monotonic() >= deadline:
            raise RuntimeError(f"Discord rate limit: no token within {max_wait}s")
        _time.sleep(0.05)


def _rate_limited_request(method, url, max_retries=3, **kwargs):
    """Make a rate-limited HTTP request to the Discord API.

    Acquires a token before each attempt and retries on 429 responses.
    """
    for attempt in range(max_retries):
        _acquire_rate_limit_token()
        response = requests.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1.0)
            log.warning(
                "Discord 429 on %s %s, retry_after=%.1fs", method, url, retry_after
            )
            _time.sleep(retry_after)
            continue
        return response
    return response


def _get_headers():
    """Get authorization headers for Discord API."""
    return {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def _log_discord_message(
    channel_id,
    embed_data,
    source,
    source_id,
    status_code=None,
    response_data=None,
    discord_message_id=None,
    success=False,
    fired_by_user_id=None,
    tournament_log_id=None,
):
    """Log a Discord message send via the internal API (HTTP, not direct DB).

    Retries once on failure. No direct DB fallback — all writes must go through
    the internal API to prevent SQLite lock contention.
    """
    import time

    from app.internal_client import create_message_log

    for attempt in range(2):
        kwargs = dict(
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
        resp = create_message_log(**kwargs)
        if resp and resp.ok:
            return resp.json().get("id")
        if attempt == 0:
            time.sleep(1)  # Brief retry delay

    log.error(
        "Failed to log Discord message via internal API after 2 attempts (source=%s, source_id=%s)",
        source,
        source_id,
    )
    return None


def sync_send_embed(
    channel_id,
    title,
    description,
    color,
    fields=None,
    footer=None,
    source="unknown",
    source_id=None,
):
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

    embed = {
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
            "Sent embed to channel %s: %s (source=%s, source_id=%s)",
            channel_id,
            title,
            source,
            source_id,
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
            "Failed to send embed to channel %s: %s (source=%s, source_id=%s)",
            channel_id,
            e,
            source,
            source_id,
        )
        return None


def sync_send_templated_embed(template):
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


def sync_send_tournament_created(tournament, channel_id=None):
    """
    Notify Discord when a tournament is created.

    Args:
        tournament: Tournament model instance
        channel_id: Override channel (defaults to DISCORD_ADMIN_CHANNEL_ID)
    """
    from .embeds import tournament_created_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
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


def sync_send_draft_ready(draft, channel_id=None):
    """Notify Discord when a draft is ready to start."""
    from .embeds import draft_ready_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
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


def sync_send_results_posted(tournament, channel_id=None):
    """Notify Discord when tournament results are posted."""
    from .embeds import results_posted_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
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


def sync_send_embed_with_components(
    channel_id,
    embed,
    components=None,
    source=None,
    source_id=None,
    forum_thread_name=None,
    content=None,
    allowed_mentions=None,
    fired_by_user_id=None,
):
    """Send an embed with components to a Discord channel.

    If forum_thread_name is provided, creates a forum thread instead of a regular
    message. Falls back to regular message if forum thread creation fails.

    For forum threads:
    - The response contains the thread object with thread["id"] (thread channel ID)
    - The initial message ID is at response["message"]["id"]
    - Both are stored in DiscordMessageLog for later edits

    Args:
        channel_id: Discord channel ID (text or forum)
        embed: Embed dict
        components: Optional action row components
        source: Log source identifier
        source_id: Log source PK
        forum_thread_name: If set, create a forum thread with this title

    Returns:
        dict: API response or None on error
    """
    embeds = embed if isinstance(embed, list) else [embed]
    message_content = {"embeds": embeds}
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

    embed_data = embeds[0] if embeds else {}

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response_data = response.json()
        response.raise_for_status()

        if forum_thread_name and response_data.get("message"):
            msg_id = response_data["message"].get("id")
            log.info(
                "Created forum thread '%s' in channel %s (source=%s, thread_id=%s)",
                forum_thread_name,
                channel_id,
                source,
                response_data.get("id"),
            )
        else:
            msg_id = response_data.get("id")
            log.info(
                "Sent embed to channel %s (source=%s, source_id=%s)",
                channel_id,
                source,
                source_id,
            )

        log_pk = _log_discord_message(
            channel_id=channel_id,
            embed_data=embed_data,
            source=source,
            source_id=source_id,
            status_code=response.status_code,
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
        log.error("Failed to send to channel %s: %s", channel_id, e)
        return None


def sync_send_v2_message(
    channel_id, v2_payload, source=None, source_id=None, forum_thread_name=None
):
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
                "Created V2 forum thread '%s' in %s (thread=%s)",
                forum_thread_name,
                channel_id,
                response_data.get("id"),
            )
        else:
            msg_id = response_data.get("id")
            log.info("Sent V2 message to %s", channel_id)

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
        log.error("Failed to send V2 message to %s: %s", channel_id, e)
        return None


def sync_edit_v2_message(channel_id, message_id, v2_payload):
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
        log.info("Edited V2 message %s in %s", message_id, channel_id)
        return response.json()
    except requests.RequestException as e:
        log.error("Failed to edit V2 message %s: %s", message_id, e)
        return None


def sync_edit_message(channel_id, message_id, embed=None, components=None):
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

    payload = {}
    if embed:
        payload["embeds"] = embed if isinstance(embed, list) else [embed]
    if components is not None:
        payload["components"] = components

    try:
        response = _rate_limited_request(
            "PATCH", url, json=payload, headers=_get_headers()
        )
        response.raise_for_status()
        log.info(f"Edited message {message_id} in channel {channel_id}")
        return response.json()
    except requests.RequestException as e:
        log.error(f"Failed to edit message {message_id}: {e}")
        return None


def sync_create_dm_channel(user_id):
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
        log.error("Failed to create DM channel for user %s: %s", user_id, e)
        return None


def sync_send_dm(
    user_id, embed=None, content=None, components=None, tournament_log_id=None
):
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
                "TEST mode: skipping DM to %s (only sending to test user %s)",
                user_id,
                test_user_id,
            )
            return {"id": "test-fake-message-id", "test_skipped": True}

    dm_channel_id = sync_create_dm_channel(user_id)
    if not dm_channel_id:
        return None

    url = f"{DISCORD_API_BASE}/channels/{dm_channel_id}/messages"
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    if components:
        payload["components"] = components

    if not payload:
        log.warning("sync_send_dm called with no content or embed")
        return None

    try:
        response = _rate_limited_request(
            "POST", url, json=payload, headers=_get_headers()
        )
        response.raise_for_status()
        data = response.json()
        log.info("Sent DM to user %s (message_id=%s)", user_id, data.get("id"))
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
        log.error("Failed to send DM to user %s: %s", user_id, e)
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


def sync_add_reactions(channel_id, message_id, emojis=None):
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
            log.error(f"Failed to add reaction {emoji}: {e}")
