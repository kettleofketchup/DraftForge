import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from django.test import TestCase


def run_async(coro):
    """Run an async function in a new event loop.

    discord.py 2.x Views/Modals require a running event loop at construction time
    (asyncio.get_running_loop() in View.__init__), so all construction must happen
    inside an async context.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class EventSignupViewTest(TestCase):
    def test_view_has_signup_button(self):
        async def _test():
            from discordbot.components import EventSignupView

            view = EventSignupView(event_id=42, has_repeater=False)
            custom_ids = [c.custom_id for c in view.children if hasattr(c, "custom_id")]
            self.assertIn("event_signup:42", custom_ids)

        run_async(_test())

    def test_view_has_notify_button_when_repeater(self):
        async def _test():
            from discordbot.components import EventSignupView

            view = EventSignupView(event_id=42, has_repeater=True)
            custom_ids = [c.custom_id for c in view.children if hasattr(c, "custom_id")]
            self.assertIn("event_notify:42", custom_ids)

        run_async(_test())

    def test_view_no_notify_button_without_repeater(self):
        async def _test():
            from discordbot.components import EventSignupView

            view = EventSignupView(event_id=42, has_repeater=False)
            custom_ids = [
                c.custom_id
                for c in view.children
                if hasattr(c, "custom_id") and c.custom_id
            ]
            self.assertNotIn("event_notify:42", custom_ids)

        run_async(_test())

    def test_view_has_link_button(self):
        async def _test():
            from discordbot.components import EventSignupView

            view = EventSignupView(
                event_id=42, has_repeater=False, site_url="https://example.com"
            )
            link_buttons = [
                c for c in view.children if isinstance(c, discord.ui.Button) and c.url
            ]
            self.assertEqual(len(link_buttons), 1)
            self.assertIn("/events/42", link_buttons[0].url)

        run_async(_test())

    def test_view_is_persistent(self):
        async def _test():
            from discordbot.components import EventSignupView

            view = EventSignupView(event_id=42, has_repeater=False)
            self.assertIsNone(view.timeout)

        run_async(_test())


class EventSignupModalTest(TestCase):
    def test_dota_modal_has_text_inputs_not_selects(self):
        """Modals must only use TextInput — NOT Select."""

        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=1, prefill={})
            for item in modal.children:
                self.assertIsInstance(
                    item,
                    discord.ui.TextInput,
                    f"Modal contains non-TextInput: {type(item)}",
                )

        run_async(_test())

    def test_dota_modal_has_steam_positions_rank(self):
        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=1, prefill={})
            custom_ids = [item.custom_id for item in modal.children]
            self.assertTrue(any("steam" in cid for cid in custom_ids))
            self.assertTrue(any("positions" in cid for cid in custom_ids))
            self.assertTrue(any("rank_status" in cid for cid in custom_ids))

        run_async(_test())

    def test_deadlock_modal_has_rank_and_date(self):
        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=2, prefill={})
            custom_ids = [item.custom_id for item in modal.children]
            self.assertTrue(any("deadlock_rank" in cid for cid in custom_ids))
            self.assertTrue(any("deadlock_date" in cid for cid in custom_ids))

        run_async(_test())

    def test_steam_input_prefilled(self):
        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(
                event_id=42, game_type=1, prefill={"unverified_steam_id": "12345"}
            )
            steam_inputs = [
                i for i in modal.children if "steam" in getattr(i, "custom_id", "")
            ]
            # When steam ID is pre-filled, the steam input should not appear
            self.assertEqual(len(steam_inputs), 0)

        run_async(_test())

    def test_max_5_components(self):
        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=1, prefill={})
            self.assertLessEqual(len(modal.children), 5)

        run_async(_test())


class RankDetailsViewTest(TestCase):
    def test_active_rank_has_medal_select(self):
        async def _test():
            from discordbot.components import RankDetailsView

            view = RankDetailsView(event_id=42, rank_status="active")
            has_select = any(isinstance(c, discord.ui.Select) for c in view.children)
            self.assertTrue(has_select)

        run_async(_test())

    def test_previous_rank_has_button(self):
        async def _test():
            from discordbot.components import RankDetailsView

            view = RankDetailsView(event_id=42, rank_status="previous")
            has_button = any(isinstance(c, discord.ui.Button) for c in view.children)
            self.assertTrue(has_button)

        run_async(_test())

    def test_never_rank_has_button(self):
        async def _test():
            from discordbot.components import RankDetailsView

            view = RankDetailsView(event_id=42, rank_status="never")
            has_button = any(isinstance(c, discord.ui.Button) for c in view.children)
            self.assertTrue(has_button)

        run_async(_test())
