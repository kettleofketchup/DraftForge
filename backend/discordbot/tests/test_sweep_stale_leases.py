"""sweep_stale_discord_leases — reaps NULL pending and False aged-out rows."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from discordbot.models import DiscordMessageLog
from discordbot.tasks import sweep_stale_discord_leases


def _row(**overrides):
    defaults = dict(
        channel_id="ch_1",
        embed_data={"title": "test"},
    )
    defaults.update(overrides)
    return DiscordMessageLog.objects.create(**defaults)


class SweepStaleLeasesTest(TestCase):
    def test_deletes_pending_lease_older_than_5_min(self):
        _row(
            source="event_announcement",
            source_id=1,
            success=None,
            claimed_at=timezone.now() - timedelta(minutes=10),
        )
        deleted = sweep_stale_discord_leases()
        self.assertEqual(deleted, 1)
        self.assertFalse(DiscordMessageLog.objects.filter(source_id=1).exists())

    def test_does_not_delete_recent_pending_lease(self):
        _row(
            source="event_announcement",
            source_id=2,
            success=None,
            claimed_at=timezone.now() - timedelta(minutes=2),
        )
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=2).exists())

    def test_does_not_delete_recent_failed_row(self):
        # Recent failures (within 1-hour budget) stay so admins can investigate
        _row(
            source="event_announcement",
            source_id=3,
            success=False,
            claimed_at=timezone.now() - timedelta(minutes=30),
        )
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=3).exists())

    def test_deletes_aged_out_failed_row(self):
        # Failures older than 1 hour are reaped so the next poll can retry
        _row(
            source="event_announcement",
            source_id=4,
            success=False,
            claimed_at=timezone.now() - timedelta(hours=2),
        )
        deleted = sweep_stale_discord_leases()
        self.assertEqual(deleted, 1)
        self.assertFalse(DiscordMessageLog.objects.filter(source_id=4).exists())

    def test_does_not_delete_successful_rows(self):
        _row(
            source="event_announcement",
            source_id=5,
            success=True,
            claimed_at=timezone.now() - timedelta(days=30),
        )
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=5).exists())
