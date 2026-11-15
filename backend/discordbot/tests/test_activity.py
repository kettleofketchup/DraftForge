"""Activity identity, persistent match resolution and draft isolation."""

from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory

from app.models import (
    CustomUser,
    Draft,
    DraftRound,
    DraftTeam,
    Game,
    HeroDraft,
    Team,
    Tournament,
)
from discordbot.activity import activity_session, launch_message, resolve_instance
from discordbot.activity_auth import (
    ActivityAuthentication,
    ActivitySocketMiddleware,
    authenticate_token,
    issue_activity_token,
)
from discordbot.models import DraftActivityChannel, DraftActivityInstance


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class DraftActivityTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="activity-captain", discordId="101"
        )
        self.spectator = CustomUser.objects.create_user(
            username="activity-viewer", discordId="102"
        )
        self.tournament = Tournament.objects.create(
            name="Activity", date_played=date.today()
        )
        self.team = Team.objects.create(
            name="A", tournament=self.tournament, captain=self.user
        )
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        DraftTeam.objects.create(draft=self.hero, tournament_team=self.team)
        self.other = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        self.team_draft = Draft.objects.create(tournament=self.tournament)
        self.binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="2", draft=self.hero
        )
        self.factory = APIRequestFactory()

    def instance_response(self, channel="2", users=None):
        return {
            "users": users or ["101"],
            "location": {
                "kind": "gc",
                "guild_id": "1",
                "channel_id": channel,
            },
        }

    def credential(self, kind="hero", user=None):
        instance = DraftActivityInstance.objects.create(
            instance_id=f"instance-{kind}",
            guild_id="1",
            channel_id="2",
            draft=self.hero if kind == "hero" else None,
            team_draft=self.team_draft if kind == "team" else None,
        )
        return issue_activity_token(user or self.user, instance)

    @patch("discordbot.activity.discord_json")
    def test_two_matches_four_channels_resolve_independently(self, discord):
        for channel, draft in [
            ("2", self.hero),
            ("3", self.hero),
            ("4", self.other),
            ("5", self.other),
        ]:
            DraftActivityChannel.objects.update_or_create(
                channel_id=channel, defaults={"guild_id": "1", "draft": draft}
            )
            discord.return_value = self.instance_response(channel)
            self.assertEqual(resolve_instance(f"i-{channel}", "101").draft_id, draft.pk)
        self.assertEqual(DraftActivityInstance.objects.count(), 4)

    @patch("discordbot.activity.discord_json")
    def test_reconnect_pins_original_match_after_channel_reassignment(self, discord):
        discord.return_value = self.instance_response()
        initial = resolve_instance("i-persist", "101")
        self.binding.draft = self.other
        self.binding.save()
        self.assertEqual(resolve_instance("i-persist", "101").pk, initial.pk)
        self.assertEqual(resolve_instance("i-persist", "101").draft_id, self.hero.pk)
        self.assertEqual(resolve_instance("i-new", "101").draft_id, self.other.pk)

    @patch("discordbot.activity.discord_json")
    def test_instance_participation_and_channel_are_verified(self, discord):
        for response in [
            self.instance_response(users=["999"]),
            self.instance_response("999"),
            {"users": ["101"], "location": {"kind": "pc"}},
        ]:
            discord.return_value = response
            with self.assertRaises(AuthenticationFailed):
                resolve_instance("untrusted", "101")
        self.assertFalse(DraftActivityInstance.objects.exists())

    @patch("discordbot.activity.discord_json")
    def test_oauth_session_uses_verified_identity_and_scoped_token(self, discord):
        discord.side_effect = [
            {"access_token": "oauth-token"},
            {"id": "101"},
            self.instance_response(),
        ]
        response = activity_session(
            self.factory.post("/", {"code": "code", "instance_id": "i-session"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_id"], self.hero.pk)
        self.assertEqual(response.data["kind"], "hero")
        self.assertEqual(
            authenticate_token(response.data["token"], self.hero.pk, "hero"), self.user
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    @patch("discordbot.activity.discord_json")
    def test_team_session_resolves_tournament(self, discord):
        self.binding.draft = None
        self.binding.team_draft = self.team_draft
        self.binding.save()
        discord.side_effect = [
            {"access_token": "oauth-token"},
            {"id": "101"},
            self.instance_response(),
        ]
        response = activity_session(
            self.factory.post("/", {"code": "code", "instance_id": "i-team"})
        )
        self.assertEqual(response.data["kind"], "team")
        self.assertEqual(response.data["tournament_id"], self.tournament.pk)

    @patch("discordbot.activity.discord_json")
    def test_unlinked_user_is_rejected(self, discord):
        discord.side_effect = [{"access_token": "secret"}, {"id": "999"}]
        response = activity_session(
            self.factory.post("/", {"code": "code", "instance_id": "i"})
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("secret", str(response.data))

    def test_token_rejects_wrong_draft_kind_tampering_expiry_and_inactive_users(self):
        token = self.credential()
        for draft_id, kind in [(self.other.pk, "hero"), (self.hero.pk, "team")]:
            with self.assertRaises(AuthenticationFailed):
                authenticate_token(token, draft_id, kind)
        with self.assertRaises(AuthenticationFailed):
            authenticate_token(token + "x", self.hero.pk, "hero")
        with patch("django.core.signing.time.time", return_value=9999999999):
            with self.assertRaises(AuthenticationFailed):
                authenticate_token(token, self.hero.pk, "hero")
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(AuthenticationFailed):
            authenticate_token(token, self.hero.pk, "hero")

    def test_rest_scope_blocks_other_drafts_and_account_mutations(self):
        token = self.credential()
        auth = ActivityAuthentication()
        for path in [
            f"/api/herodraft/{self.other.pk}/ready/",
            "/api/users/1/",
            "/api/tournaments/init-draft",
        ]:
            with self.assertRaises(AuthenticationFailed):
                auth.authenticate(
                    self.factory.post(path, HTTP_AUTHORIZATION=f"DraftActivity {token}")
                )
        request = self.factory.get(
            f"/api/herodraft/{self.hero.pk}/",
            HTTP_AUTHORIZATION=f"DraftActivity {token}",
        )
        self.assertEqual(auth.authenticate(request)[0], self.user)
        self.assertIsNone(auth.authenticate(self.factory.get("/api/current_user")))

    def test_team_scope_checks_pick_round_belongs_to_bound_draft(self):
        token = self.credential("team")
        other_tournament = Tournament.objects.create(
            name="Other activity", date_played=date.today()
        )
        other_draft = Draft.objects.create(tournament=other_tournament)
        round_ = DraftRound.objects.create(
            draft=other_draft, captain=self.user, pick_number=1
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        response = client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": round_.pk, "user_pk": self.spectator.pk},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "Activity credentials are only valid for this draft.",
        )

    def test_spectator_cannot_ready_as_captain(self):
        token = self.credential(user=self.spectator)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        response = client.post(f"/api/herodraft/{self.hero.pk}/set-ready/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"], "You are not a captain in this draft")

    def test_bind_command_switches_kind_and_prints_launch_payload(self):
        output = StringIO()
        call_command(
            "configure_draft_activity",
            "1",
            "2",
            "team",
            str(self.team_draft.pk),
            stdout=output,
        )
        self.binding.refresh_from_db()
        self.assertIsNone(self.binding.draft_id)
        self.assertEqual(self.binding.team_draft_id, self.team_draft.pk)
        self.assertIn('"flags": 32768', output.getvalue())
        self.assertEqual(
            launch_message()["components"][1]["components"][0]["custom_id"],
            "draft_activity:launch",
        )

    def test_database_requires_exactly_one_draft_kind(self):
        for values in [{}, {"draft": self.hero, "team_draft": self.team_draft}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                DraftActivityChannel.objects.create(
                    guild_id="1", channel_id="invalid", **values
                )

    @override_settings(DISCORD_ACTIVITY_ENABLED=False)
    @patch("discordbot.activity.discord_json")
    def test_feature_disabled_does_not_contact_discord(self, discord):
        response = activity_session(
            self.factory.post("/", {"code": "code", "instance_id": "i"})
        )
        self.assertEqual(response.status_code, 404)
        discord.assert_not_called()

    def test_socket_rejects_missing_credential(self):
        app, send = AsyncMock(), AsyncMock()
        async_to_sync(ActivitySocketMiddleware(app, "hero").__call__)(
            {"subprotocols": [], "url_route": {"kwargs": {"draft_id": self.hero.pk}}},
            AsyncMock(),
            send,
        )
        app.assert_not_awaited()
        send.assert_awaited_once_with({"type": "websocket.close", "code": 4401})

    def test_gateway_launch_uses_activity_callback(self):
        import discord

        from discordbot.interaction_router import route_component_interaction

        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            channel=SimpleNamespace(type=discord.ChannelType.voice),
            response=SimpleNamespace(launch_activity=AsyncMock()),
        )
        async_to_sync(route_component_interaction)(interaction, "draft_activity:launch")
        interaction.response.launch_activity.assert_awaited_once()

    def test_socket_passes_verified_user_to_existing_consumer(self):
        user = self.user
        app, send = AsyncMock(), AsyncMock()
        resolver = AsyncMock(return_value=user)
        scope = {
            "subprotocols": ["draftactivity", "signed-token"],
            "url_route": {"kwargs": {"draft_id": self.hero.pk}},
        }
        with (
            patch(
                "discordbot.activity_auth.database_sync_to_async", return_value=resolver
            ),
            patch(
                "discordbot.activity_auth._token_data",
                return_value={"expires": 9999999999},
            ),
        ):
            async_to_sync(ActivitySocketMiddleware(app, "hero").__call__)(
                scope, AsyncMock(), send
            )
        resolver.assert_awaited_once_with("signed-token", self.hero.pk, "hero")
        self.assertEqual(app.await_args.args[0]["user"], user)
        self.assertNotIn("user", scope)

    def test_http_launch_responds_with_type_twelve(self):
        from discordbot.views import handle_message_component

        response = handle_message_component(
            {
                "guild_id": "1",
                "channel_id": "2",
                "data": {"custom_id": "draft_activity:launch"},
            }
        )
        self.assertJSONEqual(response.content, {"type": 12})

    @patch("discordbot.activity.discord_json")
    def test_deleted_and_recreated_instance_never_revives_old_credential(self, discord):
        token = self.credential()
        original = DraftActivityInstance.objects.get(instance_id="instance-hero")
        original_pk = original.pk
        original.delete()
        self.binding.draft = self.other
        self.binding.save()
        discord.return_value = self.instance_response()
        recreated = resolve_instance("instance-hero", "101")
        self.assertNotEqual(recreated.pk, original_pk)
        self.assertEqual(recreated.draft_id, self.other.pk)
        for draft in [self.hero, self.other]:
            with self.assertRaises(AuthenticationFailed):
                authenticate_token(token, draft.pk, "hero")
        fresh = issue_activity_token(self.user, recreated)
        self.assertEqual(authenticate_token(fresh, self.other.pk, "hero"), self.user)

    def test_mutating_instance_destination_invalidates_existing_tokens(self):
        token = self.credential()
        DraftActivityInstance.objects.filter(instance_id="instance-hero").update(
            draft=self.other
        )
        with self.assertRaises(AuthenticationFailed):
            authenticate_token(token, self.other.pk, "hero")

    def test_malformed_team_pick_data_is_rejected_without_server_errors(self):
        token = self.credential("team")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        for body in [
            [],
            "invalid",
            {"draft_round_pk": []},
            {"draft_round_pk": {}},
            {"draft_round_pk": 2**63},
            {"draft_round_pk": "9" * 5000},
            {"draft_round_pk": True},
        ]:
            with self.subTest(body_type=type(body).__name__):
                response = client.post(
                    "/api/tournaments/pick_player", body, format="json"
                )
                self.assertEqual(response.status_code, 403)

    def test_oversized_and_zero_padded_paths_do_not_bypass_kind_scope(self):
        token = self.credential("team")
        auth = ActivityAuthentication()
        for path in [
            f"/api/herodraft/{self.hero.pk:030d}/set-ready/",
            f"/api/herodraft/{2**63}/set-ready/",
        ]:
            with self.assertRaises(AuthenticationFailed):
                auth.authenticate(
                    self.factory.post(path, HTTP_AUTHORIZATION=f"DraftActivity {token}")
                )

    def test_team_undo_and_style_scope_match_the_assigned_draft(self):
        from rest_framework.parsers import JSONParser
        from rest_framework.request import Request

        token = self.credential("team")
        auth = ActivityAuthentication()
        for path, key in [
            ("/api/tournaments/undo-pick", "draft_pk"),
            ("/api/draft/get-style-mmrs", "pk"),
        ]:
            request = Request(
                self.factory.post(
                    path,
                    {key: self.team_draft.pk},
                    format="json",
                    HTTP_AUTHORIZATION=f"DraftActivity {token}",
                ),
                parsers=[JSONParser()],
            )
            self.assertEqual(auth.authenticate(request)[0], self.user)
            for value in [self.team_draft.pk + 1000, 2**63, None, [], True]:
                request = Request(
                    self.factory.post(
                        path,
                        {key: value},
                        format="json",
                        HTTP_AUTHORIZATION=f"DraftActivity {token}",
                    ),
                    parsers=[JSONParser()],
                )
                with self.assertRaises(AuthenticationFailed):
                    auth.authenticate(request)

    def test_activity_credential_does_not_grant_undo_staff_permission(self):
        token = self.credential("team")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        response = client.post(
            "/api/tournaments/undo-pick", {"draft_pk": self.team_draft.pk}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["error"],
            "You do not have permission to undo picks in this draft",
        )


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class ActivitySocketDatabaseTests(TransactionTestCase):
    """Exercise the real async credential lookup on a committed database."""

    def setUp(self):
        user = CustomUser.objects.create_user(
            username="socket-captain", discordId="303"
        )
        self.user_pk = user.pk
        draft = HeroDraft.objects.create(game=Game.objects.create())
        self.draft_pk = draft.pk
        instance = DraftActivityInstance.objects.create(
            instance_id="socket-instance", guild_id="1", channel_id="2", draft=draft
        )
        self.token = issue_activity_token(user, instance)

    async def test_valid_socket_uses_real_database_identity(self):
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path

        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": str(scope["user"].pk)})
            await receive()

        router = URLRouter(
            [
                path(
                    "draft/<int:draft_id>/",
                    ActivitySocketMiddleware(application, "hero"),
                )
            ]
        )
        socket = WebsocketCommunicator(
            router,
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", self.token],
        )
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        self.assertEqual(await socket.receive_from(), str(self.user_pk))
        await socket.disconnect()

    async def _open_guarded_socket(self, token=None):
        import asyncio

        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path

        self.consumer_cleaned_up = asyncio.Event()

        async def application(scope, receive, send):
            try:
                await receive()
                await send({"type": "websocket.accept"})
                while True:
                    message = await receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    await send({"type": "websocket.send", "text": "heartbeat"})
            finally:
                self.consumer_cleaned_up.set()

        router = URLRouter(
            [
                path(
                    "draft/<int:draft_id>/",
                    ActivitySocketMiddleware(application, "hero"),
                )
            ]
        )
        socket = WebsocketCommunicator(
            router,
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", token or self.token],
        )
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        return socket

    async def test_open_socket_closes_after_mapping_revocation(self):
        from channels.db import database_sync_to_async

        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket()
            await database_sync_to_async(
                DraftActivityInstance.objects.filter(
                    instance_id="socket-instance"
                ).delete
            )()
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4401},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()

    async def test_open_socket_closes_after_account_deactivation(self):
        from channels.db import database_sync_to_async

        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket()
            await database_sync_to_async(
                CustomUser.objects.filter(pk=self.user_pk).update
            )(is_active=False)
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4401},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()

    async def test_open_socket_closes_when_activity_feature_is_disabled(self):
        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket()
            with self.settings(DISCORD_ACTIVITY_ENABLED=False):
                self.assertEqual(
                    await socket.receive_output(timeout=5),
                    {"type": "websocket.close", "code": 4401},
                )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()

    async def test_open_socket_expires_before_periodic_revalidation(self):
        import time

        from django.core import signing

        from discordbot.activity_auth import SALT

        data = signing.loads(self.token.replace(".", ":"), salt=SALT)
        data["expires"] = time.time() + 0.1
        token = signing.dumps(data, salt=SALT).replace(":", ".")
        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 30):
            socket = await self._open_guarded_socket(token)
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4401},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()

    @override_settings(ALLOWED_HOSTS=["123.discordsays.com"])
    async def test_discord_proxy_origin_is_allowed_and_foreign_origin_is_denied(self):
        from channels.routing import URLRouter
        from channels.security.websocket import AllowedHostsOriginValidator
        from channels.testing import WebsocketCommunicator
        from django.urls import path

        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": str(scope["user"].pk)})
            await receive()

        router = AllowedHostsOriginValidator(
            URLRouter(
                [
                    path(
                        "draft/<int:draft_id>/",
                        ActivitySocketMiddleware(application, "hero"),
                    ),
                ]
            )
        )
        good = WebsocketCommunicator(
            router,
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", self.token],
            headers=[(b"origin", b"https://123.discordsays.com")],
        )
        self.assertTrue((await good.connect(timeout=5))[0])
        self.assertEqual(await good.receive_from(), str(self.user_pk))
        await good.disconnect()
        foreign = WebsocketCommunicator(
            router,
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", self.token],
            headers=[(b"origin", b"https://foreign.example")],
        )
        with patch("discordbot.activity_auth.authenticate_token") as auth:
            self.assertFalse((await foreign.connect(timeout=5))[0])
            auth.assert_not_called()
        await foreign.disconnect()
