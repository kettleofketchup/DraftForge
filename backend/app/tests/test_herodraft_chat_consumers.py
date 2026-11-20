import asyncio
import json
import uuid
from datetime import date, timedelta
from typing import Any
from unittest import mock

from asgiref.sync import async_to_sync, sync_to_async
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from django.urls import path, re_path
from django.utils import timezone
from structlog.testing import capture_logs

from app.broadcast import broadcast_herodraft_state
from app.consumers import HeroDraftConsumer
from app.functions.herodraft import new_herodraft_for_game
from app.functions.herodraft_chat import (
    RATE_LIMIT_MAX,
    ChatError,
    draft_roster_user_ids,
    rate_limit_key,
    resolve_chat_viewer,
    team_group_name,
)
from app.models import (
    CustomUser,
    Game,
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    HeroDraftRound,
    HeroDraftState,
    League,
    Organization,
    Team,
    Tournament,
)
from app.redis_client import get_redis_client
from app.services.team_management import follow_captain
from app.tests.ws_helpers import (
    assert_no_frame_except_ping,
    next_non_ping_output,
    read_until_type,
)
from discordbot.activity_auth import ActivitySocketMiddleware, issue_activity_token
from discordbot.models import DraftActivityChannel, DraftActivityInstance

Channel = HeroDraftChatMessage.Channel
Kind = HeroDraftChatMessage.Kind

type Viewer = CustomUser | AnonymousUser


class _RecordingConsumer(HeroDraftConsumer):
    instances: list["_RecordingConsumer"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        type(self).instances.append(self)


class ChatConsumerFixture(TransactionTestCase):
    def setUp(self) -> None:
        def user(name: str, **kw: Any) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x", **kw)

        self.cap_a = user("cc_cap_a")
        self.mem_a = user("cc_mem_a")
        self.cap_b = user("cc_cap_b")
        self.mem_b = user("cc_mem_b")
        self.spectator = user("cc_spectator")
        self.both = user("cc_both")
        self.superuser = CustomUser.objects.create_superuser(
            username="cc_super", password="x"
        )
        self.league_staff = user("cc_league_staff")
        self.org_admin = user("cc_org_admin")
        self.anonymous = AnonymousUser()

        org = Organization.objects.create(name="Chat Consumer Org")
        org.admins.add(self.org_admin)
        league = League.objects.create(name="Chat Consumer League", organization=org)
        league.staff.add(self.league_staff)
        self.tournament = Tournament.objects.create(
            name="Chat Consumer Tournament", date_played=date.today(), league=league
        )
        self.team_a = Team.objects.create(
            name="CC A", tournament=self.tournament, captain=self.cap_a
        )
        self.team_b = Team.objects.create(
            name="CC B", tournament=self.tournament, captain=self.cap_b
        )
        self.team_a.members.add(self.mem_a, self.both)
        self.team_b.members.add(self.mem_b, self.both)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_a,
            dire_team=self.team_b,
        )
        self.draft: HeroDraft = new_herodraft_for_game(self.game)
        self.draft.refresh_from_db()

        for roster_user, team in (
            (self.cap_a, self.team_a),
            (self.mem_a, self.team_a),
            (self.cap_b, self.team_b),
            (self.mem_b, self.team_b),
        ):
            row = HeroDraftChatMembership.objects.get(
                draft=self.draft, user=roster_user, left_at__isnull=True
            )
            self.assertEqual(row.team_id, team.pk)
            self.assertEqual(row.joined_at, self.draft.created_at)
        self.assertFalse(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=self.both
            ).exists()
        )

        _RecordingConsumer.instances = []
        self.comms: list[WebsocketCommunicator] = []
        redis_client = get_redis_client()
        for rate_user in CustomUser.objects.all():
            redis_client.delete(rate_limit_key(self.draft.pk, rate_user.pk))

    def application(self) -> URLRouter:
        return URLRouter(
            [
                re_path(
                    r"api/herodraft/(?P<draft_id>\d+)/$",
                    _RecordingConsumer.as_asgi(),
                )
            ]
        )

    def consumer_for(self, user: Viewer) -> _RecordingConsumer:
        matches = [c for c in _RecordingConsumer.instances if c.user is user]
        self.assertTrue(matches, f"no consumer for {user}")
        return matches[-1]

    async def connect_with_frames(
        self, user: Viewer, session: SessionBase | None = None
    ) -> tuple[WebsocketCommunicator, dict[str, Any], dict[str, Any]]:
        comm = WebsocketCommunicator(
            self.application(), f"/api/herodraft/{self.draft.pk}/"
        )
        comm.scope["user"] = user
        if session is not None:
            comm.scope["session"] = session
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        self.comms.append(comm)
        initial = await read_until_type(comm, "initial_state")
        history = await read_until_type(comm, "chat_history")
        return comm, initial, history

    async def connect_as(self, user: Viewer) -> WebsocketCommunicator:
        comm, _, _ = await self.connect_with_frames(user)
        return comm

    async def close_all(self) -> None:
        for comm in self.comms:
            await comm.disconnect()
        self.comms = []

    @database_sync_to_async
    def seed_history(self, sentinel: str) -> dict[str, str]:
        bodies = {
            "a": f"team-a {sentinel}",
            "b": f"team-b {sentinel}",
            "all": f"all {sentinel}",
        }
        for team, sender, key in (
            (self.team_a, self.mem_a, "a"),
            (self.team_b, self.mem_b, "b"),
        ):
            HeroDraftChatMessage.objects.create(
                draft=self.draft,
                channel=Channel.TEAM,
                team=team,
                sender=sender,
                kind=Kind.TEXT,
                body=bodies[key],
            )
        HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.ALL,
            team=None,
            sender=self.cap_b,
            kind=Kind.TEXT,
            body=bodies["all"],
        )
        return bodies

    @database_sync_to_async
    def set_state(self, state: str) -> None:
        HeroDraft.objects.filter(pk=self.draft.pk).update(state=state)

    @staticmethod
    def bodies(history: dict[str, Any]) -> list[str]:
        return [m["body"] for m in history["messages"]]


class ChatHistoryOnConnectTest(ChatConsumerFixture):
    async def assert_history(
        self,
        user: Viewer,
        role: str,
        team: Team | None,
        sentinel: str,
        bodies: dict[str, str],
    ) -> None:
        comm, initial, history = await self.connect_with_frames(user)
        self.assertEqual(set(initial), {"type", "draft_state", "server_time"})
        self.assertNotIn(sentinel, json.dumps(initial))
        self.assertEqual(history["viewer"]["role"], role)
        self.assertEqual(history["viewer"]["team_id"], team.pk if team else None)
        self.assertEqual(history["viewer"]["can_post_team"], role == "member")
        self.assertEqual(history["viewer"]["can_post_all"], role == "member")
        seen = self.bodies(history)
        expected = [bodies["a"]] if team == self.team_a else []
        expected += [bodies["b"]] if team == self.team_b else []
        expected.append(bodies["all"])
        self.assertEqual(seen, expected)
        own = {self.team_a: "a", self.team_b: "b"}.get(team) if team else None
        for key in ("a", "b"):
            if key != own:
                self.assertNotIn(bodies[key], json.dumps(history))
        await comm.disconnect()
        self.comms.remove(comm)

    async def test_history_per_role(self) -> None:
        sentinel = "hist-role-7d1c"
        bodies = await self.seed_history(sentinel)
        try:
            await self.assert_history(
                self.mem_a, "member", self.team_a, sentinel, bodies
            )
            await self.assert_history(
                self.cap_a, "member", self.team_a, sentinel, bodies
            )
            await self.assert_history(
                self.cap_b, "member", self.team_b, sentinel, bodies
            )
            await self.assert_history(
                self.mem_b, "member", self.team_b, sentinel, bodies
            )
            for viewer in (
                self.spectator,
                self.anonymous,
                self.superuser,
                self.league_staff,
                self.org_admin,
            ):
                await self.assert_history(viewer, "spectator", None, sentinel, bodies)
            await self.assert_history(self.both, "ambiguous", None, sentinel, bodies)
        finally:
            await self.close_all()

    async def test_chat_history_follows_initial_state(self) -> None:
        try:
            comm = WebsocketCommunicator(
                self.application(), f"/api/herodraft/{self.draft.pk}/"
            )
            comm.scope["user"] = self.mem_a
            self.comms.append(comm)
            await comm.connect()
            first = await comm.receive_json_from()
            second = await comm.receive_json_from()
            self.assertEqual(first["type"], "initial_state")
            self.assertEqual(second["type"], "chat_history")
            self.assertEqual(
                second["viewer"],
                {
                    "role": "member",
                    "team_id": self.team_a.pk,
                    "can_post_team": True,
                    "can_post_all": True,
                },
            )
        finally:
            await self.close_all()

    async def test_member_socket_joins_team_group_spectator_does_not(self) -> None:
        try:
            member = await self.connect_as(self.mem_a)
            other = await self.connect_as(self.mem_b)
            spectator = await self.connect_as(self.spectator)
            self.assertEqual(
                self.consumer_for(self.mem_a)._extra_groups,
                {team_group_name(self.draft.pk, self.team_a.pk)},
            )
            self.assertEqual(self.consumer_for(self.spectator)._extra_groups, set())
            await get_channel_layer().group_send(
                team_group_name(self.draft.pk, self.team_a.pk),
                {"type": "herodraft.event", "event_type": "group-probe-41aa"},
            )
            frame = await read_until_type(member, "herodraft_event")
            self.assertEqual(frame["event_type"], "group-probe-41aa")
            await assert_no_frame_except_ping(other)
            await assert_no_frame_except_ping(spectator)
        finally:
            await self.close_all()

    async def test_disconnect_leaves_team_group(self) -> None:
        try:
            member = await self.connect_as(self.mem_a)
            consumer = self.consumer_for(self.mem_a)
            await member.disconnect()
            self.comms.remove(member)
            self.assertEqual(consumer._extra_groups, set())
        finally:
            await self.close_all()

    async def test_reconnect_sends_same_history(self) -> None:
        await self.seed_history("reconnect-93be")
        try:
            comm, _, first = await self.connect_with_frames(self.mem_a)
            await comm.disconnect()
            self.comms.remove(comm)
            _, _, second = await self.connect_with_frames(self.mem_a)
            self.assertEqual(first, second)
            self.assertEqual(len(first["messages"]), 2)
        finally:
            await self.close_all()

    async def test_bootstrap_failure_keeps_socket(self) -> None:
        with (
            mock.patch("app.consumers_base.PING_INTERVAL", 0.1),
            mock.patch(
                "app.consumers.visible_messages", side_effect=RuntimeError("boom")
            ),
            capture_logs() as logs,
        ):
            try:
                comm = WebsocketCommunicator(
                    self.application(), f"/api/herodraft/{self.draft.pk}/"
                )
                comm.scope["user"] = self.cap_a
                self.comms.append(comm)
                connected, _ = await comm.connect()
                self.assertTrue(connected)
                first = await comm.receive_json_from()
                self.assertEqual(first["type"], "initial_state")
                error = await comm.receive_json_from()
                self.assertEqual(error, {"type": "chat_error", "code": "unavailable"})
                await read_until_type(comm, "ping")
                consumer = self.consumer_for(self.cap_a)
                self.assertEqual(consumer._extra_groups, set())
                self.assertEqual(consumer._chat_viewer.role, "spectator")
            finally:
                await self.close_all()
        events = [entry["event"] for entry in logs]
        self.assertIn("herodraft_chat_bootstrap_failed", events)
        self.assertNotIn("initial_state_send_failed", events)
        failed = next(
            e for e in logs if e["event"] == "herodraft_chat_bootstrap_failed"
        )
        self.assertEqual(failed["system"], "herodraft")
        self.assertEqual(failed["subsystem"], "chat")

    async def test_completed_draft_history_stays_private(self) -> None:
        for state in (HeroDraftState.COMPLETED, HeroDraftState.ABANDONED):
            with self.subTest(state=state):
                await self.set_state(state)
                sentinel = f"closed-{state}-5e02"
                bodies = await self.seed_history(sentinel)
                try:
                    _, _, history = await self.connect_with_frames(self.mem_a)
                    self.assertIn(bodies["a"], self.bodies(history))
                    self.assertIn(bodies["all"], self.bodies(history))
                    self.assertNotIn(bodies["b"], json.dumps(history))
                    for viewer in (
                        self.mem_b,
                        self.spectator,
                        self.superuser,
                        self.league_staff,
                        self.org_admin,
                        self.anonymous,
                    ):
                        _, _, other = await self.connect_with_frames(viewer)
                        self.assertNotIn(bodies["a"], json.dumps(other))
                        self.assertIn(bodies["all"], self.bodies(other))
                        if viewer is not self.mem_b:
                            self.assertNotIn(bodies["b"], json.dumps(other))
                finally:
                    await self.close_all()


CHAT_FRAME_TYPES = frozenset({"chat_message", "chat_history", "chat_ack", "chat_error"})


async def drain(
    comm: WebsocketCommunicator, timeout: float = 0.5
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    while True:
        try:
            output = await next_non_ping_output(comm, timeout)
        except asyncio.TimeoutError:
            return frames
        frames.append(json.loads(output["text"]))


async def read_until_types(
    comm: WebsocketCommunicator, wanted: set[str], timeout: float = 5
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        try:
            output = await next_non_ping_output(comm, remaining)
        except asyncio.TimeoutError:
            raise AssertionError(f"timed out waiting for {sorted(wanted)}") from None
        frame = json.loads(output["text"])
        if frame.get("type") in wanted:
            return frame


async def read_history_with_role(
    comm: WebsocketCommunicator, role: str, timeout: float = 5
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        frame = await read_until_types(comm, {"chat_history"}, max(remaining, 0.001))
        if frame["viewer"]["role"] == role:
            return frame


class ChatSendFixture(ChatConsumerFixture):
    async def assert_no_chat_frame(
        self, comm: WebsocketCommunicator, *sentinels: str
    ) -> None:
        for frame in await drain(comm):
            self.assertNotIn(frame.get("type"), CHAT_FRAME_TYPES, frame)
            for sentinel in sentinels:
                self.assertNotIn(sentinel, json.dumps(frame))

    async def send_chat(
        self, comm: WebsocketCommunicator, body: Any, client_msg_id: str = "cid-1"
    ) -> dict[str, Any]:
        await comm.send_json_to(
            {"type": "chat_send", "body": body, "client_msg_id": client_msg_id}
        )
        return await read_until_types(comm, {"chat_ack", "chat_error"})

    async def suggest(
        self, comm: WebsocketCommunicator, kind: str, hero_id: Any
    ) -> dict[str, Any]:
        await comm.send_json_to(
            {
                "type": "chat_suggest",
                "kind": kind,
                "hero_id": hero_id,
                "client_msg_id": "sug-1",
            }
        )
        return await read_until_types(comm, {"chat_ack", "chat_error"})

    def outsiders(self) -> list[Viewer]:
        return [
            self.cap_b,
            self.mem_b,
            self.spectator,
            self.anonymous,
            self.both,
            self.superuser,
            self.league_staff,
            self.org_admin,
        ]

    @database_sync_to_async
    def stored(self, body: str) -> HeroDraftChatMessage:
        return HeroDraftChatMessage.objects.get(draft=self.draft, body=body)

    @database_sync_to_async
    def team_message(self, team: Team, sender: CustomUser, body: str) -> None:
        msg = HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.TEAM,
            team=team,
            sender=sender,
            kind=Kind.TEXT,
            body=body,
        )
        HeroDraftChatMessage.objects.filter(pk=msg.pk).update(
            created_at=timezone.now() - timedelta(seconds=1)
        )

    def raw_team_event(self, team: Team, body: str, created_at: str) -> dict[str, Any]:
        return {
            "type": "herodraft.chat_team",
            "team_id": team.pk,
            "message": {
                "id": str(uuid.uuid4()),
                "channel": "team",
                "team_id": team.pk,
                "kind": "text",
                "hero_id": None,
                "body": body,
                "created_at": created_at,
                "sender": {"pk": self.cap_a.pk, "username": "x"},
            },
        }

    @staticmethod
    def now_iso() -> str:
        return timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ChatSendTest(ChatSendFixture):
    async def test_t1_t2_t7_t11_team_text_reaches_only_own_team(self) -> None:
        sentinel = "t1-team-a8f2"
        try:
            cap_a = await self.connect_as(self.cap_a)
            mem_a = await self.connect_as(self.mem_a)
            others = [await self.connect_as(u) for u in self.outsiders()]
            await drain(mem_a, 0.2)

            reply = await self.send_chat(cap_a, sentinel)
            self.assertEqual(reply["type"], "chat_ack")
            self.assertEqual(reply["client_msg_id"], "cid-1")
            uuid.UUID(reply["id"])

            frame = await read_until_type(mem_a, "chat_message")
            message = frame["message"]
            self.assertEqual(message["body"], sentinel)
            self.assertEqual(message["channel"], "team")
            self.assertEqual(message["team_id"], self.team_a.pk)
            self.assertEqual(message["id"], reply["id"])
            self.assertNotIn("client_msg_id", json.dumps(frame))

            await asyncio.gather(
                *(self.assert_no_chat_frame(comm, sentinel) for comm in others)
            )
        finally:
            await self.close_all()

    async def test_t20_all_chat_reaches_everyone_without_private_ids(self) -> None:
        sentinel = "t20-all-55c1"
        try:
            sender = await self.connect_as(self.mem_b)
            viewers = [
                await self.connect_as(u)
                for u in (
                    self.cap_a,
                    self.mem_a,
                    self.cap_b,
                    self.spectator,
                    self.anonymous,
                    self.both,
                    self.superuser,
                )
            ]
            reply = await self.send_chat(sender, f"/ALL {sentinel}", "all-1")
            self.assertEqual(reply["type"], "chat_ack")
            own = await read_until_type(sender, "chat_message")
            self.assertEqual(own["message"]["channel"], "all")
            for comm in viewers:
                frame = await read_until_type(comm, "chat_message")
                message = frame["message"]
                self.assertEqual(message["body"], sentinel)
                self.assertEqual(message["channel"], "all")
                self.assertIsNone(message["team_id"])
                self.assertIsInstance(message["id"], str)
                uuid.UUID(message["id"])
                self.assertNotIn("client_msg_id", json.dumps(frame))
                self.assertNotIn("all-1", json.dumps(frame))
        finally:
            await self.close_all()

    async def test_t9_forged_channel_and_team_ignored(self) -> None:
        sentinel = "t9-forge-3b70"
        try:
            mem_a = await self.connect_as(self.mem_a)
            mem_b = await self.connect_as(self.mem_b)
            await mem_a.send_json_to(
                {
                    "type": "chat_send",
                    "body": sentinel,
                    "channel": "all",
                    "team_id": self.team_b.pk,
                    "client_msg_id": "forge-1",
                }
            )
            reply = await read_until_types(mem_a, {"chat_ack", "chat_error"})
            self.assertEqual(reply["type"], "chat_ack")
            row = await self.stored(sentinel)
            self.assertEqual(row.channel, Channel.TEAM)
            self.assertEqual(row.team_id, self.team_a.pk)
            await self.assert_no_chat_frame(mem_b, sentinel)
        finally:
            await self.close_all()

    async def test_t11_non_members_rejected_without_db_or_rate_limit(self) -> None:
        cases: list[tuple[Viewer, str]] = [
            (self.spectator, "not_participant"),
            (self.anonymous, "not_participant"),
            (self.superuser, "not_participant"),
            (self.league_staff, "not_participant"),
            (self.org_admin, "not_participant"),
            (self.both, "ambiguous_team"),
        ]
        try:
            comms = [(await self.connect_as(u), u, code) for u, code in cases]
            with (
                mock.patch("app.consumers.check_rate_limit") as rate,
                mock.patch("app.consumers.resolve_chat_viewer") as resolve,
                mock.patch("app.consumers.post_text") as post,
                mock.patch("app.consumers.post_suggestion") as suggest,
            ):
                for comm, user, code in comms:
                    with self.subTest(user=str(user)):
                        reply = await self.send_chat(comm, "/all t11-x", "t11")
                        self.assertEqual(
                            reply,
                            {
                                "type": "chat_error",
                                "code": code,
                                "client_msg_id": "t11",
                            },
                        )
                        reply = await self.suggest(comm, Kind.SUGGEST_BAN, 74)
                        self.assertEqual(reply["code"], code)
                for patched in (rate, resolve, post, suggest):
                    patched.assert_not_called()
            consumer = self.consumer_for(self.spectator)

            def short_circuit() -> str | None:
                with self.assertNumQueries(0):
                    try:
                        async_to_sync(consumer._authorize_and_post)(
                            "chat_send", {"body": "x"}
                        )
                    except ChatError as e:
                        return e.code
                return None

            with (
                mock.patch.object(_RecordingConsumer, "_post_chat") as post_chat,
                mock.patch.object(
                    _RecordingConsumer, "_resolve_chat_viewer"
                ) as resolve_viewer,
            ):
                code = await sync_to_async(short_circuit, thread_sensitive=False)()
            self.assertEqual(code, "not_participant")
            post_chat.assert_not_called()
            resolve_viewer.assert_not_called()
            self.assertFalse(
                await database_sync_to_async(
                    HeroDraftChatMessage.objects.filter(draft=self.draft).exists
                )()
            )
        finally:
            await self.close_all()

    async def test_bad_client_msg_id_and_body(self) -> None:
        try:
            mem_a = await self.connect_as(self.mem_a)
            for bad in ("a b", "x" * 65, 5, "", ["a"]):
                with self.subTest(client_msg_id=bad):
                    await mem_a.send_json_to(
                        {"type": "chat_send", "body": "hi", "client_msg_id": bad}
                    )
                    reply = await read_until_types(mem_a, {"chat_ack", "chat_error"})
                    self.assertEqual(
                        reply, {"type": "chat_error", "code": "bad_request"}
                    )
            for body in (5, None, ["x"], {"a": 1}):
                with self.subTest(body=body):
                    reply = await self.send_chat(mem_a, body, "body-1")
                    self.assertEqual(
                        reply,
                        {
                            "type": "chat_error",
                            "code": "bad_request",
                            "client_msg_id": "body-1",
                        },
                    )
            self.assertEqual(
                (await self.send_chat(mem_a, "x" * 64, "a" * 64))["type"], "chat_ack"
            )
        finally:
            await self.close_all()

    async def test_malformed_frames_from_anyone_keep_socket(self) -> None:
        try:
            anon = await self.connect_as(self.anonymous)
            for raw in ("{not json", "[1, 2]", '{"type": ["chat_send"]}', "null"):
                await anon.send_to(text_data=raw)
            reply = await self.send_chat(anon, "hi", "after")
            self.assertEqual(reply["code"], "not_participant")
        finally:
            await self.close_all()

    async def test_t15_rate_limit(self) -> None:
        try:
            mem_a = await self.connect_as(self.mem_a)
            for n in range(RATE_LIMIT_MAX):
                reply = await self.send_chat(mem_a, f"rate {n}", f"r{n}")
                self.assertEqual(reply["type"], "chat_ack", reply)
            reply = await self.send_chat(mem_a, "rate over", "over")
            self.assertEqual(
                reply,
                {"type": "chat_error", "code": "rate_limited", "client_msg_id": "over"},
            )
        finally:
            await self.close_all()

    async def test_suggestions_team_only(self) -> None:
        try:
            mem_a = await self.connect_as(self.mem_a)
            cap_a = await self.connect_as(self.cap_a)
            others = [
                await self.connect_as(u)
                for u in (self.cap_b, self.mem_b, self.spectator, self.anonymous)
            ]
            reply = await self.suggest(mem_a, Kind.SUGGEST_BAN, 74)
            self.assertEqual(reply["code"], "draft_inactive")

            await self.set_state(HeroDraftState.DRAFTING)
            reply = await self.suggest(mem_a, Kind.SUGGEST_BAN, 74)
            self.assertEqual(reply["type"], "chat_ack")
            for comm in (mem_a, cap_a):
                message = (await read_until_type(comm, "chat_message"))["message"]
                self.assertEqual(message["kind"], "suggest_ban")
                self.assertEqual(message["hero_id"], 74)
                self.assertEqual(message["channel"], "team")
                self.assertEqual(message["team_id"], self.team_a.pk)
            await asyncio.gather(*(self.assert_no_chat_frame(c) for c in others))

            await database_sync_to_async(HeroDraftRound.objects.create)(
                draft=self.draft,
                draft_team=await database_sync_to_async(
                    lambda: self.draft.draft_teams.first()
                )(),
                round_number=1,
                action_type="pick",
                hero_id=1,
                state="completed",
            )
            reply = await self.suggest(mem_a, Kind.SUGGEST_PICK, 1)
            self.assertEqual(reply["code"], "hero_unavailable")
        finally:
            await self.close_all()

    async def test_heartbeat_still_captain_only(self) -> None:
        with mock.patch.object(
            _RecordingConsumer, "handle_heartbeat", new_callable=mock.AsyncMock
        ) as heartbeat:
            try:
                mem_a = await self.connect_as(self.mem_a)
                await mem_a.send_json_to({"type": "heartbeat"})
                await self.send_chat(mem_a, "hb", "bad id")
                heartbeat.assert_not_called()
                cap_a = await self.connect_as(self.cap_a)
                on_connect = heartbeat.await_count
                await cap_a.send_json_to({"type": "heartbeat"})
                await self.send_chat(cap_a, "hb", "bad id")
                self.assertEqual(heartbeat.await_count, on_connect + 1)
            finally:
                await self.close_all()


class ChatDeliveryTest(ChatSendFixture):
    async def test_t6a_removed_member_loses_team_chat(self) -> None:
        before = "t6a-before-1d0e"
        after = "t6a-after-1d0e"
        try:
            await self.team_message(self.team_a, self.cap_a, before)
            cap_a = await self.connect_as(self.cap_a)
            mem_a = await self.connect_as(self.mem_a)
            await database_sync_to_async(self.team_a.members.remove)(self.mem_a)

            history = await read_history_with_role(mem_a, "spectator")
            self.assertNotIn(before, json.dumps(history))
            self.assertEqual(self.consumer_for(self.mem_a)._extra_groups, set())

            self.assertEqual((await self.send_chat(cap_a, after))["type"], "chat_ack")
            await self.assert_no_chat_frame(mem_a, after)

            await mem_a.disconnect()
            self.comms.remove(mem_a)
            _, _, history = await self.connect_with_frames(self.mem_a)
            self.assertEqual(history["viewer"]["role"], "spectator")
            self.assertNotIn(before, json.dumps(history))
            self.assertNotIn(after, json.dumps(history))
        finally:
            await self.close_all()

    async def test_t6b_transfer_b_to_a_socket(self) -> None:
        a_before = "t6b-a-before-6f3d"
        b_before = "t6b-b-before-6f3d"
        a_after = "t6b-a-after-6f3d"
        b_after = "t6b-b-after-6f3d"
        try:
            await self.team_message(self.team_a, self.cap_a, a_before)
            await self.team_message(self.team_b, self.cap_b, b_before)
            cap_a = await self.connect_as(self.cap_a)
            cap_b = await self.connect_as(self.cap_b)
            mover = await self.connect_as(self.mem_b)

            await database_sync_to_async(self.team_b.members.remove)(self.mem_b)
            await database_sync_to_async(self.team_a.members.add)(self.mem_b)

            history = await read_history_with_role(mover, "member")
            self.assertEqual(history["viewer"]["team_id"], self.team_a.pk)
            dumped = json.dumps(history)
            for gone in (a_before, b_before):
                self.assertNotIn(gone, dumped)

            await self.send_chat(cap_a, a_after)
            frame = await read_until_type(mover, "chat_message")
            self.assertEqual(frame["message"]["body"], a_after)
            await self.send_chat(cap_b, b_after)
            await self.assert_no_chat_frame(mover, b_after, b_before, a_before)
        finally:
            await self.close_all()

    @database_sync_to_async
    def make_team_c(self) -> tuple[Team, CustomUser, CustomUser]:
        cap_c = CustomUser.objects.create_user(username="cc_cap_c", password="x")
        mem_c = CustomUser.objects.create_user(username="cc_mem_c", password="x")
        team_c = Team.objects.create(
            name="CC C", tournament=self.tournament, captain=cap_c
        )
        team_c.members.add(mem_c)
        return team_c, cap_c, mem_c

    @database_sync_to_async
    def repoint_radiant(self, team: Team) -> None:
        self.game.radiant_team = team
        self.game.save()

    async def test_t8_draft_reset_resyncs_history(self) -> None:
        old = "t8-old-a-0c9a"
        new = "t8-new-c-0c9a"
        team_c, cap_c, mem_c = await self.make_team_c()
        try:
            await self.team_message(self.team_a, self.cap_a, old)
            mem_a = await self.connect_as(self.mem_a)
            cap_c_comm = await self.connect_as(cap_c)
            mem_c_comm = await self.connect_as(mem_c)
            spectator = await self.connect_as(self.spectator)

            await self.repoint_radiant(team_c)

            history = await read_history_with_role(mem_a, "spectator")
            self.assertNotIn(old, json.dumps(history))
            self.assertEqual(self.consumer_for(self.mem_a)._extra_groups, set())

            for comm in (cap_c_comm, mem_c_comm):
                history = await read_history_with_role(comm, "member")
                self.assertEqual(history["viewer"]["team_id"], team_c.pk)
                self.assertNotIn(old, json.dumps(history))

            await get_channel_layer().group_send(
                team_group_name(self.draft.pk, self.team_a.pk),
                self.raw_team_event(self.team_a, "t8-stale-a", self.now_iso()),
            )
            await self.assert_no_chat_frame(mem_a, "t8-stale-a")

            self.assertEqual(
                (await self.send_chat(mem_c_comm, new))["type"], "chat_ack"
            )
            frame = await read_until_type(cap_c_comm, "chat_message")
            self.assertEqual(frame["message"]["body"], new)
            self.assertEqual(frame["message"]["team_id"], team_c.pk)
            await self.assert_no_chat_frame(spectator, new)
        finally:
            await self.close_all()

    async def test_t6b_stale_group_second_queued_frame_dropped_silently(self) -> None:
        first = "stale-first-8e44"
        second = "stale-second-8e44"
        try:
            cap_a = await self.connect_as(self.cap_a)
            mem_a = await self.connect_as(self.mem_a)
            await database_sync_to_async(
                Team.members.through.objects.filter(
                    team_id=self.team_a.pk, customuser_id=self.mem_a.pk
                ).delete
            )()
            with capture_logs() as logs:
                group = team_group_name(self.draft.pk, self.team_a.pk)
                layer = get_channel_layer()
                await layer.group_send(
                    group, self.raw_team_event(self.team_a, first, self.now_iso())
                )
                await layer.group_send(
                    group, self.raw_team_event(self.team_a, second, self.now_iso())
                )
                history = await read_until_type(mem_a, "chat_history")
                self.assertEqual(history["viewer"]["role"], "spectator")
                rest = await drain(mem_a, 1.0)
            types = [f.get("type") for f in rest]
            self.assertNotIn("chat_history", types)
            self.assertNotIn("chat_message", types)
            for frame in [history, *rest]:
                self.assertNotIn(first, json.dumps(frame))
                self.assertNotIn(second, json.dumps(frame))
            self.assertEqual(self.consumer_for(self.mem_a)._extra_groups, set())
            revoked = [
                e for e in logs if e["event"] == "herodraft_chat_delivery_revoked"
            ]
            self.assertEqual(len(revoked), 1)
            self.assertEqual(revoked[0]["subsystem"], "chat")
            bodies = [
                (await read_until_type(cap_a, "chat_message"))["message"]["body"]
                for _ in range(2)
            ]
            self.assertEqual(bodies, [first, second])
        finally:
            await self.close_all()

    async def test_tenure_blocks_frame_older_than_joined_at(self) -> None:
        try:
            mem_a = await self.connect_as(self.mem_a)
            group = team_group_name(self.draft.pk, self.team_a.pk)
            old_at = (self.draft.created_at - timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            layer = get_channel_layer()
            await layer.group_send(
                group, self.raw_team_event(self.team_a, "tenure-old-77", old_at)
            )
            await layer.group_send(
                group, self.raw_team_event(self.team_a, "tenure-new-77", self.now_iso())
            )
            frames = await drain(mem_a, 1.0)
            messages = [f for f in frames if f.get("type") == "chat_message"]
            self.assertEqual(
                [m["message"]["body"] for m in messages], ["tenure-new-77"]
            )
            self.assertNotIn("chat_history", [f.get("type") for f in frames])
        finally:
            await self.close_all()

    async def test_t19_deleted_session_stops_team_delivery(self) -> None:
        sentinel = "t19-session-4a1b"

        @database_sync_to_async
        def make_session() -> SessionStore:
            session = SessionStore()
            session["_auth_user_id"] = str(self.mem_a.pk)
            session.create()
            return session

        try:
            session = await make_session()
            cap_a = await self.connect_as(self.cap_a)
            mem_a, _, history = await self.connect_with_frames(self.mem_a, session)
            self.assertEqual(history["viewer"]["role"], "member")
            await database_sync_to_async(
                Session.objects.filter(session_key=session.session_key).delete
            )()
            await self.send_chat(cap_a, sentinel)
            history = await read_until_type(mem_a, "chat_history")
            self.assertEqual(history["viewer"]["role"], "spectator")
            await self.assert_no_chat_frame(mem_a, sentinel)
            self.assertNotIn(sentinel, json.dumps(history))
        finally:
            await self.close_all()

    async def test_regroup_on_send_before_publish(self) -> None:
        sentinel = "regroup-send-2e8f"
        through = Team.members.through
        try:
            mover = await self.connect_as(self.mem_a)

            @database_sync_to_async
            def move_without_signals() -> None:
                through.objects.filter(
                    team_id=self.team_a.pk, customuser_id=self.mem_a.pk
                ).delete()
                through.objects.create(
                    team_id=self.team_b.pk, customuser_id=self.mem_a.pk
                )

            await move_without_signals()
            await mover.send_json_to(
                {"type": "chat_send", "body": sentinel, "client_msg_id": "rg"}
            )
            chat_frames: list[dict[str, Any]] = []
            while not {"chat_message", "chat_ack"} <= {f["type"] for f in chat_frames}:
                chat_frames.append(await read_until_types(mover, CHAT_FRAME_TYPES))
            self.assertEqual(chat_frames[0]["type"], "chat_history")
            self.assertEqual(chat_frames[0]["viewer"]["role"], "member")
            self.assertEqual(chat_frames[0]["viewer"]["team_id"], self.team_b.pk)
            message = next(f for f in chat_frames if f["type"] == "chat_message")
            self.assertEqual(message["message"]["body"], sentinel)
            self.assertEqual(message["message"]["team_id"], self.team_b.pk)
            self.assertEqual(
                self.consumer_for(self.mem_a)._extra_groups,
                {team_group_name(self.draft.pk, self.team_b.pk)},
            )
        finally:
            await self.close_all()

    async def test_targeted_resync_skips_unlisted_spectator(self) -> None:
        try:
            mem_a = await self.connect_as(self.mem_a)
            spectator = await self.connect_as(self.spectator)
            anon = await self.connect_as(self.anonymous)
            with mock.patch(
                "app.consumers.resolve_chat_viewer", wraps=resolve_chat_viewer
            ) as resolve:
                await get_channel_layer().group_send(
                    f"herodraft_{self.draft.pk}",
                    {
                        "type": "herodraft.chat_resync",
                        "team_ids": [self.team_a.pk],
                        "user_ids": [self.cap_a.pk],
                    },
                )
                history = await read_until_type(mem_a, "chat_history")
                self.assertEqual(history["viewer"]["role"], "member")
                await self.assert_no_chat_frame(spectator)
                await self.assert_no_chat_frame(anon)
            seen = [c.args[1] for c in resolve.call_args_list]
            self.assertIn(self.mem_a, seen)
            self.assertNotIn(self.spectator, seen)
            self.assertNotIn(self.anonymous, seen)
        finally:
            await self.close_all()

    @database_sync_to_async
    def swap_captain(self, new: CustomUser) -> None:
        with transaction.atomic():
            old = self.team_a.captain
            self.team_a.captain = new
            self.team_a.save(update_fields=["captain"])
            follow_captain(self.team_a, old, new, actor=None)

    async def test_team_changed_regroups_old_and_new_captain(self) -> None:
        pre = "swap-pre-91d3"
        post = "swap-post-91d3"
        newbie = await database_sync_to_async(CustomUser.objects.create_user)(
            username="cc_newbie", password="x"
        )
        try:
            await self.team_message(self.team_a, self.cap_a, pre)
            old_cap = await self.connect_as(self.cap_a)
            new_cap = await self.connect_as(newbie)
            mem_a = await self.connect_as(self.mem_a)

            await self.swap_captain(newbie)

            history = await read_history_with_role(new_cap, "member")
            self.assertEqual(history["viewer"]["team_id"], self.team_a.pk)
            self.assertNotIn(pre, json.dumps(history))
            for frame in await drain(new_cap, 0.5):
                self.assertNotIn(pre, json.dumps(frame))
            await read_history_with_role(old_cap, "spectator")
            for frame in await drain(old_cap, 0.5):
                if frame.get("type") == "chat_history":
                    self.assertEqual(frame["viewer"]["role"], "spectator")
                self.assertNotIn(pre, json.dumps(frame))
            self.assertEqual(self.consumer_for(self.cap_a)._extra_groups, set())

            self.assertEqual((await self.send_chat(mem_a, post))["type"], "chat_ack")
            frame = await read_until_type(new_cap, "chat_message")
            self.assertEqual(frame["message"]["body"], post)
            await self.assert_no_chat_frame(old_cap, post)
        finally:
            await self.close_all()


class ChatRosterPromotionTest(ChatSendFixture):
    async def test_signal_less_promotion_waits_for_resync(self) -> None:
        sentinel = "promote-91aa"
        try:
            comm = await self.connect_as(self.spectator)
            await database_sync_to_async(Team.members.through.objects.create)(
                team_id=self.team_a.pk, customuser_id=self.spectator.pk
            )
            reply = await self.send_chat(comm, sentinel)
            self.assertEqual(reply["type"], "chat_error")
            self.assertEqual(reply["code"], "not_participant")
            self.assertEqual(self.consumer_for(self.spectator)._extra_groups, set())

            await get_channel_layer().group_send(
                f"herodraft_{self.draft.pk}",
                {
                    "type": "herodraft.chat_resync",
                    "team_ids": [self.team_a.pk],
                    "user_ids": [self.spectator.pk],
                },
            )
            history = await read_history_with_role(comm, "member")
            self.assertEqual(history["viewer"]["team_id"], self.team_a.pk)
            self.assertEqual((await self.send_chat(comm, sentinel))["type"], "chat_ack")
        finally:
            await self.close_all()

    async def test_draft_event_roster_avoids_per_socket_query(self) -> None:
        try:
            spectator = await self.connect_as(self.spectator)
            mem_a = await self.connect_as(self.mem_a)
            with mock.patch(
                "app.consumers.draft_roster_user_ids", wraps=draft_roster_user_ids
            ) as roster:
                await database_sync_to_async(broadcast_herodraft_state)(
                    self.draft, "team_changed"
                )
                await read_until_type(spectator, "herodraft_event")
                event = await read_until_type(mem_a, "herodraft_event")
                await read_history_with_role(mem_a, "member")
                await self.assert_no_chat_frame(spectator)
            roster.assert_not_called()
            self.assertNotIn("chat_roster", event)
        finally:
            await self.close_all()


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class ChatActivitySocketTest(ChatSendFixture):
    def activity_application(self) -> Any:
        return AuthMiddlewareStack(
            URLRouter(
                [
                    path(
                        "api/discord/activity/draft/<int:draft_id>/",
                        ActivitySocketMiddleware(_RecordingConsumer.as_asgi(), "hero"),
                    )
                ]
            )
        )

    @database_sync_to_async
    def activity_token(self, user: CustomUser) -> str:
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="chat-activity", draft=self.draft
        )
        instance = DraftActivityInstance.objects.create(
            instance_id="chat-activity-instance",
            guild_id="1",
            channel_id="chat-activity",
            draft=self.draft,
        )
        return issue_activity_token(user, instance)

    async def test_activity_member_gets_team_chat(self) -> None:
        incoming = "activity-in-5c2e"
        outgoing = "activity-out-5c2e"
        try:
            token = await self.activity_token(self.mem_a)
            comm = WebsocketCommunicator(
                self.activity_application(),
                f"/api/discord/activity/draft/{self.draft.pk}/",
                subprotocols=["draftactivity", token],
            )
            connected, _ = await comm.connect(timeout=5)
            self.assertTrue(connected)
            self.comms.append(comm)
            consumer = next(
                c for c in _RecordingConsumer.instances if c.user.pk == self.mem_a.pk
            )
            self.assertIn("session", consumer.scope)
            self.assertIn("activity", consumer.scope)
            history = await read_until_type(comm, "chat_history")
            self.assertEqual(history["viewer"]["role"], "member")
            self.assertEqual(history["viewer"]["team_id"], self.team_a.pk)

            cap_a = await self.connect_as(self.cap_a)
            others = [await self.connect_as(u) for u in self.outsiders()]
            self.assertEqual(
                (await self.send_chat(cap_a, incoming))["type"], "chat_ack"
            )
            frame = await read_until_type(comm, "chat_message")
            self.assertEqual(frame["message"]["body"], incoming)

            reply = await self.send_chat(comm, outgoing, "act-1")
            self.assertEqual(reply["type"], "chat_ack")
            self.assertEqual(reply["client_msg_id"], "act-1")
            bodies = [
                (await read_until_type(cap_a, "chat_message"))["message"]["body"]
                for _ in range(2)
            ]
            self.assertEqual(bodies, [incoming, outgoing])

            await asyncio.gather(
                *(
                    self.assert_no_chat_frame(other, incoming, outgoing)
                    for other in others
                )
            )
        finally:
            await self.close_all()
