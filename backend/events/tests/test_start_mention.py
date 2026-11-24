"""Pre-start member mention: chunking, scope, lease and manual fire."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog
from events.constants import Commitment, SignupStatus, StartMentionScope
from events.models import EventSignup
from events.schemas import EventSignupSchema
from events.start_mention import (
    MAX_CONTENT_CHARS,
    chunk_mentions,
    start_mention_recipients,
)
from events.tasks import send_start_mention
from events.tests.base import EventTestCase
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response
from user.schemas import TournamentUserSchema

HEADER = "Weekly Inhouse starts <t:1900000000:R>."
MISCONFIGURED_DESCRIPTION = (
    'Needs a signup post: enable "Post event signup embed" with a channel, '
    "or a pre-day announcement with a channel"
)
CONFIGURED_DESCRIPTION = (
    "Mentions signed-up members on the signup post 30m before event"
)


def _ids(count: int, digits: int = 18) -> list[str]:
    base = 10 ** (digits - 1)
    return [str(base + i) for i in range(count)]


def _signup(
    pk: int,
    status: str,
    *,
    discord_id: str | None = "1",
    commitment: str = Commitment.MAIN,
    holds_seat: bool | None = None,
) -> EventSignupSchema:
    return EventSignupSchema(
        id=pk,
        event=1,
        user=pk,
        status=status,
        commitment=commitment,
        holds_seat=holds_seat,
        user_data=TournamentUserSchema(pk=pk, discordId=discord_id),
    )


class ChunkMentionsTest(EventTestCase):
    def test_250_members_make_four_messages_within_limits(self) -> None:
        ids = _ids(250)
        chunks = chunk_mentions(ids, HEADER)

        self.assertEqual(len(chunks), 4)
        self.assertEqual([len(c.user_ids) for c in chunks], [80, 80, 80, 10])
        for chunk in chunks:
            self.assertLessEqual(len(chunk.content), MAX_CONTENT_CHARS)
            self.assertLessEqual(chunk.content.count("<@"), 100)
            self.assertEqual(chunk.content.count("<@"), len(chunk.user_ids))
        self.assertTrue(chunks[0].content.startswith(HEADER))
        self.assertNotIn(HEADER, chunks[1].content)
        self.assertEqual([i for c in chunks for i in c.user_ids], ids)

    def test_long_ids_and_long_header_stay_under_char_limit(self) -> None:
        header = "x" * 300
        chunks = chunk_mentions(_ids(250, digits=20), header)

        for chunk in chunks:
            self.assertLessEqual(len(chunk.content), MAX_CONTENT_CHARS)
            self.assertLessEqual(len(chunk.user_ids), 80)
        self.assertEqual(sum(len(c.user_ids) for c in chunks), 250)

    def test_no_members_makes_no_messages(self) -> None:
        self.assertEqual(chunk_mentions([], HEADER), [])


class StartMentionScopeTest(EventTestCase):
    def setUp(self) -> None:
        self.signups = [
            _signup(1, SignupStatus.RSVP, discord_id="101"),
            _signup(2, SignupStatus.CONFIRMED, discord_id="102"),
            _signup(3, SignupStatus.WAITLISTED, discord_id="103"),
            _signup(4, SignupStatus.TENTATIVE, discord_id="104"),
            _signup(5, SignupStatus.RSVP, discord_id="105", commitment="maybe"),
            _signup(6, SignupStatus.CANCELLED, discord_id="106"),
            _signup(7, SignupStatus.REJECTED, discord_id="107"),
            _signup(8, SignupStatus.DROPPED, discord_id="108"),
            _signup(9, SignupStatus.RSVP, discord_id=None),
            _signup(10, SignupStatus.WAITLISTED, discord_id=""),
        ]

    def test_main_scope_is_seated_main_commitment(self) -> None:
        result = start_mention_recipients(self.signups, StartMentionScope.MAIN)
        self.assertEqual(result.discord_ids, ["101", "102"])
        self.assertEqual(result.skipped_no_discord_id, 1)

    def test_all_active_scope_excludes_declined(self) -> None:
        result = start_mention_recipients(self.signups, StartMentionScope.ALL_ACTIVE)
        self.assertEqual(result.discord_ids, ["101", "102", "103", "104", "105"])
        self.assertEqual(result.skipped_no_discord_id, 2)

    def test_holds_seat_flag_wins_over_status(self) -> None:
        signups = [
            _signup(1, SignupStatus.RSVP, discord_id="201", holds_seat=False),
            _signup(2, SignupStatus.WAITLISTED, discord_id="202", holds_seat=True),
        ]
        result = start_mention_recipients(signups, StartMentionScope.MAIN)
        self.assertEqual(result.discord_ids, ["202"])

    def test_each_member_is_mentioned_once(self) -> None:
        signups = [
            _signup(1, SignupStatus.RSVP, discord_id="301"),
            _signup(2, SignupStatus.RSVP, discord_id="301"),
        ]
        result = start_mention_recipients(signups, StartMentionScope.ALL_ACTIVE)
        self.assertEqual(result.discord_ids, ["301"])


class SendStartMentionTaskTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.event.state = "roll_call"
        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 15
        self.event.discord_start_mention_scope = StartMentionScope.ALL_ACTIVE
        self.event.scheduled_at = timezone.now() + timedelta(minutes=10)
        self.event.save()
        DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id="5550001",
            thread_id="5550002",
            message_id="5550003",
            has_posted=True,
        )

    def _add_signups(self, count: int, start: int = 0) -> list[str]:
        ids: list[str] = []
        for i in range(start, start + count):
            discord_id = str(100000000000000000 + i)
            user = CustomUser.objects.create_user(
                username=f"mention_user_{i}", password="x", discordId=discord_id
            )
            EventSignup.objects.create(
                event=self.event, user=user, status=SignupStatus.RSVP
            )
            ids.append(discord_id)
        return ids

    def _posts(self, mock_req: MagicMock) -> list[dict[str, Any]]:
        return [
            {"url": c.args[1], **c.kwargs["json"]}
            for c in mock_req.call_args_list
            if c.args[0] == "POST"
        ]

    @patch("discordbot.utils._rate_limited_request")
    def test_mentions_every_member_once_as_thread_replies(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = [_ok_response({"id": f"m{i}"}) for i in range(10)]
        ids = self._add_signups(250)
        no_discord = CustomUser.objects.create_user(username="no_discord", password="x")
        EventSignup.objects.create(
            event=self.event, user=no_discord, status=SignupStatus.RSVP
        )

        send_start_mention(self.event.pk)

        posts = self._posts(mock_req)
        self.assertEqual(len(posts), 4)
        mentioned: list[str] = []
        for post in posts:
            self.assertIn("/channels/5550002/messages", post["url"])
            self.assertEqual(post["message_reference"]["message_id"], "5550003")
            self.assertEqual(set(post["allowed_mentions"]), {"users"})
            self.assertLessEqual(len(post["content"]), 2000)
            self.assertLessEqual(len(post["allowed_mentions"]["users"]), 100)
            mentioned.extend(post["allowed_mentions"]["users"])
        self.assertEqual(sorted(mentioned), sorted(ids))

        log_row = DiscordMessageLog.objects.get(
            source="start_mention", source_id=self.event.pk
        )
        self.assertTrue(log_row.success)
        self.assertEqual(log_row.response_data["mentioned"], 250)
        self.assertEqual(log_row.response_data["skipped_no_discord_id"], 1)
        self.assertEqual(log_row.response_data["message_ids"], ["m0", "m1", "m2", "m3"])

    @patch("discordbot.utils._rate_limited_request")
    def test_fires_once_when_dispatched_twice(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "m"})
        self._add_signups(3)

        send_start_mention(self.event.pk)
        send_start_mention(self.event.pk)

        self.assertEqual(len(self._posts(mock_req)), 1)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="start_mention").count(), 1
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_lease_held_by_other_worker_sends_nothing(
        self, mock_req: MagicMock
    ) -> None:
        self._add_signups(3)
        with (
            patch("events.tasks.check_message_log_exists", return_value=False),
            patch("events.tasks.claim_discord_message_log", return_value=None),
        ):
            result = send_start_mention(self.event.pk)

        self.assertIn("lease held", result)
        self.assertEqual(self._posts(mock_req), [])

    @patch("discordbot.utils._rate_limited_request")
    def test_main_scope_skips_waitlist(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "m"})
        self.event.discord_start_mention_scope = StartMentionScope.MAIN
        self.event.save()
        seated = self._add_signups(2)
        waiter = CustomUser.objects.create_user(
            username="waiter", password="x", discordId="200000000000000001"
        )
        EventSignup.objects.create(
            event=self.event, user=waiter, status=SignupStatus.WAITLISTED
        )

        send_start_mention(self.event.pk)

        (post,) = self._posts(mock_req)
        self.assertEqual(sorted(post["allowed_mentions"]["users"]), sorted(seated))

    @patch("discordbot.utils._rate_limited_request")
    def test_disabled_option_sends_nothing_unless_fired_by_staff(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "m"})
        self.event.discord_start_mention = False
        self.event.save()
        self._add_signups(1)

        send_start_mention(self.event.pk)
        self.assertEqual(self._posts(mock_req), [])

        send_start_mention(self.event.pk, fired_by_user_id=self.admin.pk)
        self.assertEqual(len(self._posts(mock_req)), 1)

    @patch("discordbot.utils._rate_limited_request")
    def test_no_signup_post_sends_nothing(self, mock_req: MagicMock) -> None:
        DiscordEventMsgSignup.objects.filter(event=self.event).delete()
        self._add_signups(1)

        send_start_mention(self.event.pk)

        self.assertEqual(self._posts(mock_req), [])
        self.assertFalse(DiscordMessageLog.objects.filter(source="start_mention"))


class FireStartMentionEndpointTest(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.url = f"/api/events/{self.event.pk}/task-schedule/start_mention/fire/"

    @patch("events.views.current_app")
    def test_staff_can_fire_and_second_fire_is_409(self, mock_app: MagicMock) -> None:
        mock_send = mock_app.send_task
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once_with(
            "events.tasks.send_start_mention",
            args=[self.event.pk],
            kwargs={"fired_by_user_id": self.admin.pk},
        )

        DiscordMessageLog.objects.create(
            source="start_mention",
            source_id=self.event.pk,
            success=True,
            channel_id="5550002",
            embed_data={"type": "start_mention"},
        )
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(mock_send.call_count, 1)

    def test_non_staff_cannot_fire(self) -> None:
        self.client.force_authenticate(user=self.unrelated_user)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403)

    @patch("events.views.current_app")
    def test_org_member_cannot_fire(self, mock_app: MagicMock) -> None:
        self.client.force_authenticate(user=self.make_user())
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403)
        mock_app.send_task.assert_not_called()

    @patch("events.views.current_app")
    def test_league_staff_can_fire(self, mock_app: MagicMock) -> None:
        self.client.force_authenticate(user=self.league_staff)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        mock_app.send_task.assert_called_once_with(
            "events.tasks.send_start_mention",
            args=[self.event.pk],
            kwargs={"fired_by_user_id": self.league_staff.pk},
        )

    def test_schedule_lists_start_mention(self) -> None:
        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 30
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "5550001"
        self.event.save()

        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        task = next(t for t in resp.json() if t["task"] == "start_mention")
        self.assertEqual(task["status"], "pending")
        self.assertTrue(task["can_fire"])
        self.assertEqual(
            task["fires_at"],
            (self.event.scheduled_at - timedelta(minutes=30)).isoformat(),
        )
        self.assertEqual(task["description"], CONFIGURED_DESCRIPTION)

    def _schedule_entry(self) -> dict[str, Any]:
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return next(t for t in resp.json() if t["task"] == "start_mention")

    def _configure(
        self,
        *,
        post_signups: bool,
        signup_channel: str,
        announcement: bool,
        announcement_channel: str,
    ) -> None:
        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 30
        self.event.discord_post_signups = post_signups
        self.event.discord_post_signups_channel_id = signup_channel
        self.event.discord_announcement = announcement
        self.event.discord_announcement_channel_id = announcement_channel
        self.event.save()

    def _assert_misconfigured(self) -> None:
        task = self._schedule_entry()
        self.assertEqual(task["status"], "misconfigured")
        self.assertIs(task["can_fire"], False)
        self.assertEqual(task["description"], MISCONFIGURED_DESCRIPTION)

    def test_schedule_start_mention_misconfigured_when_signup_posts_off(
        self,
    ) -> None:
        self._configure(
            post_signups=False,
            signup_channel="",
            announcement=False,
            announcement_channel="",
        )
        self._assert_misconfigured()

    def test_schedule_start_mention_misconfigured_without_signup_channel(
        self,
    ) -> None:
        self._configure(
            post_signups=True,
            signup_channel="",
            announcement=False,
            announcement_channel="",
        )
        self._assert_misconfigured()

    def test_schedule_start_mention_misconfigured_when_signup_off_with_stored_channel(
        self,
    ) -> None:
        self._configure(
            post_signups=False,
            signup_channel="5550001",
            announcement=False,
            announcement_channel="",
        )
        self._assert_misconfigured()

    def test_schedule_start_mention_announcement_fallback_is_configured(
        self,
    ) -> None:
        self._configure(
            post_signups=False,
            signup_channel="",
            announcement=True,
            announcement_channel="5550009",
        )
        task = self._schedule_entry()
        self.assertNotEqual(task["status"], "misconfigured")
        self.assertIs(task["can_fire"], True)
        self.assertEqual(task["description"], CONFIGURED_DESCRIPTION)
