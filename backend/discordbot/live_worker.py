"""Edit existing bot messages through Discord; all queue access goes over HTTP."""

import math

import redis
import requests
from django.conf import settings

from app.internal_client.transport import InternalAPIUnavailable
from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from discordbot.http_evidence import discord_error_code, response_json
from discordbot.internal_client.live_messages import claim_edit, finish_edit
from discordbot.schemas import LiveEditClaim, LiveEditFinish
from discordbot.utils import (
    DiscordAuthError,
    _retry_after_seconds,
    request_v2_message_edit,
)
from telemetry.logging import get_logger

log = get_logger(__name__)
BATCH_SIZE = 20
_PAUSE_KEY = "discord:live_edits:pause"
_LOG = {"system": "discord", "subsystem": "live_edits"}


def cooldown_remaining() -> float:
    key = namespaced_key(_PAUSE_KEY)
    try:
        return max(0, get_redis_client().pttl(key)) / 1000
    except redis.RedisError:
        # Match the shared Discord token bucket's Redis outage behavior.
        log.warning("live_edit_cooldown_unavailable", **_LOG)
        return 0


def pause_live_edits(seconds: float) -> None:
    key = namespaced_key(_PAUSE_KEY)
    ttl_ms = max(1, math.ceil(min(365 * 24 * 3600, seconds) * 1000))
    try:
        # One transaction: concurrent workers may lengthen, never shorten, a pause.
        with get_redis_client().pipeline() as pipe:
            pipe.set(key, "1", nx=True, px=ttl_ms)
            pipe.pexpire(key, ttl_ms, gt=True)
            pipe.execute()
    except redis.RedisError:
        log.warning("live_edit_cooldown_unavailable", **_LOG)


def apply_edit(claim: LiveEditClaim) -> LiveEditFinish:
    # The lease covers one bounded request. The durable queue owns 429 delays,
    # so a sleeping worker cannot wake after its lease and PATCH an old layout.
    payload = {
        "components": claim.payload.components,
        "allowed_mentions": {"parse": []},
    }
    # Another worker may have learned of a global limit while we claimed.
    remaining = cooldown_remaining()
    if remaining > 0:
        return LiveEditFinish(token=claim.token, outcome="retry", retry_after=remaining)
    try:
        response = request_v2_message_edit(
            claim.channel_id, claim.message_id, payload, max_retries=1
        )
    except DiscordAuthError:
        raise
    except requests.RequestException:
        return LiveEditFinish(token=claim.token, outcome="retry")

    status = response.status_code
    if status == 200:
        body = response_json(response)
        if (
            isinstance(body, dict)
            and body.get("id") == claim.message_id
            and body.get("channel_id") == claim.channel_id
        ):
            return LiveEditFinish(token=claim.token, outcome="edited")
    code = discord_error_code(response)
    if status == 429:
        delay = _retry_after_seconds(response)
        body = response_json(response)
        if (
            isinstance(body, dict)
            and body.get("global") is True
            or response.headers.get("X-RateLimit-Scope") == "global"
            or response.headers.get("X-RateLimit-Global", "").lower() == "true"
        ):
            pause_live_edits(delay)
        return LiveEditFinish(
            token=claim.token, outcome="retry", error_code=code, retry_after=delay
        )
    if status == 404 and code in (10003, 10008):
        return LiveEditFinish(token=claim.token, outcome="missing", error_code=code)
    if status in (400, 403):
        return LiveEditFinish(token=claim.token, outcome="blocked", error_code=code)
    return LiveEditFinish(token=claim.token, outcome="retry", error_code=code)


def drain_live_edits() -> int:
    if not getattr(settings, "DISCORD_BOT_TOKEN", ""):
        return 0

    recipient = None
    if getattr(settings, "TEST", False):
        recipient = str(getattr(settings, "TEST_DISCORD_USER_ID", "") or "")
        if not recipient:
            return 0

    acknowledged = 0
    try:
        for _ in range(BATCH_SIZE):
            if cooldown_remaining() > 0:
                break
            claim = claim_edit(discord_user_id=recipient)
            if claim is None:
                break
            try:
                result = apply_edit(claim)
            except DiscordAuthError:
                pause_live_edits(60)
                finish_edit(
                    claim.id,
                    LiveEditFinish(token=claim.token, outcome="retry", retry_after=60),
                )
                log.error("live_edit_bot_auth_rejected", **_LOG)
                break
            if finish_edit(claim.id, result):
                acknowledged += 1
            if result.retry_after is not None:
                # A global 429 can affect other messages too. Yield this batch.
                break
    except InternalAPIUnavailable:
        # A lost acknowledgement leaves the lease recoverable on a later beat.
        log.warning("live_edit_internal_api_unavailable", **_LOG)
    return acknowledged
