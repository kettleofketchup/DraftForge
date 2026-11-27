"""Test-stack stand-in for the Discord calls an Activity session makes.

Playwright cannot reach Discord, so on a TEST stack the three server-side
calls behind ``activity_session`` are answered here instead: the OAuth code
exchange, ``/users/@me`` and the activity-instance lookup. Every entry point
is inert unless ``settings.TEST`` is on and ``settings.RELEASE`` is off.

Registered instances live in the bot Redis DB under a namespaced key, not the
Django cache: reset endpoints flush every cache key while other specs run.
"""

import json
import re
from typing import Any, cast

import requests
from django.conf import settings

from app.redis_keys import namespaced_key
from discordbot.utils import redis_client
from telemetry.logging import get_logger

log = get_logger(__name__)

FAKE_CLIENT_ID = "100000000000000001"
FAKE_PREFIX = "e2e-"
INSTANCE_TTL_S = 60 * 60

_INSTANCE_PATH = re.compile(
    r"^/applications/[^/]+/activity-instances/([A-Za-z0-9_-]+)$"
)


def active() -> bool:
    return bool(getattr(settings, "TEST", False)) and not getattr(
        settings, "RELEASE", False
    )


class FakeInstanceMissing(requests.RequestException):
    """A fake instance ID with no registration; Discord would not know it either."""


def _instance_key(instance_id: str) -> str:
    return namespaced_key(f"activity_fake_instance:{instance_id}")


def fake_code(discord_id: str) -> str:
    return f"{FAKE_PREFIX}{discord_id}"


def client_id() -> str | None:
    """The configured application ID, or the fake one on an unconfigured TEST stack."""
    configured = getattr(settings, "SOCIAL_AUTH_DISCORD_KEY", None)
    if configured or not active():
        return configured
    return FAKE_CLIENT_ID


def register_instance(
    instance_id: str, guild_id: str, channel_id: str, users: list[str]
) -> None:
    if not active():
        return
    redis_client.set(
        _instance_key(instance_id),
        json.dumps(
            {
                "id": instance_id,
                "users": [str(u) for u in users],
                "location": {
                    "kind": "gc",
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                },
            }
        ),
        ex=INSTANCE_TTL_S,
    )
    log.info(
        "activity_fake_instance_registered",
        system="discord",
        subsystem="activity",
        instance_id=instance_id,
        guild_id=str(guild_id),
        channel_id=str(channel_id),
    )


def _fake_discord_id(value: object) -> str | None:
    if isinstance(value, str) and value.startswith(FAKE_PREFIX):
        discord_id = value[len(FAKE_PREFIX) :]
        if discord_id.isdigit():
            return discord_id
    return None


def answer(method: str, path: str, kwargs: dict[str, Any]) -> dict[str, Any] | None:
    """A canned Discord response for a fake identity, or None to call Discord."""
    if not active():
        return None
    if method == "POST" and path == "/oauth2/token":
        discord_id = _fake_discord_id((kwargs.get("data") or {}).get("code"))
        return None if discord_id is None else {"access_token": fake_code(discord_id)}
    if method == "GET" and path == "/users/@me":
        bearer = (kwargs.get("headers") or {}).get("Authorization", "")
        discord_id = _fake_discord_id(bearer.removeprefix("Bearer "))
        return None if discord_id is None else {"id": discord_id}
    match = _INSTANCE_PATH.match(path)
    if method == "GET" and match:
        return _registered_instance(match.group(1))
    return None


def forget_instance(instance_id: str) -> None:
    redis_client.delete(_instance_key(instance_id))


def _registered_instance(instance_id: str) -> dict[str, Any] | None:
    raw = redis_client.get(_instance_key(instance_id))
    if raw is not None:
        return cast(dict[str, Any], json.loads(cast(bytes, raw)))
    if not instance_id.startswith(FAKE_PREFIX):
        return None
    log.warning(
        "activity_fake_instance_missing",
        system="discord",
        subsystem="activity",
        instance_id=instance_id,
    )
    raise FakeInstanceMissing(instance_id)
