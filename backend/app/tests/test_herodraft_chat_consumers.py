import json
from datetime import date
from typing import Any
from unittest import mock

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from django.urls import re_path
from structlog.testing import capture_logs

from app.consumers import HeroDraftConsumer
from app.functions.herodraft import new_herodraft_for_game
from app.functions.herodraft_chat import team_group_name
from app.models import (
    CustomUser,
    Game,
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    HeroDraftState,
    League,
    Organization,
    Team,
    Tournament,
)
from app.tests.ws_helpers import assert_no_frame_except_ping, read_until_type

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
        self, user: Viewer
    ) -> tuple[WebsocketCommunicator, dict[str, Any], dict[str, Any]]:
        comm = WebsocketCommunicator(
            self.application(), f"/api/herodraft/{self.draft.pk}/"
        )
        comm.scope["user"] = user
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
