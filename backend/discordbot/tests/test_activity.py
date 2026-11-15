"""Activity identity, persistent match resolution and draft isolation."""

from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core import signing
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
    SALT,
    ActivityAuthentication,
    ActivitySocketMiddleware,
    authenticate_token,
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
        return signing.dumps(
            {"user": (user or self.user).pk, "instance": instance.instance_id},
            salt=SALT,
        ).replace(":", ".")

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
        from discordbot.interaction_router import route_component_interaction

        interaction = SimpleNamespace(
            response=SimpleNamespace(launch_activity=AsyncMock())
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
        with patch(
            "discordbot.activity_auth.database_sync_to_async", return_value=resolver
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
            {"data": {"custom_id": "draft_activity:launch"}}
        )
        self.assertJSONEqual(response.content, {"type": 12})


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
        self.token = signing.dumps(
            {"user": user.pk, "instance": instance.instance_id}, salt=SALT
        ).replace(":", ".")

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
