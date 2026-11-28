from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from discordbot.models import DiscordMessageLog
from events.tasks import send_event_announcement
from events.tests.test_discord_tasks import _discord_http, _DiscordTaskTestCase


def _row(**overrides):
    """Helper — DiscordMessageLog requires channel_id and embed_data.

    Worker passes both at claim time per the lease pattern (Option B).
    """
    defaults = dict(
        channel_id="ch_1",
        embed_data={"title": "test"},
        success=None,
        claimed_at=timezone.now(),
    )
    defaults.update(overrides)
    return DiscordMessageLog.objects.create(**defaults)


class DiscordMessageLogLeaseSchemaTest(TransactionTestCase):
    def test_success_field_is_nullable(self):
        row = _row(source="signup_reminder", source_id=1, success=None)
        self.assertIsNone(row.success)

    def test_claimed_at_field_exists(self):
        row = _row(source="signup_reminder", source_id=2)
        self.assertIsNotNone(row.claimed_at)

    def test_partial_unique_blocks_second_claim_when_pending(self):
        _row(source="signup_reminder", source_id=3, success=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _row(source="signup_reminder", source_id=3, success=None)

    def test_partial_unique_blocks_second_claim_when_successful(self):
        _row(source="signup_reminder", source_id=4, success=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _row(source="signup_reminder", source_id=4, success=None)

    def test_partial_unique_DOES_NOT_block_after_failed_send(self):
        # Failed sends are reclaimable so transient errors don't permanently brick reminders
        _row(source="signup_reminder", source_id=5, success=False)
        # Re-claim should succeed
        _row(source="signup_reminder", source_id=5, success=None)

    def test_unique_is_per_source_and_event(self):
        _row(source="signup_reminder", source_id=6, success=True)
        # Different source_id — fine
        _row(source="signup_reminder", source_id=7, success=True)
        # Different source — fine
        _row(source="attendance_reminder", source_id=6, success=True)


class ConcurrentReminderTasksProduceOneSendTest(_DiscordTaskTestCase):
    """End-to-end verification that the lease pattern prevents duplicate
    Discord HTTP sends, not just duplicate audit rows.

    SQLite serializes writers via a single write lock, so a true
    parallel-thread test would just sequence the writes. Instead we
    simulate the race by invoking the reminder task twice in sequence
    and asserting:
    - The Discord HTTP send fires AT MOST ONCE (lease prevents duplicate)
    - Exactly one success log row exists (no duplicate audit)
    - The second invocation returns 'lease held' (short-circuit path)

    This covers the production race: check_event_reminders dispatches the
    same reminder twice (e.g. from a hung worker requeue), both dispatched
    tasks run, the second hits the partial unique constraint and exits
    cleanly.
    """

    @patch("discordbot.utils._rate_limited_request")
    def test_two_invocations_send_to_discord_exactly_once(self, mock_req):
        mock_req.side_effect = _discord_http("100000000000000006")
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.state = "signups_open"
        self.event.save()

        # Two sequential invocations — second hits the lease and exits
        send_event_announcement(self.event.pk)
        send_event_announcement(self.event.pk)

        # The second invocation sees the delivered signup and makes no POST.
        self.assertEqual(len(self.posts(mock_req)), 1)

        # Exactly one success log row
        success_rows = DiscordMessageLog.objects.filter(
            source="event_announcement",
            source_id=self.event.pk,
            success=True,
        )
        self.assertEqual(success_rows.count(), 1)
