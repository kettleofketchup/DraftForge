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
    def test_dota_modal_components_are_textinput_or_label(self):
        """Modal items must be TextInput or Label (Label wraps Select for components-v2)."""

        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=1, prefill={})
            allowed = (discord.ui.TextInput, discord.ui.Label)
            for item in modal.children:
                self.assertIsInstance(
                    item,
                    allowed,
                    f"Modal contains unsupported item: {type(item)}",
                )

        run_async(_test())

    def test_dota_modal_has_friend_id_and_rank_status(self):
        """Dota modal collects friend_id (when missing) and rank_status; positions
        are gathered in a follow-up ephemeral, not in the modal."""

        async def _test():
            from discordbot.components import EventSignupModal

            modal = EventSignupModal(event_id=42, game_type=1, prefill={})
            custom_ids = []
            for item in modal.children:
                if hasattr(item, "custom_id") and item.custom_id:
                    custom_ids.append(item.custom_id)
                # Label wraps a component (e.g. Select) where the custom_id lives
                wrapped = getattr(item, "component", None)
                if wrapped is not None and getattr(wrapped, "custom_id", None):
                    custom_ids.append(wrapped.custom_id)
            self.assertTrue(
                any("friend_id" in cid for cid in custom_ids),
                f"missing friend_id in {custom_ids}",
            )
            self.assertTrue(
                any("rank_status" in cid for cid in custom_ids),
                f"missing rank_status in {custom_ids}",
            )

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
                event_id=42, game_type=1, prefill={"unverified_friend_id": "12345"}
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

    def test_previous_rank_has_medal_select(self):
        # RankDetailsView is now all-selects (medal+star for active/previous,
        # battle-cup tier for never).
        async def _test():
            from discordbot.components import RankDetailsView

            view = RankDetailsView(event_id=42, rank_status="previous")
            self.assertTrue(any(isinstance(c, discord.ui.Select) for c in view.children))

        run_async(_test())

    def test_never_rank_has_battlecup_select(self):
        async def _test():
            from discordbot.components import RankDetailsView

            view = RankDetailsView(event_id=42, rank_status="never")
            self.assertTrue(any(isinstance(c, discord.ui.Select) for c in view.children))

        run_async(_test())


# ---------------------------------------------------------------------------
# Regression test: MedalSelect → StarSelect medal-encoding race
#
# Verifies that picking "Crusader" in MedalSelect rebuilds the view such that
# StarSelect.custom_id is `rank_star:{event_id}:Crusader` — NOT the initial
# default of `rank_star:{event_id}:Herald`. Without the fix in
# backend/discordbot/components.py:MedalSelect.callback, this test would fail.
# ---------------------------------------------------------------------------

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from discordbot.components import MedalSelect, RankDetailsView, StarSelect


class TestMedalSelectRebuildsView(IsolatedAsyncioTestCase):
    async def test_callback_rebuilds_view_with_medal_in_star_custom_id(self):
        event_id = 42
        medal = MedalSelect(
            event_id, rank_status="active", require_screenshot=False
        )
        # discord.py populates `values` from the user's selection before callback fires
        medal._values = ["Crusader"]  # private attr used by ui.Select

        # Mock the interaction.response.edit_message
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await medal.callback(interaction)

        # edit_message must have been called once
        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args.kwargs

        # The new view must contain a StarSelect with custom_id encoding "Crusader"
        view = kwargs["view"]
        star_selects = [c for c in view.children if isinstance(c, StarSelect)]
        self.assertEqual(len(star_selects), 1)
        self.assertEqual(
            star_selects[0].custom_id, f"rank_star:{event_id}:Crusader"
        )

        # Content includes the medal name
        self.assertIn("Crusader", kwargs["content"])

    async def test_callback_preserves_previous_rank_status(self):
        event_id = 99
        medal = MedalSelect(
            event_id, rank_status="previous", require_screenshot=False
        )
        medal._values = ["Divine"]

        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await medal.callback(interaction)

        kwargs = interaction.response.edit_message.call_args.kwargs
        # Label should say "Previous rank", not "Rank"
        self.assertIn("Previous rank", kwargs["content"])
        # Rebuilt view's StarSelect should still be in active/previous mode
        view = kwargs["view"]
        star = next(c for c in view.children if isinstance(c, StarSelect))
        self.assertEqual(star.rank_status, "previous")
