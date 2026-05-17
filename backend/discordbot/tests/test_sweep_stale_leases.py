"""sweep_stale_discord_leases — celery task wrapper around the internal
sweep endpoint.

DB-side correctness (which rows get reaped at which thresholds) lives
in app/tests/test_internal_avatar_and_sweep::SweepStaleDiscordLeasesTest
since the actual delete is server-side now. These tests cover the
task-level contract: it forwards the right thresholds and returns the
total count.
"""

from unittest.mock import patch

from django.test import TestCase

from discordbot.tasks import sweep_stale_discord_leases


class SweepStaleLeasesTaskTest(TestCase):
    @patch("app.internal_client.sweep_discord_leases")
    def test_forwards_default_thresholds(self, mock_sweep):
        mock_sweep.return_value = {
            "pending_swept": 0,
            "failed_swept": 0,
            "total": 0,
        }
        sweep_stale_discord_leases()
        mock_sweep.assert_called_once_with(
            pending_threshold_minutes=5, failed_threshold_hours=1
        )

    @patch("app.internal_client.sweep_discord_leases")
    def test_returns_total_count(self, mock_sweep):
        mock_sweep.return_value = {
            "pending_swept": 2,
            "failed_swept": 3,
            "total": 5,
        }
        result = sweep_stale_discord_leases()
        self.assertEqual(result, 5)

    @patch("app.internal_client.sweep_discord_leases")
    def test_zero_total_when_nothing_swept(self, mock_sweep):
        mock_sweep.return_value = {
            "pending_swept": 0,
            "failed_swept": 0,
            "total": 0,
        }
        result = sweep_stale_discord_leases()
        self.assertEqual(result, 0)

    @patch("app.internal_client.sweep_discord_leases")
    def test_handles_missing_keys_defensively(self, mock_sweep):
        """If the endpoint returns an unexpected shape (e.g. network
        wrapper bailed mid-parse), the task must not crash beat."""
        mock_sweep.return_value = {}
        result = sweep_stale_discord_leases()
        self.assertEqual(result, 0)
