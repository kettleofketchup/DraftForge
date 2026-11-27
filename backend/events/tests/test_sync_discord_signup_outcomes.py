from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from django.utils import timezone
from structlog.testing import capture_logs

from discordbot.models import SignupDeliveryStatus, SignupPostDeliveryState
from events.scheduling.fire import fire_due_reminders
from events.scheduling.registry import REMINDERS
from events.signup_post_send import SignupPostResult, SignupRunOutcome
from events.tasks import send_event_announcement, sync_discord_events
from events.tests.test_discord_tasks import _DiscordTaskTestCase
from events.tests.test_signup_post_send import GUILD, PRIMARY, response


def sync_state(event_id: int = 17) -> SimpleNamespace:
    return SimpleNamespace(
        active_events=[
            {
                "pk": event_id,
                "state": "signups_open",
                "discord_post_signups": True,
                "discord_post_signups_channel_id": PRIMARY,
                "discord_announcement": False,
                "discord_announcement_channel_id": None,
                "discord_create_event": False,
            }
        ],
        existing_logs=[],
        events_with_signup=[],
        events_with_scheduled=[],
        events_with_recent_attempt=[],
        events_with_signup_blocked=[],
    )


class SyncSignupOutcomesTest(SimpleTestCase):
    def run_sync(
        self, outcome: SignupRunOutcome, *, persisted: bool = False
    ) -> tuple[str, list[dict[str, Any]]]:
        result = SignupPostResult(outcome, 17, persisted=persisted)
        with (
            patch("events.tasks.get_sync_discord_state", return_value=sync_state()),
            patch("events.tasks.run_signup_post", return_value=result),
            capture_logs() as logs,
        ):
            summary = sync_discord_events()
        return summary, logs

    def test_failed_signup_not_counted_or_logged_created(self) -> None:
        summary, logs = self.run_sync(SignupRunOutcome.FAILED)
        self.assertIn("0 signup posts", summary)
        self.assertNotIn("sync_signup_post_created", [log["event"] for log in logs])
        not_created = [
            log for log in logs if log["event"] == "sync_signup_post_not_created"
        ]
        self.assertEqual([log["outcome"] for log in not_created], ["failed"])

    def test_delivered_counted_once(self) -> None:
        summary, logs = self.run_sync(SignupRunOutcome.DELIVERED, persisted=True)
        self.assertIn("1 signup posts", summary)
        self.assertEqual(
            [log["event"] for log in logs].count("sync_signup_post_created"), 1
        )

    def test_deferred_and_exhausted_not_counted(self) -> None:
        for outcome in SignupRunOutcome:
            if outcome == SignupRunOutcome.DELIVERED:
                continue
            with self.subTest(outcome=outcome):
                summary, logs = self.run_sync(outcome)
                self.assertIn("0 signup posts", summary)
                self.assertNotIn(
                    "sync_signup_post_created", [log["event"] for log in logs]
                )
                self.assertEqual(
                    [
                        log["outcome"]
                        for log in logs
                        if log["event"] == "sync_signup_post_not_created"
                    ],
                    [outcome.value],
                )

    def test_blocked_event_skipped_without_call(self) -> None:
        state = sync_state()
        state.events_with_signup_blocked = [17]
        with (
            patch("events.tasks.get_sync_discord_state", return_value=state),
            patch("events.tasks.run_signup_post") as run,
            patch("events.tasks.send_event_announcement") as legacy,
        ):
            summary = sync_discord_events()
        self.assertIn("0 signup posts", summary)
        run.assert_not_called()
        legacy.assert_not_called()

    def test_unrecorded_delivery_logs_distinct_event(self) -> None:
        summary, logs = self.run_sync(SignupRunOutcome.DELIVERED)
        self.assertIn("1 signup posts", summary)
        events = [log["event"] for log in logs]
        self.assertEqual(events.count("sync_signup_post_delivered_unrecorded"), 1)
        self.assertNotIn("sync_signup_post_created", events)


class SharedSignupBudgetTest(_DiscordTaskTestCase):
    def test_five_attempt_cap_across_poll_and_reminder(self) -> None:
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = PRIMARY
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = PRIMARY
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.save()
        announcement = next(r for r in REMINDERS if r.key == "announcement")
        clock = timezone.now()

        def discord_request(method: str, url: str, **kwargs: Any) -> requests.Response:
            if method == "GET":
                return response(200, {"id": PRIMARY, "guild_id": GUILD, "type": 0})
            self.assertEqual(method, "POST")
            self.assertTrue(url.endswith(f"/channels/{PRIMARY}/messages"))
            return response(403, {"code": 50013})

        with (
            patch("django.utils.timezone.now", side_effect=lambda: clock),
            patch(
                "events.tasks.get_sync_discord_state",
                return_value=sync_state(self.event.pk),
            ),
            patch("events.scheduling.fire.REMINDERS", [announcement]),
            patch(
                "events.tasks.send_event_announcement.delay",
                side_effect=send_event_announcement,
            ) as dispatch,
            patch(
                "discordbot.utils.requests.request", side_effect=discord_request
            ) as http,
            patch("discordbot.utils._acquire_rate_limit_token"),
        ):
            for attempt, wait in enumerate((1, 2, 4, 8, 60), start=1):
                if attempt % 2:
                    sync_discord_events()
                else:
                    fire_due_reminders()
                state = SignupPostDeliveryState.objects.get(event=self.event)
                self.assertEqual(state.attempts, attempt)
                # Both polling paths run during the cooldown, with stale sync state.
                sync_discord_events()
                fire_due_reminders()
                self.assertEqual(
                    sum(call.args[0] == "POST" for call in http.call_args_list), attempt
                )
                clock += timedelta(minutes=wait, seconds=1)
            sync_discord_events()
            fire_due_reminders()
        state.refresh_from_db()
        self.assertEqual(state.state, SignupDeliveryStatus.EXHAUSTED)
        self.assertEqual(state.attempts, 5)
        self.assertEqual(dispatch.call_count, 2)
        self.assertEqual(sum(call.args[0] == "POST" for call in http.call_args_list), 5)
