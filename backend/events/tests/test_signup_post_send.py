import json
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.utils import timezone

from app import internal_client
from app.internal_client import InternalAPIUnavailable
from discordbot.delivery_types import ClaimResult
from discordbot.models import (
    DiscordEvent,
    DiscordEventLog,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    SignupPostDeliveryState,
)
from discordbot.signup_delivery import reset_signup_delivery
from discordbot.utils import DISCORD_API_BASE
from events.signup_post_send import SignupRunOutcome, run_signup_post
from events.tasks import _resolve_signup_edit_channel, send_event_announcement
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase

PRIMARY = "100000000000000001"
FALLBACK = "100000000000000002"
MESSAGE = "100000000000000003"
THREAD = "100000000000000004"
GUILD = "200000000000000001"


def response(status: int, body: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


class SignupPostSendTest(DiscordTestMixin, EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.post_event = self.make_event(
            name="Synthetic Event",
            discord_post_signups=True,
            discord_post_signups_channel_id=PRIMARY,
            discord_announcement=False,
            discord_announcement_channel_id=FALLBACK,
        )
        self.channel_type: int = 0
        self.lookup_failure: object = None
        self.primary_response: requests.Response | Exception | None = None
        self.fallback_response: requests.Response | None = None
        self.http: MagicMock = self.enterContext(
            patch("discordbot.utils.requests.request", side_effect=self.request)
        )
        self.enterContext(patch("discordbot.utils._acquire_rate_limit_token"))
        self.sleep: MagicMock = self.enterContext(
            patch("discordbot.utils._time.sleep", side_effect=AssertionError("sleep"))
        )

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        channel = url.removeprefix(f"{DISCORD_API_BASE}/channels/").split("/")[0]
        self.assertIn(channel, (PRIMARY, FALLBACK))
        if method == "GET":
            if channel == PRIMARY and self.lookup_failure is not None:
                if isinstance(self.lookup_failure, Exception):
                    raise self.lookup_failure
                if isinstance(self.lookup_failure, requests.Response):
                    return self.lookup_failure
            return response(
                200,
                {
                    "id": channel,
                    "guild_id": GUILD,
                    "type": self.channel_type if channel == PRIMARY else 0,
                },
            )
        self.assertEqual(method, "POST")
        selected = (
            self.primary_response if channel == PRIMARY else self.fallback_response
        )
        if isinstance(selected, Exception):
            raise selected
        if selected is not None:
            return selected
        return response(
            201,
            {"id": THREAD, "message": {"id": MESSAGE}}
            if url.endswith("/threads")
            else {"id": MESSAGE},
        )

    def enable_fallback(self, channel: str = FALLBACK) -> None:
        self.post_event.discord_announcement = True
        self.post_event.discord_announcement_channel_id = channel
        self.post_event.save()

    def posts(self) -> list[Any]:
        return [call for call in self.http.call_args_list if call.args[0] == "POST"]

    def state(self) -> SignupPostDeliveryState:
        return SignupPostDeliveryState.objects.get(event=self.post_event)

    def run_post(self, **kwargs: Any) -> Any:
        return run_signup_post(self.post_event.pk, **kwargs)

    def test_text_channel_signup_posts_to_messages(self) -> None:
        result = self.run_post(fired_by_user_id=self.admin.pk)
        self.assertEqual(result.outcome, SignupRunOutcome.DELIVERED)
        self.assertTrue(result.persisted)
        self.assertTrue(result.newly_delivered())
        self.assertEqual(
            [p.args[1] for p in self.posts()],
            [f"{DISCORD_API_BASE}/channels/{PRIMARY}/messages"],
        )
        row = DiscordEventMsgSignup.objects.get(event=self.post_event)
        self.assertEqual(
            (row.channel_id, row.message_id, row.thread_id, row.channel_type),
            (PRIMARY, MESSAGE, None, "text"),
        )
        self.assertEqual(
            DiscordEvent.objects.get(event=self.post_event).signup_message_id, row.pk
        )
        self.assertEqual(
            DiscordMessageLog.objects.get(source_id=self.post_event.pk).fired_by_id,
            self.admin.pk,
        )

    def test_forum_signup_posts_thread(self) -> None:
        self.channel_type = 15
        result = self.run_post()
        self.assertTrue(result.persisted)
        self.assertEqual(
            self.posts()[0].args[1], f"{DISCORD_API_BASE}/channels/{PRIMARY}/threads"
        )
        self.assertEqual(self.posts()[0].kwargs["json"]["name"], "Synthetic Event")
        row = DiscordEventMsgSignup.objects.get(event=self.post_event)
        self.assertEqual((row.message_id, row.thread_id), (MESSAGE, THREAD))

    def test_text_post_clears_stale_thread_id(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.post_event,
            channel_id=PRIMARY,
            thread_id=THREAD,
            channel_type="forum",
            has_posted=False,
        )
        self.run_post()
        row = DiscordEventMsgSignup.objects.get(event=self.post_event)
        self.assertIsNone(row.thread_id)
        state = internal_client.get_discord_event_state(self.post_event.pk)
        self.assertEqual(_resolve_signup_edit_channel(state, {}), PRIMARY)

    def test_primary_failed_fallback_delivers(self) -> None:
        self.enable_fallback()
        self.primary_response = response(403, {"code": 50013})
        result = self.run_post(fired_by_user_id=self.admin.pk)
        self.assertEqual(
            (result.outcome, result.destination, result.persisted),
            (SignupRunOutcome.DELIVERED, "announcement", True),
        )
        self.assertEqual(len(self.posts()), 2)
        self.assertEqual(self.state().attempts, 1)
        self.assertEqual(self.state().receipt["parent_channel_id"], FALLBACK)
        self.assertEqual(
            set(DiscordMessageLog.objects.values_list("fired_by_id", flat=True)),
            {self.admin.pk},
        )

    def test_primary_lookup_failure_distinct_enabled_fallback_delivers(self) -> None:
        self.enable_fallback()
        for failure in (
            response(403, {"code": 50013}),
            requests.Timeout(),
            "unsupported",
        ):
            with self.subTest(failure=type(failure).__name__):
                reset_signup_delivery(self.post_event.pk)
                self.lookup_failure = failure
                self.channel_type = 2 if failure == "unsupported" else 0
                self.http.reset_mock()
                result = self.run_post()
                self.assertEqual(
                    (result.outcome, result.destination, result.persisted),
                    (SignupRunOutcome.DELIVERED, "announcement", True),
                )
                self.assertEqual(self.state().attempts, 1)
                self.assertEqual(len(self.posts()), 1)
                self.assertEqual(
                    self.posts()[0].args[1],
                    f"{DISCORD_API_BASE}/channels/{FALLBACK}/messages",
                )
                self.assertFalse(
                    DiscordMessageLog.objects.filter(channel_id=PRIMARY).exists()
                )

    def test_same_channel_fallback_suppressed(self) -> None:
        self.enable_fallback(PRIMARY)
        self.primary_response = response(403, {})
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.FAILED)
        self.assertEqual(len(self.posts()), 1)

    def test_primary_held_no_fallback(self) -> None:
        self.enable_fallback()
        with patch.object(
            internal_client,
            "claim_discord_message_log_result",
            return_value=ClaimResult("held"),
        ):
            self.assertEqual(self.run_post().outcome, SignupRunOutcome.IN_FLIGHT)
        self.assertEqual(self.posts(), [])

    def test_claim_unavailable_no_fallback(self) -> None:
        self.enable_fallback()
        with patch.object(
            internal_client,
            "claim_discord_message_log_result",
            return_value=ClaimResult("unavailable"),
        ):
            self.assertEqual(self.run_post().outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertEqual(self.posts(), [])

    def test_primary_timeout_uncertain_no_fallback(self) -> None:
        self.enable_fallback()
        self.primary_response = requests.Timeout()
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.UNCERTAIN)
        self.assertEqual(self.state().state, "uncertain")
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.IN_FLIGHT)
        self.assertEqual(len(self.posts()), 1)

    def test_primary_rejection_unconfirmed_finalization_no_fallback(self) -> None:
        self.enable_fallback()
        self.primary_response = response(403, {"code": 50013})
        for finalized in (None, response(410, {})):
            with self.subTest(finalized=finalized):
                event = self.make_event(
                    name="Synthetic Event",
                    discord_post_signups=True,
                    discord_post_signups_channel_id=PRIMARY,
                    discord_announcement=True,
                    discord_announcement_channel_id=FALLBACK,
                )
                self.http.reset_mock()
                with patch.object(
                    internal_client,
                    "finalize_discord_message_log",
                    return_value=finalized,
                ):
                    result = run_signup_post(event.pk)
                self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
                self.assertEqual(len(self.posts()), 1)
                self.assertEqual(
                    SignupPostDeliveryState.objects.get(event=event).state, "sending"
                )
                self.assertTrue(
                    DiscordMessageLog.objects.filter(
                        source_id=event.pk, success__isnull=True
                    ).exists()
                )

    def test_429_cannot_resume_old_generation_post(self) -> None:
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                event = self.make_event(
                    name="Synthetic Event",
                    discord_post_signups=True,
                    discord_post_signups_channel_id=PRIMARY,
                    discord_announcement=fallback,
                    discord_announcement_channel_id=FALLBACK,
                )
                self.primary_response = response(
                    429, {"retry_after": 600, "code": 20028}
                )
                self.fallback_response = response(429, {"retry_after": 600})
                self.http.reset_mock()
                now = timezone.now()
                with patch("discordbot.signup_delivery.timezone.now", return_value=now):
                    result = run_signup_post(event.pk, generation=0)
                state = SignupPostDeliveryState.objects.get(event=event)
                self.assertEqual(
                    (result.outcome, state.state, state.attempts),
                    (SignupRunOutcome.FAILED, "ready", 1),
                )
                self.assertEqual(state.next_attempt_at, now + timedelta(minutes=1))
                self.assertEqual(len(self.posts()), 2 if fallback else 1)
                with patch(
                    "discordbot.signup_delivery.timezone.now",
                    return_value=now + timedelta(minutes=6),
                ):
                    reset_signup_delivery(event.pk)
                    stale = run_signup_post(event.pk, generation=0)
                self.assertEqual(stale.outcome, SignupRunOutcome.STALE_GENERATION)
                self.assertEqual(len(self.posts()), 2 if fallback else 1)
        self.sleep.assert_not_called()

    def test_both_destinations_fail_records_one_attempt(self) -> None:
        self.enable_fallback()
        self.primary_response = response(403, {"code": 50013})
        self.fallback_response = response(500, {})
        now = timezone.now()
        with patch("discordbot.signup_delivery.timezone.now", return_value=now):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.FAILED)
        self.assertEqual(self.state().attempts, 1)
        self.assertEqual(self.state().next_attempt_at, now + timedelta(minutes=1))
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.DEFERRED)
        self.assertEqual(len(self.posts()), 2)

    def test_notice_failure_keeps_signup_delivered(self) -> None:
        self.enable_fallback()
        self.fallback_response = response(403, {})
        result = self.run_post()
        self.assertEqual(
            (result.outcome, result.notice), (SignupRunOutcome.DELIVERED, "failed")
        )
        self.assertTrue(result.persisted)
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.ALREADY_DELIVERED)
        self.assertEqual(len(self.posts()), 2)

    def test_finalize_410_still_completes_state(self) -> None:
        with patch.object(
            internal_client,
            "finalize_discord_message_log",
            return_value=response(410, {}),
        ):
            result = self.run_post()
        self.assertTrue(result.persisted)
        self.assertEqual(self.state().state, "delivered")
        self.assertTrue(
            DiscordMessageLog.objects.get(source_id=self.post_event.pk).success
        )

    def test_completion_retry_persists_without_another_post(self) -> None:
        complete = internal_client.complete_signup_delivery
        calls = 0

        def record(**kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            recorded = complete(**kwargs)
            return None if calls == 1 else recorded

        with patch.object(
            internal_client, "complete_signup_delivery", side_effect=record
        ):
            result = self.run_post()
        self.assertTrue(result.persisted)
        self.assertEqual(calls, 2)
        self.assertEqual(len(self.posts()), 1)

    def test_persistence_failure_after_delivery_not_resent(self) -> None:
        with patch.object(
            internal_client, "complete_signup_delivery", return_value=None
        ) as complete:
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.DELIVERED)
        self.assertFalse(result.persisted)
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(complete.call_args_list[0], complete.call_args_list[1])
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.IN_FLIGHT)
        self.assertEqual(len(self.posts()), 1)

    def test_malformed_success_blocks_further_posts(self) -> None:
        self.channel_type = 15
        self.primary_response = response(201, {"id": THREAD})
        self.enable_fallback()
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.UNCERTAIN)
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.IN_FLIGHT)
        DiscordMessageLog.objects.filter(source_id=self.post_event.pk).delete()
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.UNCERTAIN)
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.state().state, "uncertain")

    def test_task_with_old_generation_does_not_send(self) -> None:
        reset_signup_delivery(self.post_event.pk)
        summary = send_event_announcement(self.post_event.pk, generation=0)
        self.assertIn("stale_generation", summary)
        self.assertEqual(self.posts(), [])

    def test_build_failure_does_not_consume_attempt(self) -> None:
        with patch(
            "events.signup_post_send.build_announcement_v2",
            side_effect=InternalAPIUnavailable("signups"),
        ):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.post_event).exists()
        )
        self.http.assert_not_called()

    def test_build_error_does_not_consume_attempt(self) -> None:
        with patch(
            "events.signup_post_send.build_announcement_v2",
            side_effect=ValueError("private content"),
        ):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.post_event).exists()
        )
        self.assertEqual(self.posts(), [])

    def test_missing_built_payload_does_not_consume_attempt(self) -> None:
        with patch("events.signup_post_send.build_announcement_v2", return_value={}):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.post_event).exists()
        )
        self.assertEqual(self.posts(), [])

    def test_discord_event_unavailable_does_not_consume_attempt(self) -> None:
        with patch.object(
            internal_client, "get_or_create_discord_event", return_value=None
        ):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.post_event).exists()
        )
        self.assertEqual(self.posts(), [])

    def test_begin_unavailable_does_not_post(self) -> None:
        with patch.object(internal_client, "begin_signup_delivery", return_value=None):
            self.assertEqual(self.run_post().outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertEqual(self.posts(), [])

    def test_sending_authorization_failure_prevents_post_and_fallback(self) -> None:
        self.enable_fallback()
        with patch.object(
            internal_client, "mark_signup_delivery_sending", return_value=False
        ):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.state().state, "reserved")

    def test_finalized_primary_and_failed_fallback_lookup_complete_attempt(
        self,
    ) -> None:
        self.enable_fallback()
        self.primary_response = response(403, {"code": 50013})
        request = self.request

        def failed_lookup(method: str, url: str, **kwargs: Any) -> requests.Response:
            if method == "GET" and url.endswith(f"/{FALLBACK}"):
                return response(403, {"code": 50001})
            return request(method, url, **kwargs)

        self.http.side_effect = failed_lookup
        result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.FAILED)
        self.assertTrue(result.persisted)
        self.assertEqual(
            (self.state().state, self.state().attempts, self.state().last_failure_code),
            ("ready", 1, 50001),
        )
        self.assertEqual(len(self.posts()), 1)

    def test_failed_lookup_without_fallback_completes_attempt(self) -> None:
        self.lookup_failure = response(403, {"code": 50001})
        result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.FAILED)
        self.assertTrue(result.persisted)
        self.assertEqual((self.state().state, self.state().attempts), ("ready", 1))
        self.assertEqual(self.posts(), [])
        self.assertFalse(DiscordMessageLog.objects.exists())

    def test_notice_build_failure_keeps_signup_delivered(self) -> None:
        self.enable_fallback()
        with patch(
            "events.signup_post_send.build_announcement_notice",
            side_effect=ValueError("private content"),
        ):
            result = self.run_post()
        self.assertEqual(
            (result.outcome, result.notice, result.persisted),
            (SignupRunOutcome.DELIVERED, "failed", True),
        )
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.ALREADY_DELIVERED)
        self.assertEqual(len(self.posts()), 1)

    def test_notice_and_signup_leases_record_actor(self) -> None:
        self.enable_fallback()
        result = self.run_post(fired_by_user_id=self.admin.pk, manual=True)
        self.assertEqual(
            (result.outcome, result.notice), (SignupRunOutcome.DELIVERED, "delivered")
        )
        self.assertEqual(
            list(
                DiscordMessageLog.objects.order_by("pk").values_list(
                    "source", "fired_by_id"
                )
            ),
            [("event_announcement", self.admin.pk), ("event_notice", self.admin.pk)],
        )
        self.assertEqual(self.state().attempts, 1)

    def test_success_records_signup_action_once(self) -> None:
        self.run_post()
        self.run_post()
        self.assertEqual(
            list(
                DiscordEventLog.objects.filter(action="send_signup_post").values_list(
                    "message_id", "success"
                )
            ),
            [(MESSAGE, True)],
        )

    def test_action_log_failure_does_not_change_delivery(self) -> None:
        with patch.object(
            internal_client,
            "create_event_log",
            side_effect=ValueError("private content"),
        ):
            result = self.run_post()
        self.assertEqual(
            (result.outcome, result.persisted), (SignupRunOutcome.DELIVERED, True)
        )
        self.assertEqual(self.run_post().outcome, SignupRunOutcome.ALREADY_DELIVERED)
        self.assertEqual(len(self.posts()), 1)

    def test_discord_event_malformed_data_does_not_consume_attempt(self) -> None:
        for payload in ({}, [], {"id": True}, {"id": "invalid"}):
            with self.subTest(payload=payload):
                with patch.object(
                    internal_client,
                    "get_or_create_discord_event",
                    return_value=response(200, payload),
                ):
                    result = self.run_post()
                self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
                self.assertFalse(
                    SignupPostDeliveryState.objects.filter(
                        event=self.post_event
                    ).exists()
                )
                self.assertEqual(self.posts(), [])

    def test_invalid_event_data_does_not_consume_attempt(self) -> None:
        with patch.object(
            internal_client,
            "get_event_for_task",
            side_effect=ValueError("private content"),
        ):
            result = self.run_post()
        self.assertEqual(result.outcome, SignupRunOutcome.UNAVAILABLE)
        self.assertFalse(
            SignupPostDeliveryState.objects.filter(event=self.post_event).exists()
        )
        self.assertEqual(self.posts(), [])

    def test_task_returns_string_summary(self) -> None:
        result = send_event_announcement(self.post_event.pk)
        self.assertIsInstance(result, str)
        self.assertIn("delivered", result)
        json.dumps(result)
