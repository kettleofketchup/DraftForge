from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch as mock_patch

from discordbot.components.base import SignupButton
from events.discord._shared import _direct_signup
from events.eligibility import UNMET_LABELS, Unmet
from events.schemas import SignupActionResponse, signed_up_text
from events.tests.base import EventTestCase


@asynccontextmanager
async def _fake_log_context(
    *_args: object, **_kwargs: object
) -> AsyncIterator[MagicMock]:
    yield MagicMock()


class DirectSignupLabelsTests(EventTestCase):
    @mock_patch("events.services.notify_signup_changed")
    def test_pending_signup_returns_labels(self, _notify: MagicMock) -> None:
        ev = self.make_event(min_mmr=3000)
        result = _direct_signup(ev, self.make_user())
        self.assertEqual(result["status"], "pending_approval")
        self.assertEqual(
            result["unmet_labels"], [UNMET_LABELS[Unmet.DOTA_RANK_UNDECLARED]]
        )
        SignupActionResponse.model_validate(result)

    @mock_patch("events.services.notify_signup_changed")
    def test_approved_signup_has_no_labels(self, _notify: MagicMock) -> None:
        result = _direct_signup(self.make_event(), self.make_user())
        self.assertIsNone(result.get("unmet_labels"))


class SignedUpTextTests(IsolatedAsyncioTestCase):
    def test_lists_labels_when_pending(self) -> None:
        text = signed_up_text("pending_approval", ["Rank not declared"])
        self.assertIn("pending_approval", text)
        self.assertIn("Rank not declared", text)

    def test_plain_without_labels(self) -> None:
        self.assertNotIn("\n", signed_up_text("approved", None))

    async def test_discord_pending_reply_lists_labels(self) -> None:
        label = UNMET_LABELS[Unmet.DOTA_RANK_UNDECLARED]
        interaction = MagicMock()
        interaction.user.id = 7
        interaction.user.name = "alice"
        with (
            mock_patch(
                "discordbot.components.base.signup_button",
                return_value={
                    "action": "signed_up",
                    "status": "pending_approval",
                    "unmet_labels": [label],
                },
            ),
            mock_patch(
                "discordbot.components.base.respond_to_signup_user",
                new_callable=AsyncMock,
            ) as respond,
            mock_patch(
                "discordbot.components.base.discord_log_context", _fake_log_context
            ),
        ):
            await SignupButton(1).callback(interaction)
        self.assertIn(label, respond.await_args.kwargs["content"])
