"""Voice presence feed: reports watched-channel voice changes and snapshots.

Runs inside the bot process and talks to the backend only through
``discordbot.internal_client.voice_actions``. Every HTTP call goes through
one serial queue so reports reach the backend in gateway order.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

import discord
from asgiref.sync import sync_to_async

from discordbot.internal_client.voice_actions import (
    get_watched_channels,
    post_voice_snapshot,
    report_voice_state,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

QUEUE_MAXSIZE = 1000

VoiceJob = tuple[Literal["state"], dict[str, Any]] | tuple[Literal["snapshot"], None]


def _channel_id(state: discord.VoiceState) -> int | None:
    channel = state.channel
    return channel.id if channel is not None else None


class VoiceFeed:
    def __init__(
        self,
        client: discord.Client,
        *,
        ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.watched: dict[int, set[int]] = {}
        self.watched_at: float | None = None
        self.gateway_connected: bool = False
        self.queue: asyncio.Queue[VoiceJob] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._watch_lock = asyncio.Lock()
        self._snapshot_queued = False
        self._skip_logged = False

    def mark_connected(self) -> None:
        self.gateway_connected = True
        self._skip_logged = False

    def mark_disconnected(self) -> None:
        self.gateway_connected = False

    async def refresh_watched(self, *, force: bool = False) -> None:
        async with self._watch_lock:
            if (
                not force
                and self.watched_at is not None
                and self.clock() - self.watched_at < self.ttl_seconds
            ):
                return
            result = await sync_to_async(get_watched_channels, thread_sensitive=False)()
            self.watched_at = self.clock()
            if not result.get("available"):
                log.warning(
                    "voice_watched_unavailable",
                    system="discord",
                    subsystem="voice",
                    count=len(self.watched),
                )
                return
            watched: dict[int, set[int]] = {}
            for row in result.get("channels", []):
                watched.setdefault(int(row["channel_id"]), set()).add(
                    int(row["guild_id"])
                )
            if watched != self.watched:
                self.watched = watched
                log.info(
                    "voice_watched_refreshed",
                    system="discord",
                    subsystem="voice",
                    count=len(watched),
                )

    def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        before_id = _channel_id(before)
        after_id = _channel_id(after)
        if before_id == after_id:
            return
        if before_id not in self.watched and after_id not in self.watched:
            return
        job: dict[str, Any] = {
            "guild_id": str(member.guild.id),
            "discord_user_id": str(member.id),
            "before_channel_id": str(before_id) if before_id is not None else None,
            "after_channel_id": str(after_id) if after_id is not None else None,
        }
        try:
            self.queue.put_nowait(("state", job))
        except asyncio.QueueFull:
            log.warning(
                "voice_queue_full",
                system="discord",
                subsystem="voice",
                guild_id=job["guild_id"],
                discord_user_id=job["discord_user_id"],
            )

    def enqueue_snapshot(self) -> None:
        if self._snapshot_queued:
            return
        try:
            self.queue.put_nowait(("snapshot", None))
        except asyncio.QueueFull:
            log.warning("voice_queue_full", system="discord", subsystem="voice")
            return
        self._snapshot_queued = True

    async def run_one(self, job: VoiceJob) -> None:
        kind, payload = job
        if kind == "snapshot":
            self._snapshot_queued = False
            await self.post_snapshots()
            return
        if payload is None:
            return
        result = await sync_to_async(report_voice_state, thread_sensitive=False)(
            **payload
        )
        if not result.get("success"):
            log.warning(
                "voice_state_report_failed",
                system="discord",
                subsystem="voice",
                guild_id=payload["guild_id"],
                discord_user_id=payload["discord_user_id"],
                detail=result.get("detail"),
            )
            return
        log.debug(
            "voice_state_reported",
            system="discord",
            subsystem="voice",
            guild_id=payload["guild_id"],
            discord_user_id=payload["discord_user_id"],
            detail=result.get("detail"),
            events=result.get("events"),
            joined=result.get("joined"),
            left=result.get("left"),
            confirmed=result.get("confirmed"),
        )

    async def worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self.run_one(job)
            except Exception:
                log.exception(
                    "voice_worker_job_failed",
                    system="discord",
                    subsystem="voice",
                    job=job[0],
                )
            finally:
                self.queue.task_done()

    def _guild_channels(
        self, guild_id: int, channel_ids: list[int]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        guild = self.client.get_guild(guild_id)
        if guild is None or guild.unavailable:
            return [], [str(cid) for cid in channel_ids]
        channels: list[dict[str, Any]] = []
        missing: list[str] = []
        for cid in channel_ids:
            ch = guild.get_channel(cid)
            if (
                not isinstance(ch, discord.VoiceChannel | discord.StageChannel)
                or ch.guild.id != guild_id
            ):
                missing.append(str(cid))
                continue
            member_ids: list[str] = []
            for uid in sorted(ch.voice_states):
                member = guild.get_member(uid)
                if member is not None and member.bot:
                    continue
                member_ids.append(str(uid))
            channels.append({"channel_id": str(cid), "member_ids": member_ids})
        return channels, missing

    def _can_snapshot(self) -> bool:
        if self.gateway_connected:
            return True
        if not self._skip_logged:
            self._skip_logged = True
            log.info(
                "voice_snapshot_skipped_disconnected",
                system="discord",
                subsystem="voice",
            )
        return False

    async def post_snapshots(self) -> None:
        if not self._can_snapshot():
            return
        await self.refresh_watched()
        by_guild: dict[int, list[int]] = defaultdict(list)
        for cid, guild_ids in self.watched.items():
            for gid in guild_ids:
                by_guild[gid].append(cid)
        for gid in sorted(by_guild):
            if not self._can_snapshot():
                return
            channels, missing = self._guild_channels(gid, sorted(by_guild[gid]))
            result = await sync_to_async(post_voice_snapshot, thread_sensitive=False)(
                guild_id=str(gid), channels=channels, missing_channel_ids=missing
            )
            if not result.get("success"):
                log.warning(
                    "voice_snapshot_post_failed",
                    system="discord",
                    subsystem="voice",
                    guild_id=str(gid),
                    detail=result.get("detail"),
                )
                continue
            log.info(
                "voice_snapshot_posted",
                system="discord",
                subsystem="voice",
                guild_id=str(gid),
                channel_count=len(channels),
                missing_count=len(missing),
                member_total=sum(len(c["member_ids"]) for c in channels),
            )
