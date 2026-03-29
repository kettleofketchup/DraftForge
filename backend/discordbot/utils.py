# backend/discordbot/utils.py
"""Admin utility functions for sending Discord messages."""

import logging

import requests
from django.conf import settings

from .embeds import event_announcement_embed

log = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


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
):
    """Log a Discord message send via the internal API (HTTP, not direct DB).

    Retries once on failure. No direct DB fallback — all writes must go through
    the internal API to prevent SQLite lock contention.
    """
    import time

    from app.internal_client import create_message_log

    for attempt in range(2):
        resp = create_message_log(
            channel_id=str(channel_id),
            embed_data=embed_data,
            source=source or "unknown",
            source_id=source_id,
            status_code=status_code,
            response_data=response_data,
            discord_message_id=discord_message_id,
            success=success,
        )
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
        response = requests.post(url, json=payload, headers=_get_headers())
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
        response = requests.post(url, json=payload, headers=_get_headers())
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
        response = requests.post(url, json=payload, headers=_get_headers())
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
        response = requests.patch(url, json=v2_payload, headers=_get_headers())
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
        response = requests.patch(url, json=payload, headers=_get_headers())
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
        response = requests.post(url, json=payload, headers=_get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get("id")
    except requests.RequestException as e:
        log.error("Failed to create DM channel for user %s: %s", user_id, e)
        return None


def sync_send_dm(user_id, embed=None, content=None):
    """Send a DM to a Discord user.

    Creates a DM channel then sends a message with optional embed.

    Args:
        user_id: Discord user ID
        embed: Optional embed dict
        content: Optional text content

    Returns:
        dict: API response with message data, or None on error
    """
    dm_channel_id = sync_create_dm_channel(user_id)
    if not dm_channel_id:
        return None

    url = f"{DISCORD_API_BASE}/channels/{dm_channel_id}/messages"
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]

    if not payload:
        log.warning("sync_send_dm called with no content or embed")
        return None

    try:
        response = requests.post(url, json=payload, headers=_get_headers())
        response.raise_for_status()
        data = response.json()
        log.info("Sent DM to user %s (message_id=%s)", user_id, data.get("id"))
        return data
    except requests.RequestException as e:
        log.error("Failed to send DM to user %s: %s", user_id, e)
        return None


def sync_add_reactions(channel_id, message_id, emojis=None):
    """
    Add reaction emojis to a message for RSVP.

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID
        emojis: List of emoji strings (defaults to RSVP emojis)
    """
    import time

    if emojis is None:
        emojis = ["\u2705", "\u2753", "\u274c"]  # checkmark, question, x

    for i, emoji in enumerate(emojis):
        if i > 0:
            time.sleep(0.3)  # Discord rate limits reactions at ~1/s
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        try:
            response = requests.put(url, headers=_get_headers())
            response.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Failed to add reaction {emoji}: {e}")
