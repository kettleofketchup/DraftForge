"""Tests for the internal Discord lease sweep endpoint."""

from datetime import timedelta
from itertools import count

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SweepStaleDiscordLeasesTest(TestCase):
    # Each call yields a unique source_id so we dodge the partial
    # UniqueConstraint on (source, source_id) WHERE success IS NOT FALSE.
    # Defined as a class attribute (not an instance attr) so every test
    # method that calls _make_log within the class shares the same counter
    # but no test ever sees a value from a prior test (the DB rolls back).
    _ids = count(1000)

    def _make_log(self, **kwargs):
        from discordbot.models import DiscordMessageLog

        defaults = {
            "channel_id": "123",
            "source": "event_announcement",
            "source_id": next(type(self)._ids),
            "embed_data": {"title": "x"},
            "claimed_at": timezone.now(),
        }
        defaults.update(kwargs)
        return DiscordMessageLog.objects.create(**defaults)

    def test_sweeps_stale_pending_and_aged_failures(self):
        from discordbot.models import DiscordMessageLog

        now = timezone.now()
        # Stale pending (claimed >5 min ago, success NULL) → deleted
        self._make_log(claimed_at=now - timedelta(minutes=10), success=None)
        # Recent pending (only 1 min old) → kept
        self._make_log(claimed_at=now - timedelta(minutes=1), success=None)
        # Aged failure (>1 hour, success=False) → deleted
        self._make_log(claimed_at=now - timedelta(hours=2), success=False)
        # Recent failure (only 5 min old) → kept
        self._make_log(claimed_at=now - timedelta(minutes=5), success=False)
        # Successful log → never touched
        self._make_log(claimed_at=now - timedelta(hours=3), success=True)

        self.assertEqual(DiscordMessageLog.objects.count(), 5)

        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["pending_swept"], 1)
        self.assertEqual(body["failed_swept"], 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(DiscordMessageLog.objects.count(), 3)

    def test_custom_thresholds(self):
        from discordbot.models import DiscordMessageLog

        now = timezone.now()
        # Only 2 min old — below default 5-min threshold, but caller can lower it.
        self._make_log(claimed_at=now - timedelta(minutes=2), success=None)

        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": 1, "failed_threshold_hours": 24},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["pending_swept"], 1)
        self.assertEqual(DiscordMessageLog.objects.count(), 0)

    def test_rejects_non_integer_thresholds(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": "abc"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_negative_pending_threshold(self):
        """Negative threshold would push the cutoff into the future and
        match every row in the table — must 400."""
        from discordbot.models import DiscordMessageLog

        # Pre-existing fresh log; must NOT be deleted.
        log_row = self._make_log(claimed_at=timezone.now(), success=None)

        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": -5},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(DiscordMessageLog.objects.filter(pk=log_row.pk).exists())

    def test_rejects_negative_failed_threshold(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"failed_threshold_hours": -1},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_accepts_zero_thresholds(self):
        """Zero is a valid threshold (sweeps anything at-or-before now)."""
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": 0, "failed_threshold_hours": 0},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)

    def test_requires_token(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/sweep-stale-leases/", {}, format="json")
        self.assertEqual(resp.status_code, 403)
