"""Activity identity, persistent match resolution and draft isolation."""

import asyncio
import json
import time
from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core import signing
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import path as url_path
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from structlog.contextvars import clear_contextvars, get_contextvars
from structlog.testing import capture_logs

from app.models import CustomUser, Draft, DraftRound, Game, Team, Tournament
from discordbot.activity import activity_session, launch_message, resolve_instance
from discordbot.activity_auth import (
    HERO_SUFFIXES,
    LEGACY_SALT,
    PATH_NOT_ALLOWED,
    SALT,
    ActivityAuthentication,
    ActivityIdentity,
    ActivitySocketMiddleware,
    authenticate_token,
    issue_activity_token,
    scope_allows,
    token_identity,
)
from discordbot.activity_errors import ActivityAuthFailed
from discordbot.activity_intent import peek_intent, record_intent
from discordbot.activity_menu import (
    external_path,
    hero_label,
    hero_status,
    notice_for,
    team_status,
)
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from discordbot.tests.activity_helpers import ClearIntentsMixin
from draft.models import DraftTeam, HeroDraft, HeroDraftState


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class DraftActivityTests(ClearIntentsMixin, TestCase):
    def setUp(self):
        super().setUp()
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
        self.other_tournament = Tournament.objects.create(
            name="Other activity", date_played=date.today()
        )
        self.foreign = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.other_tournament)
        )
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

    def legacy_token(self, kind="hero", draft=None):
        instance = DraftActivityInstance.objects.create(
            instance_id=f"legacy-{kind}",
            guild_id="1",
            channel_id="2",
            draft=self.hero if kind == "hero" else None,
            team_draft=self.team_draft if kind == "team" else None,
        )
        payload = {
            "user": self.user.pk,
            "binding": instance.pk,
            "instance": instance.instance_id,
            "kind": kind,
            "draft": draft or instance.draft_id or instance.team_draft_id,
            "expires": time.time() + 60,
        }
        return signing.dumps(payload, salt=LEGACY_SALT).replace(":", ".")

    def rest(self, path, token, method="get", data=None):
        request = getattr(self.factory, method)(
            path, data, format="json", HTTP_AUTHORIZATION=f"DraftActivity {token}"
        )
        return ActivityAuthentication().authenticate(
            Request(request, parsers=[JSONParser()])
        )

    def assert_rest_code(self, path, token, code, method="get", data=None):
        with self.assertRaises(ActivityAuthFailed) as caught:
            self.rest(path, token, method, data)
        self.assertEqual(caught.exception.activity_code, code)
        return caught.exception

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
            instance, created = resolve_instance(f"i-{channel}", "101")
            self.assertTrue(created)
            self.assertEqual(instance.draft_id, draft.pk)
        self.assertEqual(DraftActivityInstance.objects.count(), 4)

    @patch("discordbot.activity.discord_json")
    def test_reconnect_pins_original_match_after_channel_reassignment(self, discord):
        discord.return_value = self.instance_response()
        initial, _ = resolve_instance("i-persist", "101")
        self.binding.draft = self.other
        self.binding.save()
        again, created = resolve_instance("i-persist", "101")
        self.assertFalse(created)
        self.assertEqual(again.pk, initial.pk)
        self.assertEqual(again.draft_id, self.hero.pk)
        self.assertEqual(resolve_instance("i-new", "101")[0].draft_id, self.other.pk)

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

    def session(self, discord, body, instance=None, discord_id="101"):
        discord.side_effect = [
            {"access_token": "oauth-token"},
            {"id": discord_id},
            instance or self.instance_response(users=[discord_id]),
        ]
        return activity_session(self.factory.post("/", body, format="json"))

    def seed_instance(self, instance_id="i-existing", draft=None):
        return DraftActivityInstance.objects.create(
            instance_id=instance_id,
            guild_id="1",
            channel_id="2",
            draft=draft or self.hero,
        )

    @patch("discordbot.activity.discord_json")
    def test_oauth_session_uses_verified_identity_and_scoped_token(self, discord):
        response = self.session(
            discord, {"code": "code", "instance_id": "i-session", "mode": "first"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_id"], self.hero.pk)
        self.assertEqual(response.data["kind"], "hero")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.hero.pk}
        )
        self.assertIsNone(response.data["launch_intent"])
        self.assertIsNone(response.data["notice"])
        self.assertEqual(response.data["access_token"], "oauth-token")
        self.assertEqual(response.data["user"]["pk"], self.user.pk)
        self.assertEqual(
            authenticate_token(response.data["token"], self.other.pk, "hero").user,
            self.user,
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    @patch("discordbot.activity.discord_json")
    def test_hero_session_returns_tournament_and_scope(self, discord):
        response = self.session(
            discord, {"code": "code", "instance_id": "i-hero", "mode": "first"}
        )
        self.assertEqual(response.data["tournament_id"], self.tournament.pk)
        self.assertEqual(response.data["scope"], "tournament")
        self.assertEqual(response.data["site_url"], settings.SITE_URL)

    @patch("discordbot.activity.discord_json")
    def test_tournamentless_session_is_draft_scoped(self, discord):
        loose = HeroDraft.objects.create(game=Game.objects.create())
        self.binding.draft = loose
        self.binding.save()
        response = self.session(
            discord, {"code": "code", "instance_id": "i-loose", "mode": "first"}
        )
        self.assertEqual(response.data["scope"], "draft")
        self.assertIsNone(response.data["tournament_id"])
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": loose.pk}
        )

    @patch("discordbot.activity.discord_json")
    def test_team_session_resolves_tournament(self, discord):
        HeroDraft.objects.filter(pk=self.hero.pk).update(state=HeroDraftState.COMPLETED)
        self.binding.draft = None
        self.binding.team_draft = self.team_draft
        self.binding.save()
        response = self.session(
            discord, {"code": "code", "instance_id": "i-team", "mode": "first"}
        )
        self.assertEqual(response.data["kind"], "team")
        self.assertEqual(response.data["draft_id"], self.team_draft.pk)
        self.assertEqual(response.data["tournament_id"], self.tournament.pk)
        self.assertEqual(response.data["scope"], "tournament")
        self.assertEqual(
            response.data["initial_view"], {"kind": "team", "id": self.team_draft.pk}
        )

    @patch("discordbot.activity.discord_json")
    def test_legacy_handshake_after_newer_launch_returns_instance_first_draft(
        self, discord
    ):
        self.seed_instance("i-legacy")
        self.binding.draft = self.other
        self.binding.save()
        record_intent(
            "101",
            kind="hero",
            draft_id=self.other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        with capture_logs() as logs:
            response = self.session(
                discord, {"code": "code", "instance_id": "i-legacy"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_id"], self.hero.pk)
        self.assertEqual(response.data["kind"], "hero")
        self.assertEqual(DraftActivityInstance.objects.count(), 1)
        started = [e for e in logs if e["event"] == "activity_session_started"]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["mode"], "legacy")
        self.assertFalse(started[0]["instance_created"])
        self.assertEqual(started[0]["initial_kind"], "hero")
        self.assertEqual(started[0]["initial_draft_id"], self.hero.pk)
        self.assertEqual(started[0]["source"], "legacy")
        self.assertIsNone(started[0]["intent_id"])
        self.assertIsNotNone(peek_intent("101"))

    @patch("discordbot.activity.discord_json")
    def test_session_started_log_fields(self, discord):
        with capture_logs() as logs:
            self.session(
                discord, {"code": "code", "instance_id": "i-logged", "mode": "first"}
            )
        (event,) = [e for e in logs if e["event"] == "activity_session_started"]
        instance = DraftActivityInstance.objects.get(instance_id="i-logged")
        self.assertEqual(
            {k: event[k] for k in event if k not in ("log_level", "event")},
            {
                "system": "discord",
                "subsystem": "activity",
                "user_id": self.user.pk,
                "discord_user_id": "101",
                "instance_id": instance.instance_id,
                "guild_id": "1",
                "channel_id": "2",
                "tournament_id": self.tournament.pk,
                "mode": "first",
                "instance_created": True,
                "scope": "tournament",
                "initial_kind": "hero",
                "initial_draft_id": self.hero.pk,
                "source": "involves_me",
                "role": "captain",
                "notice": False,
                "intent_id": None,
            },
        )

    @patch("discordbot.activity.discord_json")
    def test_new_instance_seeded_from_matching_intent(self, discord):
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=self.other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        self.assertIsNotNone(intent_id)
        response = self.session(
            discord, {"code": "code", "instance_id": "i-seeded", "mode": "first"}
        )
        instance = DraftActivityInstance.objects.get(instance_id="i-seeded")
        self.assertEqual(instance.draft_id, self.other.pk)
        self.assertEqual(response.data["draft_id"], self.other.pk)
        self.assertEqual(peek_intent("101").intent_id, intent_id)

    @patch("discordbot.activity.discord_json")
    def test_new_instance_seeded_from_team_intent(self, discord):
        record_intent(
            "101",
            kind="team",
            draft_id=self.team_draft.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response = self.session(
            discord, {"code": "code", "instance_id": "i-team-seed", "mode": "first"}
        )
        instance = DraftActivityInstance.objects.get(instance_id="i-team-seed")
        self.assertIsNone(instance.draft_id)
        self.assertEqual(instance.team_draft_id, self.team_draft.pk)
        self.assertEqual(response.data["kind"], "team")

    @patch("discordbot.activity.discord_json")
    def test_new_instance_ignores_intent_from_other_tournament(self, discord):
        for instance_id, draft, channel in [
            ("i-foreign", self.foreign, "2"),
            ("i-elsewhere", self.other, "9"),
        ]:
            with self.subTest(instance_id=instance_id):
                record_intent(
                    "101",
                    kind="hero",
                    draft_id=draft.pk,
                    tournament_id=draft.game.tournament_id,
                    guild_id="1",
                    channel_id=channel,
                )
                self.session(
                    discord,
                    {"code": "code", "instance_id": instance_id, "mode": "first"},
                )
                instance = DraftActivityInstance.objects.get(instance_id=instance_id)
                self.assertEqual(instance.draft_id, self.hero.pk)

    @patch("discordbot.activity.discord_json")
    def test_new_instance_seeded_from_intent_without_channel_record(self, discord):
        self.binding.delete()
        record_intent(
            "101",
            kind="hero",
            draft_id=self.other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response = self.session(
            discord, {"code": "code", "instance_id": "i-unbound", "mode": "first"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_id"], self.other.pk)

    @patch("discordbot.activity.discord_json")
    def test_intent_for_deleted_draft_falls_back_to_channel_record(self, discord):
        gone = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        record_intent(
            "101",
            kind="hero",
            draft_id=gone.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        gone.delete()
        response = self.session(
            discord, {"code": "code", "instance_id": "i-gone", "mode": "first"}
        )
        self.assertEqual(response.data["draft_id"], self.hero.pk)

    @patch("discordbot.activity.discord_json")
    def test_no_channel_record_and_no_intent_is_rejected(self, discord):
        self.binding.delete()
        response = self.session(
            discord, {"code": "code", "instance_id": "i-none", "mode": "first"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"], "This voice channel has no draft configured."
        )
        self.assertNotIn("code", response.data)

    @patch("discordbot.activity.discord_json")
    def test_refresh_mode_skips_intent_and_logs_refreshed(self, discord):
        self.seed_instance("i-refresh")
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=self.other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        with capture_logs() as logs:
            response = self.session(
                discord,
                {
                    "code": "code",
                    "instance_id": "i-refresh",
                    "mode": "refresh",
                    "current_view": {"kind": "hero", "id": self.other.pk},
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["initial_view"])
        self.assertIsNone(response.data["launch_intent"])
        self.assertIsNone(response.data["notice"])
        self.assertEqual(response.data["draft_id"], self.hero.pk)
        self.assertEqual(peek_intent("101").intent_id, intent_id)
        events = [e["event"] for e in logs]
        self.assertNotIn("activity_session_started", events)
        (refreshed,) = [e for e in logs if e["event"] == "activity_session_refreshed"]
        self.assertEqual(refreshed["current_kind"], "hero")
        self.assertEqual(refreshed["current_id"], self.other.pk)
        self.assertEqual(refreshed["user_id"], self.user.pk)
        self.assertEqual(refreshed["instance_id"], "i-refresh")
        self.assertEqual(refreshed["tournament_id"], self.tournament.pk)

    @patch("discordbot.activity.discord_json")
    def test_draft_scope_refresh_keeps_pin_after_tournament_launch(self, discord):
        loose = HeroDraft.objects.create(game=Game.objects.create())
        self.binding.draft = loose
        self.binding.save()
        first = self.session(
            discord, {"code": "code", "instance_id": "i-pinned", "mode": "first"}
        )
        self.assertEqual(first.data["scope"], "draft")
        self.binding.draft = self.other
        self.binding.save()
        response = self.session(
            discord,
            {
                "code": "code",
                "instance_id": "i-pinned",
                "mode": "refresh",
                "scope": "draft",
                "current_view": {"kind": "hero", "id": loose.pk},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"], "draft")
        self.assertIsNone(response.data["tournament_id"])
        self.assertEqual(response.data["draft_id"], loose.pk)
        identity = authenticate_token(response.data["token"], loose.pk, "hero")
        self.assertEqual(identity.scope, "draft")
        self.assertEqual(identity.pin, {"kind": "hero", "draft": loose.pk})

    @patch("discordbot.activity.discord_json")
    def test_refresh_with_bracket_view_has_no_id(self, discord):
        with capture_logs() as logs:
            response = self.session(
                discord,
                {
                    "code": "code",
                    "instance_id": "i-bracket",
                    "mode": "refresh",
                    "current_view": {"kind": "bracket"},
                },
            )
        self.assertEqual(response.status_code, 200)
        (refreshed,) = [e for e in logs if e["event"] == "activity_session_refreshed"]
        self.assertEqual(refreshed["current_kind"], "bracket")
        self.assertIsNone(refreshed["current_id"])

    @patch("discordbot.activity.discord_json")
    def test_malformed_mode_or_current_view_is_rejected(self, discord):
        for extra in [
            {"mode": "switch"},
            {"mode": "refresh", "current_view": {"kind": "lobby"}},
            {"mode": "refresh", "current_view": {"kind": "hero", "id": 0}},
            {"mode": "refresh", "current_view": {"kind": "hero", "id": "x"}},
            {"mode": "refresh", "current_view": "hero"},
            {"mode": "refresh", "scope": "league"},
        ]:
            with self.subTest(extra=extra):
                response = activity_session(
                    self.factory.post(
                        "/",
                        {"code": "code", "instance_id": "i", **extra},
                        format="json",
                    )
                )
                self.assertEqual(response.status_code, 400)
        discord.assert_not_called()

    @patch("discordbot.activity.discord_json")
    def test_session_never_logs_secrets(self, discord):
        with capture_logs() as logs:
            response = self.session(
                discord,
                {
                    "code": "secret-oauth-code",
                    "instance_id": "i-quiet",
                    "mode": "first",
                },
            )
        token = response.data["token"]
        self.assertTrue(logs)
        for entry in logs:
            for value in entry.values():
                for secret in (token, "secret-oauth-code", "oauth-token"):
                    self.assertNotIn(secret, str(value))

    @patch("discordbot.activity.discord_json")
    def test_anchor_deleted_reseeds_new_instance(self, discord):
        anchor = self.seed_instance("i-anchor")
        self.binding.draft = self.other
        self.binding.save()
        self.hero.delete()
        self.assertFalse(DraftActivityInstance.objects.filter(pk=anchor.pk).exists())
        response = self.session(
            discord,
            {
                "code": "code",
                "instance_id": "i-anchor",
                "mode": "refresh",
                "current_view": {"kind": "hero", "id": self.other.pk},
            },
        )
        self.assertEqual(response.status_code, 200)
        reseeded = DraftActivityInstance.objects.get(instance_id="i-anchor")
        self.assertNotEqual(reseeded.pk, anchor.pk)
        self.assertEqual(reseeded.draft_id, self.other.pk)
        self.assertEqual(response.data["scope"], "tournament")
        self.assertEqual(response.data["tournament_id"], self.tournament.pk)
        self.assertEqual(response.data["draft_id"], self.other.pk)
        identity = authenticate_token(response.data["token"], self.other.pk, "hero")
        self.assertEqual(identity.instance.pk, reseeded.pk)

    def first_session(self, discord, instance_id, discord_id="101"):
        with capture_logs() as logs:
            response = self.session(
                discord,
                {"code": "code", "instance_id": instance_id, "mode": "first"},
                discord_id=discord_id,
            )
        self.assertEqual(response.status_code, 200)
        (started,) = [e for e in logs if e["event"] == "activity_session_started"]
        return response, started

    @patch("discordbot.activity.discord_json")
    def test_initial_view_from_launch_intent_is_peeked(self, discord):
        self.seed_instance("i-intent")
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=self.other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response, started = self.first_session(discord, "i-intent")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.other.pk}
        )
        self.assertEqual(
            response.data["launch_intent"],
            {"intent_id": intent_id, "kind": "hero", "id": self.other.pk},
        )
        self.assertIsNone(response.data["notice"])
        self.assertEqual(response.data["draft_id"], self.hero.pk)
        self.assertEqual(started["source"], "launch_intent")
        self.assertEqual(started["intent_id"], intent_id)
        self.assertEqual(peek_intent("101").intent_id, intent_id)

    @patch("discordbot.activity.discord_json")
    def test_intent_from_other_tournament_gives_notice(self, discord):
        self.seed_instance("i-foreign-intent")
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=self.foreign.pk,
            tournament_id=self.other_tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response, started = self.first_session(discord, "i-foreign-intent")
        notice = response.data["notice"]
        self.assertEqual(notice["intent_id"], intent_id)
        self.assertEqual(notice["kind"], "hero")
        self.assertEqual(notice["draft_id"], self.foreign.pk)
        self.assertEqual(notice["tournament_name"], "Other activity")
        self.assertTrue(notice["url"].startswith(settings.SITE_URL))
        self.assertTrue(notice["url"].endswith(f"/herodraft/{self.foreign.pk}"))
        self.assertIsNone(response.data["launch_intent"])
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.hero.pk}
        )
        self.assertTrue(started["notice"])
        self.assertEqual(started["intent_id"], intent_id)
        self.assertEqual(peek_intent("101").intent_id, intent_id)

    @patch("discordbot.activity.discord_json")
    def test_involves_me_beats_channel_last_with_two_matches(self, discord):
        Draft.objects.filter(pk=self.team_draft.pk).update(state="completed")
        self.binding.draft = self.other
        self.binding.save()
        response, started = self.first_session(discord, "i-shared-lobby")
        self.assertEqual(
            DraftActivityInstance.objects.get(instance_id="i-shared-lobby").draft_id,
            self.other.pk,
        )
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.hero.pk}
        )
        self.assertEqual(started["source"], "involves_me")
        self.assertEqual(started["role"], "captain")

    @patch("discordbot.activity.discord_json")
    def test_involves_me_prefers_my_hero_draft_over_unfinished_team_draft(
        self, discord
    ):
        for state in ("pending", "drafting"):
            with self.subTest(state=state):
                Draft.objects.filter(pk=self.team_draft.pk).update(state=state)
                self.binding.draft = self.other
                self.binding.save()
                response, started = self.first_session(discord, f"i-stale-{state}")
                self.assertEqual(
                    response.data["initial_view"],
                    {"kind": "hero", "id": self.hero.pk},
                )
                self.assertEqual(started["source"], "involves_me")

    @patch("discordbot.activity.discord_json")
    def test_finished_match_does_not_count_as_involves_me(self, discord):
        Draft.objects.filter(pk=self.team_draft.pk).update(state="completed")
        HeroDraft.objects.filter(pk=self.hero.pk).update(state=HeroDraftState.COMPLETED)
        self.seed_instance("i-finished-match")
        self.binding.draft = self.other
        self.binding.save()
        response, started = self.first_session(discord, "i-finished-match")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.other.pk}
        )
        self.assertEqual(started["source"], "channel_last")

    @patch("discordbot.activity.discord_json")
    def test_channel_last_when_no_intent_and_not_involved(self, discord):
        self.seed_instance("i-spectate")
        self.binding.draft = self.other
        self.binding.save()
        response, started = self.first_session(discord, "i-spectate", "102")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.other.pk}
        )
        self.assertIsNone(response.data["notice"])
        self.assertEqual(started["source"], "channel_last")
        self.assertEqual(started["role"], "spectator")
        self.assertEqual(response.data["draft_id"], self.hero.pk)

    @patch("discordbot.activity.discord_json")
    def test_channel_record_in_other_tournament_gives_notice(self, discord):
        self.seed_instance("i-foreign-channel")
        self.binding.draft = self.foreign
        self.binding.save()
        response, started = self.first_session(discord, "i-foreign-channel", "102")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.hero.pk}
        )
        self.assertEqual(started["source"], "instance_first")
        notice = response.data["notice"]
        self.assertNotIn("intent_id", notice)
        self.assertEqual(notice["draft_id"], self.foreign.pk)
        self.assertEqual(notice["tournament_name"], "Other activity")
        self.assertTrue(notice["url"].endswith(f"/herodraft/{self.foreign.pk}"))
        self.assertTrue(started["notice"])
        self.assertIsNone(started["intent_id"])

    @patch("discordbot.activity.discord_json")
    def test_instance_first_fallback(self, discord):
        HeroDraft.objects.filter(pk=self.foreign.pk).update(
            state=HeroDraftState.ABANDONED
        )
        self.seed_instance("i-fallback")
        self.binding.draft = self.foreign
        self.binding.save()
        response, started = self.first_session(discord, "i-fallback", "102")
        self.assertEqual(
            response.data["initial_view"], {"kind": "hero", "id": self.hero.pk}
        )
        self.assertIsNone(response.data["notice"])
        self.assertEqual(started["source"], "instance_first")

    def test_menu_labels_statuses_and_external_paths(self):
        self.hero.game.bracket_type = "losers"
        self.hero.game.round = 2
        self.hero.game.save()
        self.assertEqual(hero_label(self.hero), "Losers Bracket R2 · A vs TBD")
        self.assertEqual(hero_status("choosing"), "waiting")
        self.assertEqual(hero_status("resuming"), "drafting")
        self.assertEqual(hero_status("abandoned"), "finished")
        self.assertEqual(team_status("pending"), "waiting")
        self.assertEqual(team_status("completed"), "finished")
        self.assertEqual(external_path("hero", 5, 9), "/herodraft/5")
        self.assertEqual(external_path("team", 40, 9), "/tournament/9/teams/draft")
        self.assertEqual(external_path("bracket", None, 9), "/tournament/9/bracket")
        notice = notice_for("team", self.team_draft.pk, None)
        self.assertEqual(
            notice["url"],
            f"{settings.SITE_URL}/tournament/{self.tournament.pk}/teams/draft",
        )
        self.assertEqual(notice["tournament_name"], "Activity")
        self.assertIsNone(notice_for("hero", 999999, None))

    @patch("discordbot.activity.discord_json")
    def test_unlinked_user_is_rejected(self, discord):
        discord.side_effect = [{"access_token": "secret"}, {"id": "999"}]
        response = activity_session(
            self.factory.post("/", {"code": "code", "instance_id": "i"})
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("secret", str(response.data))

    def test_token_rejects_tampering_expiry_and_inactive_users(self):
        token = self.credential()
        with self.assertRaises(ActivityAuthFailed) as caught:
            authenticate_token(token + "x", self.hero.pk, "hero")
        self.assertEqual(caught.exception.activity_code, "activity_session_ended")
        self.assertEqual(caught.exception.reason, "bad_signature")
        with patch("django.core.signing.time.time", return_value=9999999999):
            with self.assertRaises(ActivityAuthFailed) as caught:
                authenticate_token(token, self.hero.pk, "hero")
        self.assertEqual(caught.exception.activity_code, "activity_session_ended")
        self.assertEqual(caught.exception.reason, "expired")
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(ActivityAuthFailed) as caught:
            authenticate_token(token, self.hero.pk, "hero")
        self.assertEqual(caught.exception.activity_code, "activity_session_ended")
        self.assertEqual(caught.exception.reason, "inactive_user")

    def test_v2_token_authenticates_as_draft_scope_pin(self):
        token = self.legacy_token()
        user, identity = self.rest(f"/api/herodraft/{self.hero.pk}/", token)
        self.assertEqual(user, self.user)
        self.assertIsInstance(identity, ActivityIdentity)
        self.assertIsNone(identity.tournament_id)
        self.assertEqual(identity.pin, {"kind": "hero", "draft": self.hero.pk})
        self.assertEqual(identity.scope, "draft")
        self.assert_rest_code(
            f"/api/herodraft/{self.other.pk}/", token, "activity_out_of_scope"
        )

    def test_v2_token_for_other_destination_ends_session(self):
        token = self.legacy_token(draft=self.other.pk)
        with self.assertRaises(ActivityAuthFailed) as caught:
            token_identity(token)
        self.assertEqual(caught.exception.activity_code, "activity_session_ended")
        self.assertEqual(caught.exception.reason, "v2_mismatch")

    def test_new_tokens_are_tournament_scoped_v3(self):
        token = self.credential()
        data = signing.loads(token.replace(".", ":"), salt=SALT)
        self.assertEqual(SALT, "discord-draft-activity-v3")
        self.assertEqual(data["tournament"], self.tournament.pk)
        self.assertIsNone(data["pin"])
        self.assertNotIn("kind", data)
        self.assertNotIn("draft", data)

    def test_tournament_scope_allows_other_drafts_of_same_tournament(self):
        token = self.credential()
        user, identity = self.rest(f"/api/herodraft/{self.other.pk}/", token)
        self.assertEqual(user, self.user)
        self.assertIsInstance(identity, ActivityIdentity)
        self.assertEqual(identity.tournament_id, self.tournament.pk)
        self.assertIsNone(identity.pin)
        self.assertEqual(identity.scope, "tournament")
        user, identity = self.rest(
            f"/api/draft/{self.team_draft.pk}/ready/", token, "post"
        )
        self.assertEqual(identity.tournament_id, self.tournament.pk)
        self.assert_rest_code(
            f"/api/herodraft/{self.foreign.pk}/", token, "activity_out_of_scope"
        )
        for path in ["/api/users/1/", "/api/tournaments/init-draft"]:
            self.assert_rest_code(path, token, "activity_path_not_allowed", "post")
        self.assertIsNone(
            ActivityAuthentication().authenticate(self.factory.get("/api/current_user"))
        )

    def test_spectator_gets_403_on_other_draft_in_same_tournament(self):
        token = self.credential(user=self.spectator)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        response = client.post(f"/api/herodraft/{self.other.pk}/set-ready/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("code", response.data)

    def test_team_scope_checks_pick_round_belongs_to_bound_draft(self):
        token = self.credential()
        own_round = DraftRound.objects.create(
            draft=self.team_draft, captain=self.user, pick_number=1
        )
        user, _ = self.rest(
            "/api/tournaments/pick_player",
            token,
            "post",
            {"draft_round_pk": own_round.pk, "user_pk": self.spectator.pk},
        )
        self.assertEqual(user, self.user)
        other_draft = Draft.objects.create(tournament=self.other_tournament)
        round_ = DraftRound.objects.create(
            draft=other_draft, captain=self.user, pick_number=1
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        response = client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": round_.pk, "user_pk": self.spectator.pk},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "DraftActivity")
        self.assertEqual(response.data["code"], "activity_out_of_scope")
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
        self.assertNotIn("code", response.data)
        self.assertNotIn("WWW-Authenticate", response)

    def test_hero_suffix_allowlist_is_explicit(self):
        staff = CustomUser.objects.create_user(
            username="activity-staff", discordId="103", is_staff=True
        )
        for user in [self.user, staff]:
            DraftActivityInstance.objects.all().delete()
            token = self.credential(user=user)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
            for suffix in ["ssr", "reset", "abandon"]:
                with self.subTest(user=user.username, suffix=suffix):
                    response = client.post(f"/api/herodraft/{self.hero.pk}/{suffix}/")
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.data["code"], "activity_path_not_allowed")
                    self.assertEqual(response.data["detail"], PATH_NOT_ALLOWED)
            with self.subTest(user=user.username, suffix="unknown-thing"):
                path = f"/api/herodraft/{self.hero.pk}/unknown-thing/"
                self.assertEqual(client.post(path).status_code, 404)
                self.assert_rest_code(path, token, "activity_path_not_allowed", "post")
            for suffix in sorted(HERO_SUFFIXES):
                with self.subTest(user=user.username, accepted=suffix):
                    _, identity = self.rest(
                        f"/api/herodraft/{self.hero.pk}/{suffix}/", token
                    )
                    self.assertEqual(identity.user, user)

    def test_spectator_403_on_every_mutating_endpoint_for_other_draft(self):
        token = self.credential(user=self.spectator)
        DraftTeam.objects.create(draft=self.other, tournament_team=self.team)
        round_ = DraftRound.objects.create(
            draft=self.team_draft, captain=self.user, pick_number=1
        )
        hero_states = {
            "set-ready": HeroDraftState.WAITING_FOR_CAPTAINS,
            "trigger-roll": HeroDraftState.ROLLING,
            "submit-choice": HeroDraftState.CHOOSING,
            "submit-pick": HeroDraftState.DRAFTING,
            "pause": HeroDraftState.DRAFTING,
            "resume": HeroDraftState.PAUSED,
        }
        requests = [
            (f"/api/herodraft/{self.other.pk}/{suffix}/", {}, state)
            for suffix, state in hero_states.items()
        ]
        requests += [
            (f"/api/draft/{self.team_draft.pk}/{action}/", {}, None)
            for action in ["ready", "start", "pause", "resume"]
        ]
        requests += [
            (
                "/api/tournaments/pick_player",
                {"draft_round_pk": round_.pk, "user_pk": self.spectator.pk},
                None,
            ),
            ("/api/tournaments/undo-pick", {"draft_pk": self.team_draft.pk}, None),
        ]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        for path, body, state in requests:
            if state is not None:
                HeroDraft.objects.filter(pk=self.other.pk).update(state=state)
            with self.subTest(path=path):
                response = client.post(path, body, format="json")
                self.assertEqual(response.status_code, 403)

    def test_new_activity_endpoints_need_identity_only(self):
        token = self.credential(user=self.spectator)
        for path, method in [
            ("/api/current_user", "get"),
            ("/api/discord/activity/drafts/", "get"),
            ("/api/discord/activity/views/", "post"),
        ]:
            with self.subTest(path=path):
                user, identity = self.rest(path, token, method, {})
                self.assertEqual(user, self.spectator)
                self.assertEqual(identity.tournament_id, self.tournament.pk)

    def test_success_binds_user_into_request_log_context(self):
        clear_contextvars()
        self.addCleanup(clear_contextvars)
        token = self.credential()
        _, identity = self.rest("/api/current_user", token)
        context = get_contextvars()
        self.assertEqual(context["user.id"], self.user.pk)
        self.assertEqual(context["activity.instance_id"], identity.instance.instance_id)

    def test_rejection_is_logged(self):
        token = self.credential()
        path = f"/api/herodraft/{self.hero.pk}/reset/"
        with capture_logs() as logs:
            self.assert_rest_code(path, token, "activity_path_not_allowed", "post")
            self.assert_rest_code(
                f"/api/herodraft/{self.foreign.pk}/",
                token,
                "activity_out_of_scope",
            )
            self.assert_rest_code(
                "/api/current_user", token + "x", "activity_session_ended"
            )
        rejected = [e for e in logs if e["event"] == "activity_auth_rejected"]
        self.assertEqual(
            [(e["code"], e["reason"]) for e in rejected],
            [
                ("activity_path_not_allowed", "path_not_allowed"),
                ("activity_out_of_scope", "out_of_scope"),
                ("activity_session_ended", "bad_signature"),
            ],
        )
        self.assertEqual(rejected[0]["path"], path)
        for event in rejected:
            self.assertEqual(event["log_level"], "warning")
            self.assertEqual(event["surface"], "rest")
            self.assertEqual(event["system"], "discord")
            self.assertEqual(event["subsystem"], "activity")
            self.assertNotIn(token, str(event))

    def test_activity_failures_are_coded_401(self):
        token = self.credential()
        cases = [
            ("bad-token", "/api/current_user", "activity_session_ended"),
            (token, "/api/users/", "activity_path_not_allowed"),
        ]
        for credential, path, code in cases:
            with self.subTest(code=code):
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {credential}")
                response = client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "DraftActivity")
                self.assertEqual(response.data["code"], code)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token}")
        with override_settings(DISCORD_ACTIVITY_ENABLED=False):
            response = client.get("/api/current_user")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "DraftActivity")
        self.assertEqual(response.data["code"], "activity_disabled")

    def test_anonymous_website_request_still_403(self):
        response = APIClient().post(f"/api/herodraft/{self.hero.pk}/set-ready/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("WWW-Authenticate", response)

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
        instance = DraftActivityInstance.objects.create(
            instance_id="socket", guild_id="1", channel_id="2", draft=self.hero
        )
        resolver = AsyncMock(
            return_value=(
                ActivityIdentity(
                    user=user,
                    instance=instance,
                    tournament_id=self.tournament.pk,
                    pin=None,
                ),
                "captain",
            )
        )
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
        self.assertEqual(
            app.await_args.args[0]["activity"],
            {
                "instance_id": "socket",
                "tournament_id": self.tournament.pk,
                "kind": "hero",
                "draft_id": self.hero.pk,
                "role": "captain",
            },
        )
        self.assertNotIn("user", scope)
        self.assertNotIn("activity", scope)

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
        recreated, _ = resolve_instance("instance-hero", "101")
        self.assertNotEqual(recreated.pk, original_pk)
        self.assertEqual(recreated.draft_id, self.other.pk)
        for draft in [self.hero, self.other]:
            with self.assertRaises(AuthenticationFailed):
                authenticate_token(token, draft.pk, "hero")
        fresh = issue_activity_token(self.user, recreated)
        self.assertEqual(
            authenticate_token(fresh, self.other.pk, "hero").user, self.user
        )

    def test_channel_launch_never_invalidates_tokens(self):
        token = self.credential()
        self.binding.draft = self.foreign
        self.binding.save()
        identity = authenticate_token(token, self.hero.pk, "hero")
        self.assertEqual(identity.tournament_id, self.tournament.pk)
        authenticate_token(token, self.other.pk, "hero")

    def test_anchor_moved_out_of_tournament_keeps_token_valid(self):
        token = self.credential()
        Game.objects.filter(pk=self.hero.game_id).update(tournament=None)
        identity = authenticate_token(token, self.other.pk, "hero")
        self.assertEqual(identity.tournament_id, self.tournament.pk)
        with self.assertRaises(ActivityAuthFailed) as caught:
            authenticate_token(token, self.hero.pk, "hero")
        self.assertEqual(caught.exception.activity_code, "activity_out_of_scope")

    def test_tournament_from_channel_record_when_anchor_has_none(self):
        loose = HeroDraft.objects.create(game=Game.objects.create())
        instance = DraftActivityInstance.objects.create(
            instance_id="loose", guild_id="1", channel_id="2", draft=loose
        )
        token = issue_activity_token(self.user, instance)
        data = signing.loads(token.replace(".", ":"), salt=SALT)
        self.assertEqual(data["tournament"], self.tournament.pk)
        self.assertIsNone(data["pin"])
        identity = authenticate_token(token, self.other.pk, "hero")
        self.assertEqual(identity.scope, "tournament")

    def test_tournamentless_instance_pins_one_draft(self):
        loose = HeroDraft.objects.create(game=Game.objects.create())
        instance = DraftActivityInstance.objects.create(
            instance_id="loose", guild_id="1", channel_id="99", draft=loose
        )
        token = issue_activity_token(self.user, instance)
        data = signing.loads(token.replace(".", ":"), salt=SALT)
        self.assertIsNone(data["tournament"])
        self.assertEqual(data["pin"], {"kind": "hero", "draft": loose.pk})
        identity = authenticate_token(token, loose.pk, "hero")
        self.assertEqual(identity.pin, {"kind": "hero", "draft": loose.pk})
        self.assertEqual(identity.scope, "draft")
        for draft_id, kind in [(self.hero.pk, "hero"), (loose.pk, "team")]:
            with self.assertRaises(ActivityAuthFailed) as caught:
                authenticate_token(token, draft_id, kind)
            self.assertEqual(caught.exception.activity_code, "activity_out_of_scope")

    def test_forged_pin_on_v3_token_ends_session(self):
        loose = HeroDraft.objects.create(game=Game.objects.create())
        instance = DraftActivityInstance.objects.create(
            instance_id="loose", guild_id="1", channel_id="99", draft=loose
        )
        data = signing.loads(
            issue_activity_token(self.user, instance).replace(".", ":"), salt=SALT
        )
        data["pin"] = {"kind": "hero", "draft": self.other.pk}
        token = signing.dumps(data, salt=SALT).replace(":", ".")
        with self.assertRaises(ActivityAuthFailed) as caught:
            token_identity(token)
        self.assertEqual(caught.exception.reason, "pin_mismatch")
        for broken in [
            {**data, "pin": None},
            {**data, "pin": {"kind": "hero"}},
            {**data, "tournament": True, "pin": None},
        ]:
            token = signing.dumps(broken, salt=SALT).replace(":", ".")
            with self.assertRaises(ActivityAuthFailed) as caught:
                token_identity(token)
            self.assertEqual(caught.exception.activity_code, "activity_session_ended")

    def test_scope_reads_bypass_cacheops(self):
        token = self.credential()
        identity = authenticate_token(token, self.other.pk, "hero")
        Game.objects.filter(pk=self.other.game_id).update(
            tournament=self.other_tournament
        )
        with self.assertRaises(ActivityAuthFailed) as caught:
            authenticate_token(token, self.other.pk, "hero")
        self.assertEqual(caught.exception.activity_code, "activity_out_of_scope")
        for model, kind, draft_id in [
            (HeroDraft, "hero", self.hero.pk),
            (Draft, "team", self.team_draft.pk),
        ]:
            with patch.object(
                model.objects, "nocache", wraps=model.objects.nocache
            ) as nocache:
                self.assertTrue(scope_allows(identity, kind, draft_id))
            nocache.assert_called_once_with()
        with patch.object(
            DraftActivityInstance.objects,
            "nocache",
            wraps=DraftActivityInstance.objects.nocache,
        ) as nocache:
            token_identity(token)
        nocache.assert_called_once_with()
        own_round = DraftRound.objects.create(
            draft=self.team_draft, captain=self.user, pick_number=1
        )
        with patch.object(
            DraftRound.objects, "nocache", wraps=DraftRound.objects.nocache
        ) as nocache:
            self.rest(
                "/api/tournaments/pick_player",
                token,
                "post",
                {"draft_round_pk": own_round.pk, "user_pk": self.spectator.pk},
            )
        nocache.assert_called_once_with()

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
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.data["code"], "activity_out_of_scope")

    def test_oversized_and_zero_padded_paths_do_not_bypass_kind_scope(self):
        token = self.credential("team")
        auth = ActivityAuthentication()
        for path in [
            f"/api/herodraft/{self.hero.pk:030d}/set-ready/",
            f"/api/herodraft/{2**63}/set-ready/",
            f"/api/draft/{self.team_draft.pk:030d}/ready/",
        ]:
            with self.assertRaises(ActivityAuthFailed) as caught:
                auth.authenticate(
                    self.factory.post(path, HTTP_AUTHORIZATION=f"DraftActivity {token}")
                )
            self.assertEqual(caught.exception.activity_code, "activity_out_of_scope")

    def test_team_undo_and_style_scope_match_the_tournament(self):
        foreign_draft = Draft.objects.create(tournament=self.other_tournament)
        for kind in ["team", "hero"]:
            token = self.credential(kind)
            for path, key in [
                ("/api/tournaments/undo-pick", "draft_pk"),
                ("/api/draft/get-style-mmrs", "pk"),
            ]:
                user, _ = self.rest(path, token, "post", {key: self.team_draft.pk})
                self.assertEqual(user, self.user)
                for value in [foreign_draft.pk, 2**63, None, [], True]:
                    with self.subTest(kind=kind, path=path, value=value):
                        self.assert_rest_code(
                            path, token, "activity_out_of_scope", "post", {key: value}
                        )

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
        self.assertNotIn("code", response.data)
        self.assertNotIn("WWW-Authenticate", response)


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class ActivitySocketDatabaseTests(ClearIntentsMixin, TransactionTestCase):
    """Exercise the real async credential lookup on a committed database."""

    intent_user_ids = ("303",)

    def setUp(self):
        super().setUp()
        user = CustomUser.objects.create_user(
            username="socket-captain", discordId="303"
        )
        self.user_pk = user.pk
        tournament = Tournament.objects.create(
            name="Socket activity", date_played=date.today()
        )
        self.tournament_pk = tournament.pk
        self.anchor_game_pk = Game.objects.create(tournament=tournament).pk
        draft = HeroDraft.objects.create(game_id=self.anchor_game_pk)
        self.draft_pk = draft.pk
        team = Team.objects.create(name="S", tournament=tournament, captain=user)
        DraftTeam.objects.create(draft=draft, tournament_team=team)
        self.second_game_pk = Game.objects.create(tournament=tournament).pk
        self.second_pk = HeroDraft.objects.create(game_id=self.second_game_pk).pk
        DraftActivityChannel.objects.create(guild_id="1", channel_id="2", draft=draft)
        instance = DraftActivityInstance.objects.create(
            instance_id="socket-instance", guild_id="1", channel_id="2", draft=draft
        )
        self.token = issue_activity_token(user, instance)

    def _router(self, application):
        return URLRouter(
            [
                url_path(
                    "draft/<int:draft_id>/",
                    ActivitySocketMiddleware(application, "hero"),
                )
            ]
        )

    async def test_valid_socket_uses_real_database_identity(self):
        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": str(scope["user"].pk)})
            await receive()

        socket = WebsocketCommunicator(
            self._router(application),
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", self.token],
        )
        connected, subprotocol = await socket.connect(timeout=5)
        self.assertTrue(connected)
        # Browsers fail a handshake that echoes none of the offered protocols.
        self.assertEqual(subprotocol, "draftactivity")
        self.assertEqual(await socket.receive_from(), str(self.user_pk))
        await socket.disconnect()

    async def test_rejected_credential_closes_with_4401_after_handshake(self):
        application = AsyncMock()
        socket = WebsocketCommunicator(
            self._router(application),
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", "forged"],
        )
        connected, subprotocol = await socket.connect(timeout=5)
        self.assertTrue(connected)
        self.assertEqual(subprotocol, "draftactivity")
        self.assertEqual(
            await socket.receive_output(timeout=5),
            {"type": "websocket.close", "code": 4401},
        )
        application.assert_not_awaited()
        await socket.disconnect()

    async def test_out_of_scope_connect_closes_4403_and_is_logged(self):
        foreign = await database_sync_to_async(HeroDraft.objects.create)(
            game=await database_sync_to_async(Game.objects.create)()
        )
        application = AsyncMock()
        socket = WebsocketCommunicator(
            self._router(application),
            f"/draft/{foreign.pk}/",
            subprotocols=["draftactivity", self.token],
        )
        with capture_logs() as logs:
            self.assertTrue((await socket.connect(timeout=5))[0])
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4403},
            )
        application.assert_not_awaited()
        await socket.disconnect()
        rejected = [e for e in logs if e["event"] == "activity_auth_rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["surface"], "socket")
        self.assertEqual(rejected[0]["kind"], "hero")
        self.assertEqual(rejected[0]["draft_id"], foreign.pk)
        self.assertEqual(rejected[0]["reason"], "out_of_scope")
        self.assertEqual(rejected[0]["code"], "activity_out_of_scope")
        self.assertEqual(rejected[0]["system"], "discord")
        self.assertEqual(rejected[0]["subsystem"], "activity")
        self.assertNotIn(self.token, str(rejected[0]))

    async def _open_guarded_socket(self, token=None, draft_pk=None):
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

        socket = WebsocketCommunicator(
            self._router(application),
            f"/draft/{draft_pk or self.draft_pk}/",
            subprotocols=["draftactivity", token or self.token],
        )
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        return socket

    async def _assert_round_trip_after_revalidation(self, socket):
        await asyncio.sleep(0.1)
        await socket.send_to(text_data="ping")
        self.assertEqual(await socket.receive_from(timeout=5), "heartbeat")
        await asyncio.sleep(0.1)
        await socket.send_to(text_data="ping")
        self.assertEqual(await socket.receive_from(timeout=5), "heartbeat")

    async def test_same_token_connects_to_second_draft_in_tournament(self):
        socket = await self._open_guarded_socket(draft_pk=self.second_pk)
        await socket.send_to(text_data="ping")
        self.assertEqual(await socket.receive_from(timeout=5), "heartbeat")
        await socket.disconnect()

    async def test_revalidation_survives_channel_rebind(self):
        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket()
            await database_sync_to_async(
                DraftActivityChannel.objects.filter(guild_id="1", channel_id="2").update
            )(draft_id=self.second_pk)
            await self._assert_round_trip_after_revalidation(socket)
            await socket.disconnect()

    async def test_draft_removed_from_tournament_closes_4403(self):
        with (
            patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03),
            capture_logs() as logs,
        ):
            socket = await self._open_guarded_socket(draft_pk=self.second_pk)
            await database_sync_to_async(
                Game.objects.filter(pk=self.second_game_pk).update
            )(tournament=None)
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4403},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "out_of_scope")
        self.assertEqual(closed[0]["close_code"], 4403)
        self.assertEqual(closed[0]["draft_id"], self.second_pk)
        self.assertEqual(closed[0]["role"], "spectator")
        self.assertEqual(closed[0]["user_id"], self.user_pk)
        self.assertEqual(closed[0]["instance_id"], "socket-instance")
        self.assertEqual(closed[0]["tournament_id"], self.tournament_pk)
        self.assertIsInstance(closed[0]["duration_s"], float)

    async def test_anchor_removed_from_tournament_keeps_other_sockets_open(self):
        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket(draft_pk=self.second_pk)
            await database_sync_to_async(
                Game.objects.filter(pk=self.anchor_game_pk).update
            )(tournament=None)
            await self._assert_round_trip_after_revalidation(socket)
            await socket.disconnect()

    async def test_anchor_deleted_closes_4401(self):
        with patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03):
            socket = await self._open_guarded_socket(draft_pk=self.second_pk)
            await database_sync_to_async(
                HeroDraft.objects.filter(pk=self.draft_pk).delete
            )()
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4401},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()

    async def test_open_socket_closes_after_mapping_revocation(self):
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
        # Warm the cacheable lookup used elsewhere before a bulk deactivation.
        # Cacheops does not invalidate ordinary QuerySet.update() calls.
        await database_sync_to_async(CustomUser.objects.get)(
            pk=self.user_pk, is_active=True
        )
        with (
            patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03),
            capture_logs() as logs,
        ):
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
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual([e["reason"] for e in closed], ["revoked"])

    async def test_disabled_flag_closes_4401(self):
        with (
            patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 0.03),
            capture_logs() as logs,
        ):
            socket = await self._open_guarded_socket()
            with self.settings(DISCORD_ACTIVITY_ENABLED=False):
                self.assertEqual(
                    await socket.receive_output(timeout=5),
                    {"type": "websocket.close", "code": 4401},
                )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()
        rejected = [e for e in logs if e["event"] == "activity_auth_rejected"]
        self.assertEqual([e["reason"] for e in rejected], ["disabled"])
        self.assertEqual(rejected[0]["code"], "activity_disabled")
        self.assertEqual(rejected[0]["surface"], "socket")
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual(
            [(e["reason"], e["close_code"]) for e in closed], [("disabled", 4401)]
        )

    async def test_open_socket_expires_before_periodic_revalidation(self):
        data = signing.loads(self.token.replace(".", ":"), salt=SALT)
        data["expires"] = time.time() + 0.1
        token = signing.dumps(data, salt=SALT).replace(":", ".")
        with (
            patch("discordbot.activity_auth.SOCKET_REVALIDATE_SECONDS", 30),
            capture_logs() as logs,
        ):
            socket = await self._open_guarded_socket(token)
            self.assertEqual(
                await socket.receive_output(timeout=5),
                {"type": "websocket.close", "code": 4401},
            )
            await self.consumer_cleaned_up.wait()
            await socket.disconnect()
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual([e["reason"] for e in closed], ["expired"])
        rejected = [e for e in logs if e["event"] == "activity_auth_rejected"]
        self.assertEqual(
            [(e["reason"], e["code"], e["surface"]) for e in rejected],
            [("expired", "activity_session_ended", "socket")],
        )

    async def test_client_disconnect_is_logged(self):
        with capture_logs() as logs:
            socket = await self._open_guarded_socket()
            await socket.disconnect(code=1000)
            await self.consumer_cleaned_up.wait()
            await asyncio.sleep(0.05)
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "client")
        self.assertEqual(closed[0]["close_code"], 1000)
        self.assertEqual(closed[0]["role"], "captain")
        self.assertEqual(closed[0]["kind"], "hero")
        self.assertEqual(closed[0]["system"], "discord")
        self.assertEqual(closed[0]["subsystem"], "activity")

    async def test_consumer_crash_is_logged_and_reraised(self):
        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            raise RuntimeError("consumer exploded")

        socket = WebsocketCommunicator(
            self._router(application),
            f"/draft/{self.draft_pk}/",
            subprotocols=["draftactivity", self.token],
        )
        with capture_logs() as logs:
            self.assertTrue((await socket.connect(timeout=5))[0])
            with self.assertRaises(RuntimeError):
                await socket.receive_output(timeout=5)
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "error")
        self.assertEqual(closed[0]["close_code"], 1011)
        self.assertEqual(closed[0]["error_type"], "RuntimeError")
        self.assertEqual(closed[0]["user_id"], self.user_pk)
        self.assertEqual(closed[0]["instance_id"], "socket-instance")

    async def test_consumer_cancel_is_logged_and_reraised(self):
        socket = await self._open_guarded_socket()
        with capture_logs() as logs:
            socket.future.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await socket.future
        closed = [e for e in logs if e["event"] == "activity_socket_closed"]
        self.assertEqual([e["reason"] for e in closed], ["cancelled"])

    async def test_scope_activity_is_set(self):
        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            await send(
                {"type": "websocket.send", "text": json.dumps(scope["activity"])}
            )
            await receive()

        expected = {
            self.draft_pk: "captain",
            self.second_pk: "spectator",
        }
        for draft_pk, role in expected.items():
            socket = WebsocketCommunicator(
                self._router(application),
                f"/draft/{draft_pk}/",
                subprotocols=["draftactivity", self.token],
            )
            self.assertTrue((await socket.connect(timeout=5))[0])
            self.assertEqual(
                json.loads(await socket.receive_from()),
                {
                    "instance_id": "socket-instance",
                    "tournament_id": self.tournament_pk,
                    "kind": "hero",
                    "draft_id": draft_pk,
                    "role": role,
                },
            )
            await socket.disconnect()

    @override_settings(ALLOWED_HOSTS=["123.discordsays.com"])
    async def test_discord_proxy_origin_is_allowed_and_foreign_origin_is_denied(self):
        async def application(scope, receive, send):
            await receive()
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": str(scope["user"].pk)})
            await receive()

        router = AllowedHostsOriginValidator(self._router(application))
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
