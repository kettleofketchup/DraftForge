"""sync_discord_events must not ask Discord to schedule an event that already started.

Discord rejects a past scheduled_start_time with 50035
GUILD_SCHEDULED_EVENT_SCHEDULE_PAST. The sync window deliberately reaches one
day back, so without a start-time check every such event was retried every
5 minutes until cleanup_stale_events cancelled it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from events.tasks import sync_discord_events


def _sync_state(scheduled_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        active_events=[
            {
                "pk": 2,
                "name": "Demo Signup Event",
                "state": "signups_open",
                "scheduled_at": scheduled_at.isoformat().replace("+00:00", "Z"),
                "discord_announcement": False,
                "discord_announcement_channel_id": None,
                "discord_post_signups": False,
                "discord_post_signups_channel_id": None,
                "discord_create_event": True,
                "organization__discord_server_id": "734185035623825559",
            }
        ],
        existing_logs=[],
        events_with_signup=[],
        events_with_scheduled=[],
        events_with_recent_attempt=[],
    )


@patch("events.tasks.create_discord_scheduled_event")
@patch("events.tasks.get_sync_discord_state")
class SyncScheduledEventStartWindowTest(SimpleTestCase):
    def test_skips_event_whose_start_has_passed(
        self, mock_state: MagicMock, mock_create: MagicMock
    ) -> None:
        mock_state.return_value = _sync_state(
            datetime.now(timezone.utc) - timedelta(hours=2)
        )

        sync_discord_events()

        mock_create.assert_not_called()

    def test_creates_event_that_starts_in_the_future(
        self, mock_state: MagicMock, mock_create: MagicMock
    ) -> None:
        mock_state.return_value = _sync_state(
            datetime.now(timezone.utc) + timedelta(hours=2)
        )

        sync_discord_events()

        mock_create.assert_called_once_with(2)
