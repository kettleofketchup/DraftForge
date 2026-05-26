"""Unit tests for discord_log_context CM and InteractionContext."""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock

import structlog
from structlog.contextvars import clear_contextvars, get_contextvars
from structlog.testing import capture_logs


class InteractionContextTests(TestCase):
    def test_starts_empty(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        self.assertIsNone(ctx.outcome)
        self.assertEqual(ctx.extra, {})

    def test_set_outcome_overwrites(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        ctx.set_outcome("signed_up")
        ctx.set_outcome("error")
        self.assertEqual(ctx.outcome, "error")

    def test_add_merges_kwargs(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        ctx.add(signup_id=42)
        ctx.add(signup_status="confirmed")
        self.assertEqual(ctx.extra, {"signup_id": 42, "signup_status": "confirmed"})
