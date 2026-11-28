from datetime import timedelta
from typing import Any

from django.test import override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from discordbot.models import (
    ChannelType,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DMType,
)
from events.constants import Commitment, SignupStatus
from events.models import Event, EventSignup
from events.tests.base import EventTestCase
from org.models import OrgUser

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}

EMBED_SIGNUP_KEYS = (
    "user",
    "username",
    "status",
    "waitlist_position",
    "holds_seat",
    "commitment",
    "line_rank",
)
EMBED_USER_DATA_KEYS = ("username", "nickname", "discordId", "guildNickname")


def embed_subset(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row[k] for k in EMBED_SIGNUP_KEYS}
    out["user_data"] = {k: row["user_data"].get(k) for k in EMBED_USER_DATA_KEYS}
    return out


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DiscordStateFixture(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def seed_discord_event(self) -> tuple[Event, DiscordEvent]:
        event = self.make_event(name="State Event")
        de = DiscordEvent.objects.create(
            event=event, guild_id="555000", scheduled_event_id="777000111"
        )
        base = tz.now() - timedelta(hours=1)
        for offset, action, success in (
            (1, "signup_reminder", True),
            (2, "start_mention", True),
            (3, "attendance_reminder", False),
        ):
            row = DiscordEventLog.objects.create(
                discord_event=de, action=action, success=success
            )
            DiscordEventLog.objects.filter(pk=row.pk).update(
                created_at=base + timedelta(minutes=offset)
            )
        org_user, _ = OrgUser.objects.get_or_create(
            user=self.user, organization=self.org
        )
        DiscordEventDM.objects.create(
            discord_event=de, org_user=org_user, dm_type=DMType.SIGNUP_REMINDER
        )
        DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="880001",
            channel_type=ChannelType.FORUM,
            message_id="990001",
            thread_id="880002",
            has_posted=True,
        )
        return event, de

    def seed_signups(self) -> Event:
        event = self.make_event(name="Signup Event", max_players=2)
        guildy = self.make_user()
        guildy.nickname = "PlainNick"
        guildy.discordId = "111000"
        guildy.save()
        OrgUser.objects.filter(user=guildy, organization=self.org).update(
            guild_nickname="Guildy"
        )
        rsvp = self.make_user()
        rsvp.nickname = "RsvpNick"
        rsvp.save()
        waiter = self.make_user()
        waiter.nickname = "Waiter"
        waiter.save()
        gone = self.make_user()
        gone.nickname = "Gone"
        gone.save()
        EventSignup.objects.create(
            event=event, user=guildy, status=SignupStatus.CONFIRMED
        )
        EventSignup.objects.create(
            event=event,
            user=rsvp,
            status=SignupStatus.RSVP,
            commitment=Commitment.MAYBE,
        )
        EventSignup.objects.create(
            event=event,
            user=waiter,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        EventSignup.objects.create(
            event=event, user=gone, status=SignupStatus.CANCELLED
        )
        self.signup_users = {
            "guildy": guildy,
            "rsvp": rsvp,
            "waiter": waiter,
            "gone": gone,
        }
        return event


class DiscordStateGoldenTest(DiscordStateFixture):
    def test_event_state_endpoint_json_literal(self) -> None:
        event, de = self.seed_discord_event()

        resp = self.client.get(
            f"/api/internal/discord/event-state/{event.pk}/", **HEADERS
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(),
            {
                "has_discord_event": True,
                "scheduled_event_id": "777000111",
                "signup_posted": True,
                "fired_actions": ["start_mention", "signup_reminder"],
                "has_dms": True,
                "discord_event_pk": de.pk,
                "signup_message_id": "990001",
                "signup_channel_id": "880001",
                "signup_thread_id": "880002",
                "signup_channel_type": "forum",
            },
        )

    def test_event_state_endpoint_without_discord_event(self) -> None:
        event = self.make_event(name="Bare Event")

        resp = self.client.get(
            f"/api/internal/discord/event-state/{event.pk}/", **HEADERS
        )

        self.assertEqual(
            resp.json(),
            {
                "has_discord_event": False,
                "scheduled_event_id": None,
                "signup_posted": False,
                "fired_actions": [],
                "has_dms": False,
            },
        )

    def test_event_state_endpoint_legacy_rows(self) -> None:
        event = self.make_event(name="Legacy Event")
        de = DiscordEvent.objects.create(event=event, guild_id="555000")
        DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="880003",
            channel_type="",
            message_id="990003",
            has_posted=True,
        )

        resp = self.client.get(
            f"/api/internal/discord/event-state/{event.pk}/", **HEADERS
        )

        self.assertEqual(
            resp.json(),
            {
                "has_discord_event": True,
                "scheduled_event_id": None,
                "signup_posted": True,
                "fired_actions": [],
                "has_dms": False,
                "discord_event_pk": de.pk,
                "signup_message_id": "990003",
                "signup_channel_id": "880003",
                "signup_thread_id": None,
                "signup_channel_type": None,
            },
        )

    def test_check_log_endpoint_literal(self) -> None:
        for source_id, success in ((101, None), (102, True), (103, False)):
            DiscordMessageLog.objects.create(
                channel_id="1",
                embed_data={},
                source="event_reminder",
                source_id=source_id,
                success=success,
            )

        for source_id, expected in (
            (101, True),
            (102, True),
            (103, False),
            (104, False),
        ):
            with self.subTest(source_id=source_id):
                resp = self.client.get(
                    "/api/internal/discord/check-log/",
                    {"source": "event_reminder", "source_id": source_id},
                    **HEADERS,
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json(), {"exists": expected})

        resp = self.client.get(
            "/api/internal/discord/check-log/", {"source": "event_reminder"}, **HEADERS
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"error": "source and source_id required"})

    def test_signup_list_json_literal(self) -> None:
        event = self.seed_signups()
        u = {k: v.pk for k, v in self.signup_users.items()}

        resp = self.client.get("/api/events/signups/", {"event": event.pk}, **HEADERS)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            [embed_subset(row) for row in resp.json()],
            [
                {
                    "user": u["guildy"],
                    "username": "Guildy",
                    "status": "confirmed",
                    "waitlist_position": None,
                    "holds_seat": True,
                    "commitment": "main",
                    "line_rank": 1,
                    "user_data": {
                        "username": self.signup_users["guildy"].username,
                        "nickname": "PlainNick",
                        "discordId": "111000",
                        "guildNickname": "Guildy",
                    },
                },
                {
                    "user": u["rsvp"],
                    "username": "RsvpNick",
                    "status": "rsvp",
                    "waitlist_position": None,
                    "holds_seat": True,
                    "commitment": "maybe",
                    "line_rank": 2,
                    "user_data": {
                        "username": self.signup_users["rsvp"].username,
                        "nickname": "RsvpNick",
                        "discordId": None,
                        "guildNickname": None,
                    },
                },
                {
                    "user": u["waiter"],
                    "username": "Waiter",
                    "status": "waitlisted",
                    "waitlist_position": 1,
                    "holds_seat": False,
                    "commitment": "main",
                    "line_rank": 3,
                    "user_data": {
                        "username": self.signup_users["waiter"].username,
                        "nickname": "Waiter",
                        "discordId": None,
                        "guildNickname": None,
                    },
                },
                {
                    "user": u["gone"],
                    "username": "Gone",
                    "status": "cancelled",
                    "waitlist_position": None,
                    "holds_seat": False,
                    "commitment": "main",
                    "line_rank": None,
                    "user_data": {
                        "username": self.signup_users["gone"].username,
                        "nickname": "Gone",
                        "discordId": None,
                        "guildNickname": None,
                    },
                },
            ],
        )

    def test_signup_list_member_gate_hides_guild_nickname_from_anonymous(self) -> None:
        event = self.seed_signups()

        rows = self.client.get("/api/events/signups/", {"event": event.pk}).json()

        self.assertEqual(rows[0]["username"], "PlainNick")
        self.assertNotIn("guildNickname", rows[0]["user_data"])

    def test_signup_detail_actions_without_event_param(self) -> None:
        event = self.seed_signups()
        pending_user = self.make_user()
        signup = EventSignup.objects.create(
            event=event, user=pending_user, status=SignupStatus.PENDING_APPROVAL
        )
        listed = EventSignup.objects.get(event=event, user=self.signup_users["rsvp"])

        resp = self.client.get(f"/api/events/signups/{listed.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], listed.pk)
        self.assertEqual(resp.json()["line_rank"], 2)

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/events/signups/{signup.pk}/approve/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], signup.pk)
        self.assertNotEqual(resp.json()["status"], SignupStatus.PENDING_APPROVAL)
