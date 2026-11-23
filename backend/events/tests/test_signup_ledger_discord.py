import itertools
from collections.abc import Callable
from typing import Any

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.models import CustomUser, GameType
from discordbot.models import DiscordMessageLog
from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.discord import (
    handle_reaction_cancel,
    handle_reaction_signup,
    handle_tentative_button,
)
from events.models import Event, EventSignup, SignupLedgerEntry
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile

TOKEN = "test-internal-token"
BASE = "/api/internal/discord"

_ids = itertools.count(1)

Case = Callable[[], tuple[str, dict[str, Any], CustomUser, Event]]


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SignupLedgerDiscordTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        clear_contextvars()
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTERNAL_TOKEN=TOKEN)

    def tearDown(self) -> None:
        clear_contextvars()
        super().tearDown()

    def _entries(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event=event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )

    def _discord_user(self) -> tuple[CustomUser, OrgUser, str]:
        n = next(_ids)
        discord_id = f"2000000000000{n:05d}"
        user = CustomUser.objects.create_user(
            username=f"ledger_discord_{n}", password="testpass"
        )
        user.discordId = discord_id
        user.save()
        org_user, _ = OrgUser.objects.get_or_create(user=user, organization=self.org)
        return user, org_user, discord_id

    def _event(self, **overrides: object) -> Event:
        return self.make_event(game_type=GameType.DOTA2, **overrides)

    def _case_signup_button(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, org_user, discord_id = self._discord_user()
        PlayerDotaProfile.objects.create(
            org_user=org_user,
            rank_status="active",
            rank_declared_at=timezone.now(),
            rank_medal="Legend",
            pos_1=True,
            pos_2=True,
            pos_5=True,
        )
        event = self._event()
        body = {"event_id": event.pk, "discord_user_id": discord_id}
        return f"{BASE}/signup-button/", body, user, event

    def _case_modal_submit(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, _, discord_id = self._discord_user()
        user.steamid = None
        user.steam_account_id = None
        user.save()
        event = self.make_event(game_type=GameType.DEADLOCK)
        body = {
            "event_id": event.pk,
            "discord_user_id": discord_id,
            "game_type": GameType.DEADLOCK,
            "values": {
                "friend_id": str(40000 + next(_ids)),
                "deadlock_rank": "Phantom IV",
                "deadlock_date": "last week",
            },
        }
        return f"{BASE}/signup-modal-submit/", body, user, event

    def _case_rank_medal(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, org_user, discord_id = self._discord_user()
        PlayerDotaProfile.objects.create(
            org_user=org_user, rank_status="active", pos_1=True
        )
        event = self._event()
        body = {"event_id": event.pk, "discord_user_id": discord_id, "medal": "Legend"}
        return f"{BASE}/rank-medal-select/", body, user, event

    def _case_battle_cup(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, _, discord_id = self._discord_user()
        event = self._event()
        body = {"event_id": event.pk, "discord_user_id": discord_id, "tier": "5"}
        return f"{BASE}/battle-cup-submit/", body, user, event

    def _case_screenshot(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, org_user, discord_id = self._discord_user()
        PlayerDotaProfile.objects.create(org_user=org_user)
        event = self._event()
        body = {
            "event_id": event.pk,
            "discord_user_id": discord_id,
            "screenshot_type": "rank",
            "attachment_url": "https://cdn.discord.com/test/screenshot.png",
        }
        return f"{BASE}/screenshot-upload/", body, user, event

    def _case_decline(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, _, discord_id = self._discord_user()
        event = self._event()
        body = {"event_id": event.pk, "discord_user_id": discord_id}
        return f"{BASE}/decline-button/", body, user, event

    def _case_tentative(self) -> tuple[str, dict[str, Any], CustomUser, Event]:
        user, _, discord_id = self._discord_user()
        event = self._event()
        body = {"event_id": event.pk, "discord_user_id": discord_id}
        return f"{BASE}/tentative-button/", body, user, event

    def _cases(self) -> list[tuple[str, Case, SignupAction]]:
        return [
            ("signup_button", self._case_signup_button, SignupAction.SIGNED_UP),
            ("signup_modal_submit", self._case_modal_submit, SignupAction.SIGNED_UP),
            ("rank_medal_select", self._case_rank_medal, SignupAction.SIGNED_UP),
            ("battle_cup_submit", self._case_battle_cup, SignupAction.SIGNED_UP),
            ("screenshot_upload", self._case_screenshot, SignupAction.SIGNED_UP),
            ("decline_button", self._case_decline, SignupAction.DECLINED),
            ("tentative_button", self._case_tentative, SignupAction.SIGNED_UP),
        ]

    def _post(self, url: str, body: dict[str, Any], **extra: str) -> Any:
        response = self.client.post(url, body, format="json", **extra)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_internal_views_record_interaction_id(self) -> None:
        for name, case, action in self._cases():
            with self.subTest(view=name):
                url, body, user, event = case()
                response = self._post(url, body, HTTP_X_DISCORD_INTERACTION_ID="123")
                entries = self._entries(event)
                self.assertEqual(
                    [e.action for e in entries], [action], response.content
                )
                entry = entries[0]
                self.assertEqual(entry.means, SignupMeans.DISCORD_BUTTON)
                self.assertEqual(entry.correlation_id, "123")
                self.assertEqual(entry.actor_role, ActorRole.MEMBER)
                self.assertEqual(entry.actor_user_id, user.pk)
                self.assertEqual(entry.subject_user_id, user.pk)

    def test_malformed_and_overlong_headers_are_ignored(self) -> None:
        for header in ("12a", "", "1" * 21, "-5", "12 "):
            with self.subTest(header=header):
                url, body, _, event = self._case_tentative()
                self._post(url, body, HTTP_X_DISCORD_INTERACTION_ID=header)
                (entry,) = self._entries(event)
                self.assertEqual(entry.correlation_id, "")

    def test_twenty_digit_header_is_accepted(self) -> None:
        url, body, _, event = self._case_tentative()
        self._post(url, body, HTTP_X_DISCORD_INTERACTION_ID="9" * 20)
        (entry,) = self._entries(event)
        self.assertEqual(entry.correlation_id, "9" * 20)

    def test_decline_promotion_inherits_interaction_id(self) -> None:
        user, _, discord_id = self._discord_user()
        event = self._event(max_players=1)
        seated = EventSignup.objects.create(
            event=event, user=user, status=SignupStatus.APPROVED
        )
        waiter = self.make_user()
        waiting = EventSignup.objects.create(
            event=event,
            user=waiter,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        self._post(
            f"{BASE}/decline-button/",
            {"event_id": event.pk, "discord_user_id": discord_id},
            HTTP_X_DISCORD_INTERACTION_ID="456",
        )
        declined, promoted = self._entries(event)
        self.assertEqual(declined.action, SignupAction.DECLINED)
        self.assertEqual(declined.signup_id, seated.pk)
        self.assertEqual(declined.correlation_id, "456")
        self.assertEqual(promoted.action, SignupAction.PROMOTED)
        self.assertEqual(promoted.signup_id, waiting.pk)
        self.assertEqual(promoted.caused_by_id, declined.pk)
        self.assertEqual(promoted.correlation_id, "456")
        self.assertEqual(promoted.actor_role, ActorRole.SYSTEM)

    def test_interaction_id_does_not_leak_to_next_request(self) -> None:
        url, body, _, first_event = self._case_tentative()
        self._post(url, body, HTTP_X_DISCORD_INTERACTION_ID="789")
        url, body, _, second_event = self._case_tentative()
        self._post(url, body)
        (first,) = self._entries(first_event)
        (second,) = self._entries(second_event)
        self.assertEqual(first.correlation_id, "789")
        self.assertEqual(second.correlation_id, "")

    def test_public_request_ignores_interaction_header(self) -> None:
        user = self.make_user()
        event = self.make_event()
        client = APIClient()
        client.force_authenticate(user)
        response = client.post(
            f"/api/events/{event.pk}/signup/",
            {"intent": "rsvp"},
            format="json",
            HTTP_X_DISCORD_INTERACTION_ID="321",
        )
        self.assertLess(response.status_code, 300, response.content)
        (entry,) = self._entries(event)
        self.assertEqual(entry.means, SignupMeans.WEB)
        self.assertEqual(entry.correlation_id, "")

    def test_handler_called_with_bound_contextvar(self) -> None:
        user, _, discord_id = self._discord_user()
        event = self._event()
        bind_contextvars(interaction_id="555")
        result = handle_tentative_button(event.pk, discord_id)
        self.assertNotEqual(result.get("action"), "error", result)
        (entry,) = self._entries(event)
        self.assertEqual(entry.correlation_id, "555")
        self.assertEqual(entry.means, SignupMeans.DISCORD_BUTTON)
        self.assertEqual(entry.actor_user_id, user.pk)


class ReactionLedgerTests(EventTestCase):
    MESSAGE_ID = "999888777"

    def setUp(self) -> None:
        super().setUp()
        clear_contextvars()
        DiscordMessageLog.objects.create(
            channel_id="1482767177063858216",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=self.event.pk,
            discord_message_id=self.MESSAGE_ID,
            success=True,
        )
        self.event.state = "signups_open"
        self.event.auto_approve = True
        self.event.save()
        self.discord_id = "100000000000000001"
        self.user.discordId = self.discord_id
        self.user.save()

    def tearDown(self) -> None:
        clear_contextvars()
        super().tearDown()

    def test_reaction_add_and_remove_share_reaction_key(self) -> None:
        bind_contextvars(interaction_id="111")
        ok, detail = handle_reaction_signup(self.MESSAGE_ID, self.discord_id)
        self.assertTrue(ok, detail)
        ok, detail = handle_reaction_cancel(self.MESSAGE_ID, self.discord_id)
        self.assertTrue(ok, detail)
        entries = list(
            SignupLedgerEntry.objects.filter(event=self.event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )
        self.assertEqual(
            [e.action for e in entries], [SignupAction.SIGNED_UP, SignupAction.WITHDREW]
        )
        key = f"reaction:{self.MESSAGE_ID}:{self.discord_id}"
        for entry in entries:
            self.assertEqual(entry.means, SignupMeans.DISCORD_REACTION)
            self.assertEqual(entry.correlation_id, key)
            self.assertEqual(entry.actor_role, ActorRole.MEMBER)
            self.assertEqual(entry.actor_user_id, self.user.pk)
