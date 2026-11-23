import asyncio
import threading
from collections.abc import Callable
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from structlog.testing import capture_logs

from discordbot.bot import KettleBot
from discordbot.voice_feed import VoiceFeed

GUILD = 1
OTHER_GUILD = 2
WATCHED = 100
UNWATCHED = 200
OK: dict[str, Any] = {"success": True, "detail": "joined", "events": 1}


def _watched(*pairs: tuple[int, int]) -> dict[str, Any]:
    return {
        "available": True,
        "ttl_seconds": 60,
        "channels": [
            {"guild_id": str(g), "channel_id": str(c), "event_ids": [1]}
            for g, c in pairs
        ],
    }


UNAVAILABLE: dict[str, Any] = {"available": False, "channels": [], "ttl_seconds": 60}


def _state(channel_id: int | None) -> MagicMock:
    state = MagicMock()
    if channel_id is None:
        state.channel = None
    else:
        state.channel.id = channel_id
    return state


def _member(uid: int, *, bot: bool = False, guild_id: int = GUILD) -> MagicMock:
    member = MagicMock()
    member.id = uid
    member.bot = bot
    member.guild.id = guild_id
    return member


def _channel(guild_id: int, member_ids: list[int]) -> MagicMock:
    ch = MagicMock(spec=discord.VoiceChannel)
    ch.guild = MagicMock()
    ch.guild.id = guild_id
    ch.voice_states = {uid: MagicMock() for uid in member_ids}
    return ch


def _guild(
    channels: dict[int, MagicMock], bots: frozenset[int] = frozenset()
) -> MagicMock:
    guild = MagicMock()
    guild.get_channel.side_effect = channels.get

    def get_member(uid: int) -> MagicMock:
        return _member(uid, bot=uid in bots)

    guild.get_member.side_effect = get_member
    return guild


def _client(guilds: dict[int, MagicMock]) -> MagicMock:
    client = MagicMock()
    client.get_guild.side_effect = guilds.get
    return client


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class VoiceFeedTestBase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.get_watched = MagicMock(return_value=_watched((GUILD, WATCHED)))
        self.report = MagicMock(return_value=OK)
        self.snapshot = MagicMock(return_value=OK)
        for name, mock in (
            ("get_watched_channels", self.get_watched),
            ("report_voice_state", self.report),
            ("post_voice_snapshot", self.snapshot),
        ):
            patcher = patch(f"discordbot.voice_feed.{name}", mock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.clock = _Clock()

    def make_feed(self, client: MagicMock | None = None) -> VoiceFeed:
        return VoiceFeed(client or _client({}), clock=self.clock)

    async def drain(self, feed: VoiceFeed) -> None:
        while not feed.queue.empty():
            await feed.run_one(feed.queue.get_nowait())


class VoiceStateHandlerTests(VoiceFeedTestBase):
    async def test_unwatched_channel_makes_no_calls_even_when_cache_expired_and_backend_down(
        self,
    ) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        self.get_watched.reset_mock()
        self.get_watched.return_value = UNAVAILABLE
        self.clock.now += 3600

        feed.on_voice_state_update(_member(5), _state(UNWATCHED), _state(300))
        feed.on_voice_state_update(_member(6), _state(None), _state(UNWATCHED))
        await self.drain(feed)

        self.get_watched.assert_not_called()
        self.report.assert_not_called()
        self.snapshot.assert_not_called()

    async def test_mute_toggle_same_channel_no_calls(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(5), _state(WATCHED), _state(WATCHED))
        self.assertEqual(feed.queue.qsize(), 0)

    async def test_bot_member_ignored(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(5, bot=True), _state(None), _state(WATCHED))
        self.assertEqual(feed.queue.qsize(), 0)

    async def test_watched_join_enqueues_one_state_job_with_member_guild_id(
        self,
    ) -> None:
        self.get_watched.return_value = _watched((999, WATCHED))
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(5), _state(None), _state(WATCHED))

        self.assertEqual(feed.queue.qsize(), 1)
        await self.drain(feed)
        self.report.assert_called_once_with(
            guild_id=str(GUILD),
            discord_user_id="5",
            before_channel_id=None,
            after_channel_id=str(WATCHED),
        )

    async def test_watched_leave_to_none_enqueues_state_job(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(5), _state(WATCHED), _state(None))

        self.assertEqual(feed.queue.qsize(), 1)
        await self.drain(feed)
        kwargs = self.report.call_args.kwargs
        self.assertEqual(kwargs["before_channel_id"], str(WATCHED))
        self.assertIsNone(kwargs["after_channel_id"])

    async def test_move_watched_to_unwatched_enqueues_state_job(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(5), _state(WATCHED), _state(UNWATCHED))

        self.assertEqual(feed.queue.qsize(), 1)
        await self.drain(feed)
        kwargs = self.report.call_args.kwargs
        self.assertEqual(kwargs["before_channel_id"], str(WATCHED))
        self.assertEqual(kwargs["after_channel_id"], str(UNWATCHED))

    async def test_queue_full_drops_state_job_with_warning(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        while not feed.queue.full():
            feed.queue.put_nowait(("snapshot", None))

        with capture_logs() as logs:
            feed.on_voice_state_update(_member(5), _state(None), _state(WATCHED))

        self.assertEqual(feed.queue.qsize(), 1000)
        self.assertIn("voice_queue_full", [e["event"] for e in logs])


class VoiceWorkerTests(VoiceFeedTestBase):
    async def _wait_for(self, cond: Callable[[], bool]) -> None:
        for _ in range(500):
            if cond():
                return
            await asyncio.sleep(0.01)
        self.fail("condition not reached")

    async def test_queued_updates_posted_in_order(self) -> None:
        release = threading.Event()
        calls: list[str] = []

        def side_effect(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs["discord_user_id"])
            if len(calls) == 1:
                release.wait(timeout=5)
            return OK

        self.report.side_effect = side_effect
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(1), _state(None), _state(WATCHED))
        feed.on_voice_state_update(_member(2), _state(WATCHED), _state(None))

        worker = asyncio.create_task(feed.worker())
        self.addAsyncCleanup(self._cancel, worker)

        await self._wait_for(lambda: len(calls) == 1)
        await asyncio.sleep(0.05)
        self.assertEqual(calls, ["1"])

        await asyncio.to_thread(release.set)
        await asyncio.wait_for(feed.queue.join(), timeout=5)
        self.assertEqual(calls, ["1", "2"])

    async def _cancel(self, task: asyncio.Task[None]) -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_worker_survives_job_exception(self) -> None:
        self.report.side_effect = [RuntimeError("boom"), OK]
        feed = self.make_feed()
        await feed.refresh_watched()
        feed.on_voice_state_update(_member(1), _state(None), _state(WATCHED))
        feed.on_voice_state_update(_member(2), _state(None), _state(WATCHED))

        with capture_logs() as logs:
            worker = asyncio.create_task(feed.worker())
            self.addAsyncCleanup(self._cancel, worker)
            await asyncio.wait_for(feed.queue.join(), timeout=5)

        self.assertEqual(self.report.call_count, 2)
        self.assertIn("voice_worker_job_failed", [e["event"] for e in logs])
        self.assertFalse(worker.done())

    async def test_enqueue_snapshot_coalesces(self) -> None:
        feed = self.make_feed()
        feed.enqueue_snapshot()
        feed.enqueue_snapshot()
        self.assertEqual(feed.queue.qsize(), 1)

    async def test_snapshot_built_at_dequeue(self) -> None:
        ch = _channel(GUILD, [5])
        feed = self.make_feed(_client({GUILD: _guild({WATCHED: ch})}))
        feed.mark_connected()
        feed.enqueue_snapshot()
        ch.voice_states = {5: MagicMock(), 6: MagicMock()}

        await feed.run_one(feed.queue.get_nowait())

        channels = self.snapshot.call_args.kwargs["channels"]
        self.assertEqual(
            channels, [{"channel_id": str(WATCHED), "member_ids": ["5", "6"]}]
        )
        feed.enqueue_snapshot()
        self.assertEqual(feed.queue.qsize(), 1)


class VoiceRefreshTests(VoiceFeedTestBase):
    async def test_refresh_only_after_ttl_and_failed_refresh_not_retried_before_ttl(
        self,
    ) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        await feed.refresh_watched()
        self.assertEqual(self.get_watched.call_count, 1)

        self.clock.now += 61
        self.get_watched.return_value = UNAVAILABLE
        await feed.refresh_watched()
        self.assertEqual(self.get_watched.call_count, 2)

        self.clock.now += 1
        await feed.refresh_watched()
        self.assertEqual(self.get_watched.call_count, 2)

        await feed.refresh_watched(force=True)
        self.assertEqual(self.get_watched.call_count, 3)

        self.clock.now += 61
        await feed.refresh_watched()
        self.assertEqual(self.get_watched.call_count, 4)

    async def test_refresh_keeps_previous_map_when_unavailable(self) -> None:
        feed = self.make_feed()
        await feed.refresh_watched()
        self.get_watched.return_value = UNAVAILABLE

        with capture_logs() as logs:
            await feed.refresh_watched(force=True)

        self.assertEqual(feed.watched, {WATCHED: GUILD})
        warnings = [e for e in logs if e["event"] == "voice_watched_unavailable"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["log_level"], "warning")

    async def test_refresh_logs_when_set_changes(self) -> None:
        feed = self.make_feed()
        with capture_logs() as logs:
            await feed.refresh_watched()
            await feed.refresh_watched(force=True)
        refreshed = [e for e in logs if e["event"] == "voice_watched_refreshed"]
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["count"], 1)
        self.assertEqual(refreshed[0]["system"], "discord")
        self.assertEqual(refreshed[0]["subsystem"], "voice")


class VoiceSnapshotTests(VoiceFeedTestBase):
    async def test_snapshot_groups_by_guild_and_reports_invisible_channels(
        self,
    ) -> None:
        self.get_watched.return_value = _watched(
            (GUILD, 100), (GUILD, 101), (OTHER_GUILD, 300)
        )
        g1 = _guild({100: _channel(GUILD, [7, 5])})
        g2 = _guild({300: _channel(OTHER_GUILD, [8])})
        feed = self.make_feed(_client({GUILD: g1, OTHER_GUILD: g2}))
        feed.mark_connected()

        with capture_logs() as logs:
            await feed.post_snapshots()

        calls = {c.kwargs["guild_id"]: c.kwargs for c in self.snapshot.call_args_list}
        self.assertEqual(set(calls), {str(GUILD), str(OTHER_GUILD)})
        self.assertEqual(
            calls[str(GUILD)]["channels"],
            [{"channel_id": "100", "member_ids": ["5", "7"]}],
        )
        self.assertEqual(calls[str(GUILD)]["missing_channel_ids"], ["101"])
        self.assertEqual(
            calls[str(OTHER_GUILD)]["channels"],
            [{"channel_id": "300", "member_ids": ["8"]}],
        )
        self.assertEqual(calls[str(OTHER_GUILD)]["missing_channel_ids"], [])
        posted = [e for e in logs if e["event"] == "voice_snapshot_posted"]
        self.assertEqual(len(posted), 2)
        g1_log = next(e for e in posted if e["guild_id"] == str(GUILD))
        self.assertEqual(g1_log["channel_count"], 1)
        self.assertEqual(g1_log["missing_count"], 1)
        self.assertEqual(g1_log["member_total"], 2)

    async def test_channel_in_other_guild_is_reported_missing(self) -> None:
        foreign = _channel(OTHER_GUILD, [5])
        feed = self.make_feed(_client({GUILD: _guild({WATCHED: foreign})}))
        feed.mark_connected()

        await feed.post_snapshots()

        kwargs = self.snapshot.call_args.kwargs
        self.assertEqual(kwargs["channels"], [])
        self.assertEqual(kwargs["missing_channel_ids"], [str(WATCHED)])

    async def test_text_channel_is_reported_missing(self) -> None:
        text = MagicMock(spec=discord.TextChannel)
        text.guild = MagicMock()
        text.guild.id = GUILD
        feed = self.make_feed(_client({GUILD: _guild({WATCHED: text})}))
        feed.mark_connected()

        await feed.post_snapshots()

        self.assertEqual(
            self.snapshot.call_args.kwargs["missing_channel_ids"], [str(WATCHED)]
        )

    async def test_stage_channel_is_accepted(self) -> None:
        stage = MagicMock(spec=discord.StageChannel)
        stage.guild = MagicMock()
        stage.guild.id = GUILD
        stage.voice_states = {5: MagicMock()}
        feed = self.make_feed(_client({GUILD: _guild({WATCHED: stage})}))
        feed.mark_connected()

        await feed.post_snapshots()

        self.assertEqual(
            self.snapshot.call_args.kwargs["channels"],
            [{"channel_id": str(WATCHED), "member_ids": ["5"]}],
        )

    async def test_unknown_guild_reports_all_channels_missing(self) -> None:
        self.get_watched.return_value = _watched((GUILD, 100), (GUILD, 101))
        feed = self.make_feed(_client({}))
        feed.mark_connected()

        await feed.post_snapshots()

        self.snapshot.assert_called_once_with(
            guild_id=str(GUILD), channels=[], missing_channel_ids=["100", "101"]
        )

    async def test_snapshot_drops_bot_members(self) -> None:
        guild = _guild({WATCHED: _channel(GUILD, [5, 9])}, bots=frozenset({9}))
        feed = self.make_feed(_client({GUILD: guild}))
        feed.mark_connected()

        await feed.post_snapshots()

        self.assertEqual(
            self.snapshot.call_args.kwargs["channels"],
            [{"channel_id": str(WATCHED), "member_ids": ["5"]}],
        )

    async def test_disconnected_snapshot_posts_nothing_then_resumes(self) -> None:
        feed = self.make_feed(_client({GUILD: _guild({WATCHED: _channel(GUILD, [5])})}))
        feed.mark_connected()
        feed.mark_disconnected()

        with capture_logs() as logs:
            await feed.post_snapshots()
            await feed.post_snapshots()

        self.snapshot.assert_not_called()
        skipped = [
            e for e in logs if e["event"] == "voice_snapshot_skipped_disconnected"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["log_level"], "info")

        feed.mark_connected()
        await feed.post_snapshots()
        self.snapshot.assert_called_once()


class BotIntentsTests(IsolatedAsyncioTestCase):
    async def test_bot_intents_include_voice_states(self) -> None:
        with patch(
            "discordbot.bot.discord.Intents.default",
            return_value=discord.Intents.none(),
        ):
            bot = KettleBot()
        self.assertIs(bot.intents.voice_states, True)


class BotWiringTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = KettleBot()
        self.feed = MagicMock()
        self.feed.refresh_watched = AsyncMock()
        self.feed.worker = AsyncMock()
        self.bot.voice_feed = self.feed

    def test_bot_owns_a_voice_feed(self) -> None:
        self.assertIsInstance(KettleBot().voice_feed, VoiceFeed)

    def _assert_resynced(self) -> None:
        self.feed.mark_connected.assert_called_once_with()
        self.feed.refresh_watched.assert_awaited_once_with(force=True)
        self.feed.enqueue_snapshot.assert_called_once_with()

    async def test_on_ready_and_on_resumed_resync(self) -> None:
        self.bot._connection.user = MagicMock(id=42)
        await self.bot.on_ready()
        self._assert_resynced()

        self.feed.reset_mock()
        await self.bot.on_resumed()
        self._assert_resynced()

    async def test_on_disconnect_marks_disconnected(self) -> None:
        await self.bot.on_disconnect()
        self.feed.mark_disconnected.assert_called_once_with()

    async def test_on_voice_state_update_delegates(self) -> None:
        m, b, a = MagicMock(), MagicMock(), MagicMock()
        await self.bot.on_voice_state_update(m, b, a)
        self.feed.on_voice_state_update.assert_called_once_with(m, b, a)

    async def test_setup_hook_starts_worker_and_loop(self) -> None:
        never = asyncio.Event()
        self.bot.wait_until_ready = AsyncMock(side_effect=never.wait)
        with (
            patch.object(self.bot.tree, "copy_global_to"),
            patch.object(self.bot.tree, "sync", new=AsyncMock()),
        ):
            await self.bot.setup_hook()

        self.addAsyncCleanup(self._stop)
        self.assertIsNotNone(self.bot._voice_worker_task)
        self.assertFalse(self.bot._voice_worker_task.done())
        self.assertTrue(self.bot.voice_snapshot_loop.is_running())

    async def _stop(self) -> None:
        self.bot.voice_snapshot_loop.cancel()
        task = self.bot._voice_worker_task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_snapshot_loop_swallows_exceptions(self) -> None:
        self.feed.enqueue_snapshot.side_effect = RuntimeError("boom")
        with capture_logs() as logs:
            await self.bot.voice_snapshot_loop.coro(self.bot)
        failed = [e for e in logs if e["event"] == "voice_snapshot_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["system"], "discord")
        self.assertEqual(failed[0]["subsystem"], "voice")
