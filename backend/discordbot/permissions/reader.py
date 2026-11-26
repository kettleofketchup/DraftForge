import hashlib
import math
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Protocol

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from discordbot.permissions.evaluate import SnapshotBundle
from discordbot.permissions.schemas import (
    ChannelSnap,
    GuildSnap,
    MemberSnap,
    Observation,
    Overwrite,
    ReasonCode,
    RoleSnap,
    ThreadMeta,
)
from telemetry.logging import get_logger

log = get_logger(__name__)
_ID = re.compile(r"^[0-9]{17,20}$")
_READ_WORKERS = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="discord-permissions"
)
_READ_SLOTS = threading.BoundedSemaphore(4)


def _release_read_slot(future: Future[Any]) -> None:
    _READ_SLOTS.release()


class SnapshotSource(Protocol):
    def get(self, path: str, timeout: float) -> tuple[int, Any, dict[str, str]]: ...


class RestSource:
    def __init__(self) -> None:
        self.token: str = settings.DISCORD_BOT_TOKEN

    def get(self, path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
        response = requests.get(
            f"{settings.DISCORD_API_BASE_URL.rstrip('/')}{path}",
            headers={"Authorization": f"Bot {self.token}"},
            timeout=timeout,
            allow_redirects=False,
        )
        try:
            data: Any = None
            if response.status_code == 200:
                data = response.json()
            elif response.status_code == 429:
                try:
                    data = response.json()
                except ValueError:
                    data = None
            return response.status_code, data, dict(response.headers)
        finally:
            response.close()


class FixtureSource:
    def __init__(self, scenario: dict[str, Any]) -> None:
        self.scenario: dict[str, Any] = scenario

    def get(self, path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
        if path not in self.scenario:
            return 404, None, {}
        value = self.scenario[path]
        if isinstance(value, dict) and "status" in value:
            return value["status"], value.get("body"), value.get("headers", {})
        return 200, value, {}


def source_for(guild_id: str) -> SnapshotSource:
    if settings.TEST:
        scenario = cache.get(f"discord_perm_fixture:{guild_id}")
        if isinstance(scenario, dict):
            return FixtureSource(scenario)
    return RestSource()


def _id(value: Any) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Invalid snowflake")
    return value


def _bits(value: Any) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError("Invalid bitfield")


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise ValueError("Invalid boolean")
    return value


def _guild(data: Any, guild_id: str) -> GuildSnap:
    if _id(data["id"]) != guild_id:
        raise ValueError("Guild mismatch")
    roles: dict[str, RoleSnap] = {}
    for role in data["roles"]:
        rid = _id(role["id"])
        if rid in roles:
            raise ValueError("Duplicate role")
        roles[rid] = RoleSnap(
            rid,
            _bits(role["permissions"]),
            _bool(role["mentionable"]),
            _bool(role["managed"]),
        )
    if guild_id not in roles:
        raise ValueError("Missing everyone role")
    return GuildSnap(guild_id, _id(data["owner_id"]), roles)


def _member(data: Any, bot_id: str) -> MemberSnap:
    if _id(data["user"]["id"]) != bot_id or not isinstance(data["roles"], list):
        raise ValueError("Member mismatch")
    timeout = data["communication_disabled_until"]
    if timeout is not None:
        timeout = datetime.fromisoformat(timeout)
        if timeout.tzinfo is None or timeout.utcoffset() is None:
            raise ValueError("Naive timeout")
    return MemberSnap(bot_id, tuple(_id(r) for r in data["roles"]), timeout)


class _ForeignResource(ValueError):
    reason: ReasonCode = "resource_unavailable"


class _MalformedResource(_ForeignResource):
    reason: ReasonCode = "malformed_snapshot"


def _channel(data: Any, guild_id: str, *, listed: bool = False) -> ChannelSnap:
    if data.get("guild_id", guild_id if listed else None) != guild_id:
        raise _ForeignResource()
    kind = data["type"]
    if type(kind) is not int or kind < 0 or not isinstance(data["name"], str):
        raise ValueError("Invalid channel")
    parent = data.get("parent_id")
    if parent is not None:
        parent = _id(parent)
    overwrites: list[Overwrite] = []
    seen: set[tuple[int, str]] = set()
    for item in data.get("permission_overwrites", []):
        discriminator = item["type"]
        if type(discriminator) is not int or discriminator not in (0, 1):
            raise ValueError("Invalid overwrite")
        oid = _id(item["id"])
        if (discriminator, oid) in seen:
            raise ValueError("Duplicate overwrite")
        seen.add((discriminator, oid))
        overwrites.append(
            Overwrite(oid, discriminator, _bits(item["allow"]), _bits(item["deny"]))
        )
    meta = None
    if kind in (10, 11, 12):
        if parent is None:
            raise ValueError("Missing parent")
        metadata = data["thread_metadata"]
        meta = ThreadMeta(
            _bool(metadata["archived"]), _bool(metadata["locked"]), kind == 12, None
        )
    elif "permission_overwrites" not in data:
        raise ValueError("Missing overwrites")
    flags = _bits(data.get("flags", 0))
    return ChannelSnap(
        _id(data["id"]),
        guild_id,
        kind,
        data["name"],
        parent,
        tuple(overwrites),
        flags,
        meta,
        bool(flags & 16),
    )


@dataclass(frozen=True)
class _Read:
    value: Any
    error: ReasonCode | None
    observation: Observation
    retry_after: int | None = None


class SnapshotReader:
    def __init__(
        self,
        source: SnapshotSource,
        *,
        budget_s: float = 15.0,
        read_timeout_s: float = 5.0,
    ) -> None:
        self.source: SnapshotSource = source
        self.deadline: float = time.monotonic() + min(15.0, budget_s)
        self.read_timeout_s: float = min(5.0, read_timeout_s)
        self.token_fp: str = (
            "test-fixture-v1"
            if isinstance(source, FixtureSource)
            else hashlib.sha256(
                (
                    source.token
                    if isinstance(source, RestSource)
                    else settings.DISCORD_BOT_TOKEN
                ).encode()
            ).hexdigest()[:12]
        )
        self.refresh_state: Literal["fresh", "cached", "coalesced", "throttled"] = (
            "fresh"
        )
        self.observations: dict[str, Observation] = {}
        self.reads: dict[str, _Read] = {}
        self.channel_dependencies: dict[str, set[str]] = {}
        self._refresh: dict[str, bool] = {}
        self._guard: threading.Lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _get(self, path: str) -> tuple[int, Any, dict[str, str]]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or not _READ_SLOTS.acquire(timeout=remaining):
            raise requests.Timeout()
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise requests.Timeout()
            future = _READ_WORKERS.submit(
                self.source.get, path, min(self.read_timeout_s, remaining)
            )
        except BaseException:
            _READ_SLOTS.release()
            raise
        future.add_done_callback(_release_read_slot)
        try:
            return future.result(timeout=max(0, self.deadline - time.monotonic()))
        except TimeoutError as exc:
            # Running reads retain their slot; late results never reach the cache.
            future.cancel()
            raise requests.Timeout() from exc

    def _refresh_allowed(self, guild_id: str, refresh: bool) -> bool:
        with self._guard:
            if guild_id not in self._refresh:
                self._refresh[guild_id] = refresh and cache.add(
                    f"discord_perm_refresh:{self.token_fp}:{guild_id}", True, timeout=10
                )
                if refresh and not self._refresh[guild_id]:
                    self.refresh_state = "coalesced"
            return self._refresh[guild_id]

    def _read(
        self,
        guild_id: str,
        path: str,
        kind: str,
        parse: Callable[[Any], Any],
        refresh: bool,
        *,
        missing: ReasonCode = "resource_unavailable",
        absent_ok: bool = False,
    ) -> _Read:
        with self._guard:
            lock = self._locks.setdefault(path, threading.Lock())
        with lock:
            if path in self.reads:
                return self.reads[path]
            bypass = self._refresh_allowed(guild_id, refresh)
            key = f"discord_perm:v1:{self.token_fp}:{guild_id}:{kind}"
            cached = None if bypass else cache.get(key)
            if cached is not None and cached.observation.expires_at > timezone.now():
                entry = cached
                with self._guard:
                    if self.refresh_state == "fresh":
                        self.refresh_state = "cached"
            else:
                reason: ReasonCode | None = None
                value: Any = None
                retry: int | None = None
                foreign = False
                try:
                    if isinstance(self.source, RestSource) and not self.source.token:
                        reason = "credential_unavailable"
                    elif refresh and not bypass:
                        reason = "network_error"
                    else:
                        status, data, headers = self._get(path)
                        if time.monotonic() >= self.deadline:
                            raise requests.Timeout()
                        if status == 200:
                            value = parse(data)
                        elif status == 404 and absent_ok:
                            value = False
                        elif status == 429:
                            reason = "rate_limited"
                            raw = next(
                                (
                                    v
                                    for k, v in headers.items()
                                    if k.lower() == "retry-after"
                                ),
                                None,
                            )
                            if raw is None and isinstance(data, dict):
                                raw = data.get("retry_after")
                            try:
                                retry = max(0, math.ceil(float(raw)))
                            except (TypeError, ValueError, OverflowError):
                                retry = None
                        else:
                            reason = {
                                401: "credential_unavailable",
                                403: "forbidden_read",
                                404: missing,
                            }.get(status, "network_error")
                except _ForeignResource as exc:
                    reason, foreign = exc.reason, True
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    reason = "malformed_snapshot"
                except requests.RequestException:
                    reason = "network_error"
                observed = timezone.now()
                entry = _Read(
                    value,
                    reason,
                    Observation(
                        observed, observed + timedelta(seconds=10 if reason else 60)
                    ),
                    retry,
                )
                if (
                    not foreign
                    and not (refresh and not bypass)
                    and time.monotonic() < self.deadline
                ):
                    cache.set(key, entry, timeout=10 if reason else 60)
                if reason:
                    log.debug(
                        "permission_snapshot_failed",
                        system="discord",
                        subsystem="permissions",
                        guild_id=guild_id,
                        reason=reason,
                    )
                else:
                    log.debug(
                        "permission_snapshot_read",
                        system="discord",
                        subsystem="permissions",
                        guild_id=guild_id,
                        reason=None,
                    )
            self.reads[path] = entry
            self.observations[path] = entry.observation
            return entry

    def guild_bundle(self, guild_id: str, refresh: bool) -> SnapshotBundle:
        _id(guild_id)
        bot = self._read(
            guild_id,
            "/users/@me",
            "bot",
            lambda d: _id(d["id"]),
            refresh,
            missing="bot_unavailable",
        )
        if bot.error:
            return SnapshotBundle(
                None, None, bot.observation, bot.error, bot.retry_after
            )
        guild = self._read(
            guild_id,
            f"/guilds/{guild_id}",
            "guild",
            lambda d: _guild(d, guild_id),
            refresh,
            missing="bot_unavailable",
        )
        if guild.error:
            return SnapshotBundle(
                None, None, guild.observation, guild.error, guild.retry_after
            )
        member = self._read(
            guild_id,
            f"/guilds/{guild_id}/members/{bot.value}",
            "member",
            lambda d: _member(d, bot.value),
            refresh,
            missing="bot_unavailable",
        )
        reason = member.error
        if not reason and any(
            r not in guild.value.roles for r in member.value.role_ids
        ):
            reason = "malformed_snapshot"
        observations = [r.observation for r in (bot, guild, member)]
        observation = Observation(
            min(o.observed_at for o in observations),
            min(o.expires_at for o in observations),
        )
        return SnapshotBundle(
            guild.value, member.value, observation, reason, member.retry_after
        )

    def _channels(self, guild_id: str, refresh: bool) -> _Read:
        def parse(data: Any) -> dict[str, ChannelSnap]:
            if not isinstance(data, list):
                raise ValueError("Invalid channel list")
            channels = [_channel(d, guild_id, listed=True) for d in data]
            if len({c.id for c in channels}) != len(channels):
                raise ValueError("Duplicate channel")
            return {c.id: c for c in channels}

        return self._read(
            guild_id, f"/guilds/{guild_id}/channels", "channels", parse, refresh
        )

    def channel(
        self, guild_id: str, channel_id: str, refresh: bool
    ) -> tuple[ChannelSnap | None, ReasonCode | None]:
        _id(guild_id)
        _id(channel_id)
        listed = self._channels(guild_id, refresh)
        path = f"/guilds/{guild_id}/channels"
        entry = listed
        channel = listed.value.get(channel_id) if not listed.error else None
        if channel is None:
            path = f"/channels/{channel_id}"

            def parse_channel(data: Any) -> ChannelSnap:
                channel = _channel(data, guild_id)
                if channel.id != channel_id:
                    raise _MalformedResource()
                return channel

            entry = self._read(
                guild_id, path, f"channel:{channel_id}", parse_channel, refresh
            )
            channel = entry.value
        dependencies = {path}
        self.channel_dependencies[channel_id] = dependencies
        if entry.error or channel is None:
            return None, entry.error
        if channel.type == 12:
            bot = self._read(
                guild_id,
                "/users/@me",
                "bot",
                lambda d: _id(d["id"]),
                refresh,
                missing="bot_unavailable",
            )
            if bot.error:
                return channel, bot.error
            path = f"/channels/{channel_id}/thread-members/{bot.value}"

            def parse_member(data: Any) -> bool:
                if _id(data["user_id"]) != bot.value or _id(data["id"]) != channel_id:
                    raise ValueError("Thread member mismatch")
                return True

            member = self._read(
                guild_id,
                path,
                f"thread-member:{channel_id}",
                parse_member,
                refresh,
                absent_ok=True,
            )
            dependencies.add(path)
            channel = replace(
                channel,
                thread_meta=replace(channel.thread_meta, bot_is_member=member.value),
            )
            return channel, member.error
        return channel, None

    def scheduled_event_creator(
        self, guild_id: str, event_id: str, refresh: bool
    ) -> tuple[str | None, ReasonCode | None]:
        _id(guild_id)
        _id(event_id)

        def parse(data: Any) -> str | None:
            if _id(data["guild_id"]) != guild_id or _id(data["id"]) != event_id:
                raise _ForeignResource()
            return (
                _id(data["creator_id"]) if data.get("creator_id") is not None else None
            )

        entry = self._read(
            guild_id,
            f"/guilds/{guild_id}/scheduled-events/{event_id}",
            f"event:{event_id}",
            parse,
            refresh,
        )
        return entry.value, entry.error

    def message_author(
        self, guild_id: str, channel_id: str, message_id: str, refresh: bool
    ) -> tuple[str | None, ReasonCode | None]:
        _id(message_id)
        channel, error = self.channel(guild_id, channel_id, refresh)
        if channel is None or error:
            return None, error or "resource_unavailable"

        def parse(data: Any) -> str:
            if _id(data["channel_id"]) != channel_id or _id(data["id"]) != message_id:
                raise ValueError("Message mismatch")
            return _id(data["author"]["id"])

        entry = self._read(
            guild_id,
            f"/channels/{channel_id}/messages/{message_id}",
            f"message:{channel_id}:{message_id}",
            parse,
            refresh,
        )
        return entry.value, entry.error
