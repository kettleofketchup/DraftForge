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


def sync_send_embed(channel_id, title, description, color, fields=None, footer=None):
    """
    Send a rich embed to a Discord channel.

    Args:
        channel_id: Discord channel ID
        title: Embed title
        description: Embed description
        color: Integer color value (e.g., 0x00FF00)
        fields: Optional list of field dicts with 'name', 'value', 'inline'
        footer: Optional footer dict with 'text'

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
        response.raise_for_status()
        log.info(f"Sent embed to channel {channel_id}: {title}")
        return response.json()
    except requests.RequestException as e:
        log.error(f"Failed to send embed to channel {channel_id}: {e}")
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
    )


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
            response = requests.put(url, headers=_get_headers())
            response.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Failed to add reaction {emoji}: {e}")
