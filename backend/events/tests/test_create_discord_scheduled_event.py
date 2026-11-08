"""Tests for events.tasks.create_discord_scheduled_event.

Pinning the contract that surfaced after the prod 0.9.49 incident:
- On Discord API non-success (e.g., 403 Missing Permissions), the task MUST
  raise so the caller (`sync_discord_events`) can record the failure and
  emit an accurate log line. The previous behavior silently returned a
  "Created Discord event for event X" success string while the underlying
  API call returned 403 — `sync_discord_events` then logged
  "Sync: created Discord scheduled event for event X" 20+ times despite
  every attempt failing.
- DiscordEventLog.error_message MUST be populated with the Discord error
  string on non-success responses so operators don't have to inspect
  response_data JSON to find out what went wrong.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase

from events.tasks import create_discord_scheduled_event


class CreateDiscordScheduledEventTest(TestCase):
    """The task must NOT silently swallow Discord API non-success responses."""

    def _mock_event(self, start_offset: timedelta = timedelta(days=1)) -> MagicMock:
        event = MagicMock()
        event.pk = 12
        event.discord_create_event = True
        event.organization.discord_server_id = "734185035623825559"
        event.discord_event_title = "Sunday Turbo Tournament"
        event.description = "Test"
        event.discord_event_description = ""
        event.name = "Sunday Turbo Tournament"
        event.scheduled_at = datetime.now(timezone.utc) + start_offset
        return event

    @patch("events.tasks.req.post")
    @patch("events.tasks.create_event_log")
    @patch("events.tasks.create_message_log")
    @patch("events.tasks.update_discord_event")
    @patch("events.tasks.get_or_create_discord_event")
    @patch("events.tasks.get_event_for_task")
    def test_raises_on_discord_403_missing_permissions(
        self,
        mock_get_event,
        mock_get_de,
        mock_update,
        mock_message_log,
        mock_event_log,
        mock_post,
    ):
        """The exact prod scenario: bot lacks MANAGE_EVENTS in the guild.
        Discord returns 403 with code 50013. The task MUST raise so the
        caller knows to emit a 'failed' log, not 'created'."""
        mock_get_event.return_value = self._mock_event()
        mock_get_de.return_value = MagicMock(
            ok=True, json=lambda: {"id": 17}
        )
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {
            "message": "Missing Permissions",
            "code": 50013,
        }
        mock_post.return_value = resp

        with self.assertRaises(Exception) as ctx:
            create_discord_scheduled_event(12)

        # The raised exception must surface the Discord error text so the
        # caller's logger.exception() emits something operators can read.
        self.assertIn("Missing Permissions", str(ctx.exception))
        # scheduled_event_id must NOT be persisted on failure.
        mock_update.assert_not_called()

    @patch("events.tasks.req.post")
    @patch("events.tasks.create_event_log")
    @patch("events.tasks.create_message_log")
    @patch("events.tasks.update_discord_event")
    @patch("events.tasks.get_or_create_discord_event")
    @patch("events.tasks.get_event_for_task")
    def test_writes_error_message_to_event_log_on_failure(
        self,
        mock_get_event,
        mock_get_de,
        mock_update,
        mock_message_log,
        mock_event_log,
        mock_post,
    ):
        """The DiscordEventLog row for the failed attempt must carry the
        Discord error message in `error_message`, not just response_data."""
        mock_get_event.return_value = self._mock_event()
        mock_get_de.return_value = MagicMock(
            ok=True, json=lambda: {"id": 17}
        )
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {
            "message": "Missing Permissions",
            "code": 50013,
        }
        mock_post.return_value = resp

        with self.assertRaises(Exception):
            create_discord_scheduled_event(12)

        # Audit log must include the human-readable error.
        mock_event_log.assert_called_once()
        kwargs = mock_event_log.call_args.kwargs
        self.assertFalse(kwargs["success"])
        self.assertIn("Missing Permissions", kwargs.get("error_message", ""))

    @patch("events.tasks.req.post")
    @patch("events.tasks.create_event_log")
    @patch("events.tasks.create_message_log")
    @patch("events.tasks.update_discord_event")
    @patch("events.tasks.get_or_create_discord_event")
    @patch("events.tasks.get_event_for_task")
    def test_error_message_includes_nested_form_errors(
        self,
        mock_get_event,
        mock_get_de,
        mock_update,
        mock_message_log,
        mock_event_log,
        mock_post,
    ):
        """50035 Invalid Form Body hides the real reason in `errors`; the
        audit log must carry it so the activity log is self-explanatory."""
        mock_get_event.return_value = self._mock_event()
        mock_get_de.return_value = MagicMock(
            ok=True, json=lambda: {"id": 17}
        )
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "message": "Invalid Form Body",
            "code": 50035,
            "errors": {
                "name": {
                    "_errors": [
                        {
                            "code": "BASE_TYPE_MAX_LENGTH",
                            "message": "Must be 100 or fewer in length.",
                        }
                    ]
                }
            },
        }
        mock_post.return_value = resp

        with self.assertRaises(Exception):
            create_discord_scheduled_event(12)

        error_message = mock_event_log.call_args.kwargs["error_message"]
        self.assertIn("Invalid Form Body (code 50035, HTTP 400)", error_message)
        self.assertIn("name: Must be 100 or fewer in length.", error_message)

    @patch("events.tasks.req.post")
    @patch("events.tasks.create_event_log")
    @patch("events.tasks.create_message_log")
    @patch("events.tasks.update_discord_event")
    @patch("events.tasks.get_or_create_discord_event")
    @patch("events.tasks.get_event_for_task")
    def test_skips_without_calling_discord_when_start_has_passed(
        self,
        mock_get_event,
        mock_get_de,
        mock_update,
        mock_message_log,
        mock_event_log,
        mock_post,
    ):
        """Discord rejects a past start with GUILD_SCHEDULED_EVENT_SCHEDULE_PAST;
        the task must not make the doomed call or write failure rows."""
        mock_get_event.return_value = self._mock_event(timedelta(hours=-2))

        result = create_discord_scheduled_event(12)

        self.assertTrue(result.startswith("Skipped"))
        mock_post.assert_not_called()
        mock_get_de.assert_not_called()
        mock_event_log.assert_not_called()

    @patch("events.tasks.req.post")
    @patch("events.tasks.create_event_log")
    @patch("events.tasks.create_message_log")
    @patch("events.tasks.update_discord_event")
    @patch("events.tasks.get_or_create_discord_event")
    @patch("events.tasks.get_event_for_task")
    def test_success_path_persists_scheduled_event_id(
        self,
        mock_get_event,
        mock_get_de,
        mock_update,
        mock_message_log,
        mock_event_log,
        mock_post,
    ):
        """On 201 Created, the task should persist the new scheduled_event_id
        and NOT raise — this is the happy path."""
        mock_get_event.return_value = self._mock_event()
        mock_get_de.return_value = MagicMock(
            ok=True, json=lambda: {"id": 17}
        )
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"id": "1505242926014402792"}
        mock_post.return_value = resp

        result = create_discord_scheduled_event(12)
        self.assertIn("Created", result)
        mock_update.assert_called_once_with(
            17, scheduled_event_id="1505242926014402792"
        )
