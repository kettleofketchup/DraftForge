"""The gateway DM choke point: discordbot.gateway_dm.send_interaction_dm."""

import asyncio
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import discord

from discordbot import gateway_dm
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import DMClaimBody, DMFinalizeBody

MOD = "discordbot.gateway_dm"
INTERACTION_ID = 987654321
USER_ID = 12345


def _interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.id = INTERACTION_ID
    interaction.user = MagicMock()
    interaction.user.id = USER_ID
    dm_channel = MagicMock()
    dm_channel.id = 555
    message = MagicMock()
    message.id = 777
    dm_channel.send = AsyncMock(return_value=message)
    interaction.user.create_dm = AsyncMock(return_value=dm_channel)
    return interaction


def _http_error(status: int, code: int = 0) -> discord.HTTPException:
    response = MagicMock(status=status, reason="err")
    cls = discord.Forbidden if status == 403 else discord.HTTPException
    if status >= 500:
        cls = discord.DiscordServerError
    return cls(response, {"code": code, "message": f"code {code}"})


class _Ledger:
    def __init__(
        self, stack: ExitStack, *, claim: ClaimResult | None, marked: bool | None
    ) -> None:
        self.claim = stack.enter_context(patch(f"{MOD}.claim_dm", return_value=claim))
        self.mark = stack.enter_context(
            patch(f"{MOD}.mark_dm_sending", return_value=marked)
        )
        self.finalize = stack.enter_context(
            patch(f"{MOD}.finalize_dm", return_value=True)
        )

    @property
    def claim_body(self) -> DMClaimBody:
        return self.claim.call_args.args[0]

    @property
    def final(self) -> DMFinalizeBody:
        self.finalize.assert_called_once()
        return self.finalize.call_args.args[1]


GRANTED = ClaimResult(
    id=41, granted=True, status=DMStatus.PENDING, attempts=1, created=True
)


@contextmanager
def _ledger(
    *, claim: ClaimResult | None = GRANTED, marked: bool | None = True
) -> Iterator[_Ledger]:
    with ExitStack() as stack:
        yield _Ledger(stack, claim=claim, marked=marked)


async def _send(
    interaction: MagicMock, **kwargs: object
) -> gateway_dm.GatewayDMOutcome:
    return await gateway_dm.send_interaction_dm(
        interaction,
        kind=DMKind.SIGNUP_CONFIRMATION,
        idempotency_key=f"signup_confirmation:interaction:{INTERACTION_ID}",
        subject=(DMSubject.EVENT, 9),
        context={"result": "signed_up", "interaction_id": INTERACTION_ID},
        content="hi",
        **kwargs,
    )


class SendInteractionDMTests(IsolatedAsyncioTestCase):
    async def test_claim_send_finalize_sent(self) -> None:
        interaction = _interaction()
        with _ledger() as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "sent")
        body = ledger.claim_body
        self.assertEqual(body.claim_token, str(INTERACTION_ID))
        self.assertEqual(body.kind, "signup_confirmation")
        self.assertEqual(body.discord_user_id, str(USER_ID))
        self.assertEqual((body.subject_type, body.subject_id), ("event", 9))
        self.assertFalse(body.has_components)
        ledger.mark.assert_called_once_with(41, claim_token=str(INTERACTION_ID))
        send = interaction.user.create_dm.return_value.send
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["nonce"], "dm41")
        final = ledger.final
        self.assertEqual(final.status, "sent")
        self.assertEqual(final.discord_channel_id, "555")
        self.assertEqual(final.discord_message_id, "777")
        self.assertEqual(final.claim_token, str(INTERACTION_ID))

    async def test_has_components_follows_view(self) -> None:
        with _ledger() as ledger:
            await _send(_interaction(), view=MagicMock(spec=discord.ui.View))
        self.assertTrue(ledger.claim_body.has_components)

    async def test_forbidden_50007_finalizes_failed_returns_forbidden(self) -> None:
        interaction = _interaction()
        interaction.user.create_dm.return_value.send.side_effect = _http_error(
            403, 50007
        )
        with _ledger() as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "forbidden")
        final = ledger.final
        self.assertEqual(final.status, "failed")
        self.assertEqual(final.error_code, 50007)
        self.assertEqual(final.error_class, "permanent")
        self.assertEqual(final.http_status, 403)

    async def test_other_4xx_failed(self) -> None:
        interaction = _interaction()
        interaction.user.create_dm.return_value.send.side_effect = _http_error(
            400, 50035
        )
        with _ledger() as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "failed")
        self.assertEqual(ledger.final.status, "failed")
        self.assertEqual(ledger.final.error_class, "pre_send")

    async def test_ledger_unavailable_no_dm(self) -> None:
        interaction = _interaction()
        with _ledger(claim=None) as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "ledger_unavailable")
        interaction.user.create_dm.assert_not_awaited()
        ledger.mark.assert_not_called()
        ledger.finalize.assert_not_called()

    async def test_mark_sending_failure_no_dm(self) -> None:
        for marked in (False, None):
            with self.subTest(marked=marked):
                interaction = _interaction()
                with _ledger(marked=marked) as ledger:
                    outcome = await _send(interaction)
                self.assertEqual(outcome, "ledger_unavailable")
                interaction.user.create_dm.assert_not_awaited()
                self.assertEqual(ledger.final.status, "failed")
                self.assertEqual(ledger.final.error_class, "pre_send")

    async def test_duplicate_no_dm(self) -> None:
        interaction = _interaction()
        claim = ClaimResult(
            id=41, granted=False, status=DMStatus.SENT, attempts=0, created=False
        )
        with _ledger(claim=claim) as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "duplicate")
        interaction.user.create_dm.assert_not_awaited()
        ledger.finalize.assert_not_called()

    async def test_http_5xx_unknown(self) -> None:
        interaction = _interaction()
        interaction.user.create_dm.return_value.send.side_effect = _http_error(503)
        with _ledger() as ledger:
            outcome = await _send(interaction)
        self.assertEqual(outcome, "unknown")
        self.assertEqual(ledger.final.status, "unknown")

    async def test_timeout_unknown(self) -> None:
        for exc in (asyncio.TimeoutError(), aiohttp.ClientConnectionError("x")):
            with self.subTest(exc=type(exc).__name__):
                interaction = _interaction()
                interaction.user.create_dm.return_value.send.side_effect = exc
                with _ledger() as ledger:
                    outcome = await _send(interaction)
                self.assertEqual(outcome, "unknown")
                self.assertEqual(ledger.final.status, "unknown")

    async def test_unexpected_exception_after_mark_finalizes_unknown(self) -> None:
        interaction = _interaction()
        interaction.user.create_dm.side_effect = RuntimeError("boom")
        with _ledger() as ledger:
            with self.assertRaises(RuntimeError):
                await _send(interaction)
        ledger.mark.assert_called_once()
        self.assertEqual(ledger.final.status, "unknown")

    async def test_cancel_after_mark_finalizes_once(self) -> None:
        interaction = _interaction()
        interaction.user.create_dm.return_value.send.side_effect = (
            asyncio.CancelledError()
        )
        with _ledger() as ledger:
            with self.assertRaises(asyncio.CancelledError):
                await _send(interaction)
        self.assertEqual(ledger.final.status, "unknown")

    async def test_finalize_rejected_is_logged(self) -> None:
        interaction = _interaction()
        with _ledger() as ledger, patch(f"{MOD}.log") as log:
            ledger.finalize.return_value = False
            outcome = await _send(interaction)
        self.assertEqual(outcome, "sent")
        events = [c.args[0] for c in log.error.call_args_list]
        self.assertIn("dm_ledger_finalize_failed", events)

    async def test_in_gateway_dm_flag_set_during_send(self) -> None:
        interaction = _interaction()
        seen: list[bool] = []

        async def _record(*_a: object, **_kw: object) -> MagicMock:
            seen.append(gateway_dm._IN_GATEWAY_DM.get())
            return MagicMock(id=777)

        interaction.user.create_dm.return_value.send.side_effect = _record
        with _ledger():
            await _send(interaction)
        self.assertEqual(seen, [True])
        self.assertFalse(gateway_dm._IN_GATEWAY_DM.get())
