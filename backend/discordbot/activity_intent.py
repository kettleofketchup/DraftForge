from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from redis.exceptions import RedisError

from app.redis_keys import namespaced_key
from discordbot.utils import redis_client
from telemetry.logging import get_logger

log = get_logger(__name__)

INTENT_TTL_SECONDS = 300

IntentKind = Literal["hero", "team"]
IntentOp = Literal["record", "peek", "consume"]

_CONSUME = redis_client.register_script(
    """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, data = pcall(cjson.decode, raw)
if not ok or type(data) ~= 'table' or data['intent_id'] ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
return 1
"""
)


def intent_key(discord_user_id: str) -> str:
    return namespaced_key(f"activity:launch_intent:{discord_user_id}")


@dataclass(frozen=True)
class LaunchIntent:
    intent_id: str
    kind: IntentKind
    draft_id: int
    tournament_id: int | None
    guild_id: str
    channel_id: str
    created_at: str

    def applies_to(self, guild_id: str, channel_id: str) -> bool:
        return self.guild_id == guild_id and self.channel_id == channel_id

    def ref(self) -> dict[str, object]:
        return {"intent_id": self.intent_id, "kind": self.kind, "id": self.draft_id}


def _redis_failed(op: IntentOp, exc: RedisError) -> None:
    log.warning(
        "activity_intent_redis_failed",
        system="discord",
        subsystem="activity",
        op=op,
        error_type=type(exc).__name__,
    )


def _decode(raw: bytes | str) -> LaunchIntent | None:
    try:
        data = json.loads(raw)
        kind = data["kind"]
        if kind not in ("hero", "team"):
            return None
        tournament_id = data["tournament_id"]
        return LaunchIntent(
            intent_id=str(data["intent_id"]),
            kind=cast(IntentKind, kind),
            draft_id=int(data["draft_id"]),
            tournament_id=None if tournament_id is None else int(tournament_id),
            guild_id=str(data["guild_id"]),
            channel_id=str(data["channel_id"]),
            created_at=str(data["created_at"]),
        )
    except (ValueError, TypeError, KeyError):
        return None


def record_intent(
    discord_user_id: str,
    *,
    kind: str,
    draft_id: int,
    tournament_id: int | None,
    guild_id: str,
    channel_id: str,
) -> str | None:
    intent = LaunchIntent(
        intent_id=secrets.token_urlsafe(8),
        kind=cast(IntentKind, kind),
        draft_id=draft_id,
        tournament_id=tournament_id,
        guild_id=guild_id,
        channel_id=channel_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    try:
        redis_client.set(
            intent_key(discord_user_id),
            json.dumps(asdict(intent)),
            ex=INTENT_TTL_SECONDS,
        )
    except RedisError as exc:
        _redis_failed("record", exc)
        return None
    return intent.intent_id


def peek_intent(discord_user_id: str) -> LaunchIntent | None:
    try:
        raw = redis_client.get(intent_key(discord_user_id))
    except RedisError as exc:
        _redis_failed("peek", exc)
        return None
    if raw is None:
        return None
    return _decode(cast(bytes, raw))


def consume_intent(discord_user_id: str, intent_id: str) -> bool:
    try:
        result = _CONSUME(keys=[intent_key(discord_user_id)], args=[intent_id])
    except RedisError as exc:
        _redis_failed("consume", exc)
        return False
    return bool(result)
