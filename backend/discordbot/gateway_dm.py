"""The gateway DM choke point: every DM the bot process sends goes through here.

No ORM here (the gateway bot has no database); the ledger is reached over the
internal API through ``discordbot.internal_client.dm_ledger``.
"""

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

import aiohttp
import discord
from asgiref.sync import sync_to_async

from discordbot.dm_ledger import PERMANENT_DM_ERROR_CODES, ErrorClass
from discordbot.internal_client.dm_ledger import claim_dm, finalize_dm, mark_dm_sending
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import DMClaimBody, DMFinalizeBody
from telemetry.logging import get_logger

log = get_logger(__name__)

GatewayDMOutcome = Literal[
    "sent", "forbidden", "duplicate", "ledger_unavailable", "failed", "unknown"
]

ERROR_MAX_LEN = 300
_LOG = {"system": "discord", "subsystem": "dm"}
_IN_GATEWAY_DM: ContextVar[bool] = ContextVar("_IN_GATEWAY_DM", default=False)


@dataclass(slots=True)
class _SendState:
    kind: DMKind
    ledger_id: int
    claim_token: str
    discord_user_id: str
    finalized: bool = False
    marked: bool = False


async def _finalize(
    state: _SendState,
    status: DMStatus,
    *,
    error_class: ErrorClass | None = None,
    channel_id: str = "",
    message_id: str | None = None,
    http_status: int | None = None,
    error_code: int | None = None,
    error: str = "",
) -> None:
    state.finalized = True
    body = DMFinalizeBody(
        claim_token=state.claim_token,
        status=status.value,
        error_class=error_class,
        discord_channel_id=channel_id,
        discord_message_id=message_id,
        http_status=http_status,
        error_code=error_code,
        error=error[:ERROR_MAX_LEN],
    )
    fields = {
        **_LOG,
        "dm_kind": state.kind.value,
        "ledger_id": state.ledger_id,
        "discord_user_id": state.discord_user_id,
        "status": status.value,
    }
    if status == DMStatus.SENT:
        log.info("dm_sent", **fields)
    else:
        log.warning(
            "dm_failed",
            **fields,
            error_class=error_class,
            error_code=error_code,
            http_status_code=http_status,
            error=error[:ERROR_MAX_LEN],
        )
    if not await sync_to_async(finalize_dm, thread_sensitive=False)(
        state.ledger_id, body
    ):
        log.error("dm_ledger_finalize_failed", **fields)


async def _http_failure(
    state: _SendState, exc: discord.HTTPException
) -> GatewayDMOutcome:
    code = exc.code or None
    error = (exc.text or str(exc))[:ERROR_MAX_LEN]
    if 400 <= exc.status < 500:
        error_class: ErrorClass = (
            "permanent" if code in PERMANENT_DM_ERROR_CODES else "pre_send"
        )
        await _finalize(
            state,
            DMStatus.FAILED,
            error_class=error_class,
            http_status=exc.status,
            error_code=code,
            error=error,
        )
        if isinstance(exc, discord.Forbidden) and code == 50007:
            return "forbidden"
        return "failed"
    await _finalize(
        state,
        DMStatus.UNKNOWN,
        http_status=exc.status if 100 <= exc.status <= 599 else None,
        error_code=code,
        error=error,
    )
    return "unknown"


async def _deliver(
    state: _SendState,
    interaction: discord.Interaction,
    *,
    content: str | None,
    embed: discord.Embed | None,
    view: discord.ui.View | None,
) -> GatewayDMOutcome:
    try:
        marked = await sync_to_async(mark_dm_sending, thread_sensitive=False)(
            state.ledger_id, claim_token=state.claim_token
        )
        if not marked:
            log.error(
                "dm_ledger_unavailable",
                **_LOG,
                dm_kind=state.kind.value,
                ledger_id=state.ledger_id,
                discord_user_id=state.discord_user_id,
                interaction_id=state.claim_token,
                status="ledger_unavailable",
            )
            await _finalize(
                state,
                DMStatus.FAILED,
                error_class="pre_send",
                error="mark_sending_refused"
                if marked is False
                else "mark_sending_unavailable",
            )
            return "ledger_unavailable"
        state.marked = True

        try:
            dm_channel = await interaction.user.create_dm()
            message = await dm_channel.send(
                content=content,
                embed=embed,
                view=view,
                nonce=f"dm{state.ledger_id}",
            )
        except discord.HTTPException as exc:
            return await _http_failure(state, exc)
        except (TimeoutError, aiohttp.ClientError) as exc:
            await _finalize(
                state, DMStatus.UNKNOWN, error=f"{type(exc).__name__}: {exc}"
            )
            return "unknown"

        await _finalize(
            state,
            DMStatus.SENT,
            channel_id=str(dm_channel.id),
            message_id=str(message.id),
        )
        return "sent"
    finally:
        if not state.finalized:
            if state.marked:
                await _finalize(
                    state, DMStatus.UNKNOWN, error="interrupted_after_send_start"
                )
            else:
                await _finalize(
                    state,
                    DMStatus.FAILED,
                    error_class="pre_send",
                    error="interrupted_before_send",
                )


async def send_interaction_dm(
    interaction: discord.Interaction,
    *,
    kind: DMKind,
    idempotency_key: str,
    subject: tuple[DMSubject, int] | None,
    context: Mapping[str, object],
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> GatewayDMOutcome:
    token = str(interaction.id)
    discord_user_id = str(interaction.user.id)
    subject_type, subject_id = subject if subject else (None, None)
    body = DMClaimBody(
        kind=kind.value,
        idempotency_key=idempotency_key,
        claim_token=token,
        discord_user_id=discord_user_id,
        subject_type=subject_type.value if subject_type else None,
        subject_id=subject_id,
        context=dict(context),
        has_components=view is not None,
    )
    claim = await sync_to_async(claim_dm, thread_sensitive=False)(body)
    if claim is None:
        log.error(
            "dm_ledger_unavailable",
            **_LOG,
            dm_kind=kind.value,
            discord_user_id=discord_user_id,
            interaction_id=token,
            status="ledger_unavailable",
        )
        return "ledger_unavailable"
    if not claim.granted:
        log.info(
            "dm_duplicate_suppressed",
            **_LOG,
            dm_kind=kind.value,
            ledger_id=claim.id,
            discord_user_id=discord_user_id,
            status=claim.status.value,
        )
        return "duplicate"

    state = _SendState(
        kind=kind,
        ledger_id=claim.id,
        claim_token=token,
        discord_user_id=discord_user_id,
    )
    flag = _IN_GATEWAY_DM.set(True)
    try:
        return await _deliver(
            state, interaction, content=content, embed=embed, view=view
        )
    finally:
        _IN_GATEWAY_DM.reset(flag)
