from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from discordbot.models import DiscordMessageLog


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
