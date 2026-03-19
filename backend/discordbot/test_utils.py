"""
Test utilities for verifying Discord message delivery.
"""

import logging
import time

import requests
from django.conf import settings

from discordbot.models import DiscordMessageLog
from discordbot.utils import DISCORD_API_BASE, _get_headers

logger = logging.getLogger(__name__)


def wait_for_discord_log(source, source_id, timeout=10, poll_interval=0.5):
    """Poll DiscordMessageLog until an entry appears. Returns log entry or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        log = (
            DiscordMessageLog.objects.filter(source=source, source_id=source_id)
            .order_by("-created_at")
            .first()
        )
        if log:
            return log
        time.sleep(poll_interval)
    return None


def fetch_channel_messages(channel_id, limit=10):
    """Fetch recent messages from a Discord channel via REST API."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    params = {"limit": limit}
    try:
        response = requests.get(url, params=params, headers=_get_headers())
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch messages from channel {channel_id}: {e}")
        return []


def assert_discord_message_delivered(log_entry):
    """Verify a logged message was delivered by reading it back from Discord."""
    if not log_entry.discord_message_id:
        return False
    messages = fetch_channel_messages(log_entry.channel_id)
    for msg in messages:
        if msg.get("id") == log_entry.discord_message_id:
            return True
    return False


def fetch_message(channel_id, message_id):
    """Fetch a single message from Discord by ID."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    try:
        response = requests.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch message {message_id}: {e}")
        return None


def get_message_reactions(channel_id, message_id):
    """Get reaction emojis on a message. Returns list of emoji strings, e.g. ['✅', '❌']."""
    msg = fetch_message(channel_id, message_id)
    if not msg or "reactions" not in msg:
        return []
    return [r["emoji"]["name"] for r in msg["reactions"]]


def get_test_bot_tokens():
    """Return available test bot tokens. Warns if none configured."""
    tokens = {}
    main = getattr(settings, "DISCORD_BOT_TOKEN", "")
    bot2 = getattr(settings, "DISCORD_TEST_BOT_2_TOKEN", "")
    bot3 = getattr(settings, "DISCORD_TEST_BOT_3_TOKEN", "")
    if main:
        tokens["main"] = main
    if bot2:
        tokens["player1"] = bot2
    if bot3:
        tokens["player2"] = bot3
    return tokens


def add_reaction_as(token, channel_id, message_id, emoji):
    """Add a reaction to a message using a specific bot token."""
    import urllib.parse

    encoded = urllib.parse.quote(emoji)
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.put(url, headers=headers)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to add reaction {emoji} with token ...{token[-6:]}: {e}")
        return False


def get_bot_user_id(token):
    """Get the Discord user ID for a bot token via GET /users/@me."""
    url = f"{DISCORD_API_BASE}/users/@me"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("id")
    except requests.RequestException as e:
        logger.error(f"Failed to get bot user ID: {e}")
        return None


def delete_discord_message(channel_id, message_id):
    """Delete a message from a Discord channel. Used in test tearDown."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    try:
        response = requests.delete(url, headers=_get_headers())
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.warning(f"Failed to delete message {message_id}: {e}")
        return False


def cleanup_test_messages(source_prefix="integration_test"):
    """Delete all Discord messages created by integration tests."""
    logs = DiscordMessageLog.objects.filter(
        source__startswith=source_prefix,
        success=True,
        discord_message_id__isnull=False,
    )
    for log in logs:
        delete_discord_message(log.channel_id, log.discord_message_id)
    logs.delete()
