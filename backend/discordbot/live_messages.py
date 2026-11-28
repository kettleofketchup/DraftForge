"""Web-side delivery tracking for opt-in Discord Components V2 renderers."""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any, Literal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

from discordbot.models import (
    DiscordDM,
    DMKind,
    DMSubject,
    LiveDiscordMessage,
    LiveMessageState,
)
from discordbot.payloads import live_component_digest
from telemetry.logging import get_logger

log = get_logger(__name__)

# One Discord rate-limit token wait plus one bounded HTTP PATCH fits within
# this interval. Never retain a DB transaction or row lock while doing HTTP.
EDIT_LEASE = timedelta(minutes=3)
CLAIM_SCAN_LIMIT = 32

EditOutcome = Literal["edited", "missing", "blocked", "retry"]


def _snowflake(value: str | None) -> bool:
    return bool(
        value
        and len(value) <= 20
        and value.isascii()
        and value.isdecimal()
        and 0 < int(value) < 2**64
    )


def track_message(
    *,
    renderer: str,
    subject_id: int,
    channel_id: str,
    message_id: str,
    dm: DiscordDM | None = None,
    initial_digest: str = "",
) -> LiveDiscordMessage:
    """Enroll a confirmed delivery. Repeating enrollment preserves pending edits."""
    from discordbot.live_renderers import RENDERERS

    if renderer not in RENDERERS:
        raise ValueError(f"unknown live message renderer: {renderer}")
    if not _snowflake(channel_id) or not _snowflake(message_id):
        raise ValueError("live message enrollment requires Discord snowflakes")
    if dm is not None and dm.delivered_address != (channel_id, message_id):
        raise ValueError("live message must match its delivered DM")
    row, _ = LiveDiscordMessage.objects.get_or_create(
        message_id=message_id,
        defaults={
            "channel_id": channel_id,
            "renderer": renderer,
            "subject_id": subject_id,
            "dm": dm,
            "applied_hash": initial_digest,
        },
    )
    if (row.renderer, row.subject_id, row.channel_id, row.dm_id) != (
        renderer,
        subject_id,
        channel_id,
        dm.pk if dm else None,
    ):
        raise ValueError("live message already enrolled for another delivery")
    return row


def track_delivered_dm(dm: DiscordDM) -> None:
    address = dm.delivered_address
    if (
        dm.kind == DMKind.SIGNUP_REMINDER
        and dm.subject_type == DMSubject.EVENT
        and dm.subject_id is not None
        and dm.context.get("live_v2") is True
        and dm.has_components
        and address is not None
        and all(_snowflake(value) for value in address)
    ):
        channel_id, message_id = address
        track_message(
            renderer="event_signup_reminder",
            subject_id=dm.subject_id,
            channel_id=channel_id,
            message_id=message_id,
            dm=dm,
            initial_digest=dm.context.get("live_digest") or "",
        )


def invalidate_live_messages(renderer: str, subject_id: int) -> int:
    """Call alongside the source write. The dirty mark rolls back with it."""
    return invalidate_live_subjects(renderer, (subject_id,))


def invalidate_live_subjects(renderer: str, subject_ids: Iterable[int]) -> int:
    """Mark multiple subjects dirty in one UPDATE, including queryset subqueries."""
    return LiveDiscordMessage.objects.filter(
        renderer=renderer,
        subject_id__in=subject_ids,
        state__in=(LiveMessageState.ACTIVE, LiveMessageState.BLOCKED),
    ).update(
        state=LiveMessageState.ACTIVE,
        revision=F("revision") + 1,
        # Preserve an active lease or a retry deadline during bursts.
        next_attempt_at=Coalesce("next_attempt_at", timezone.now()),
    )


def claim_live_edit(*, discord_user_id: str | None = None) -> dict[str, Any] | None:
    """Claim one due edit. Competing workers compare-and-swap on the deadline."""
    from discordbot.live_renderers import render_live_message

    rows = LiveDiscordMessage.objects.nocache().filter(state=LiveMessageState.ACTIVE)
    if discord_user_id is not None:
        rows = rows.filter(dm__discord_user_id=discord_user_id)
    if getattr(settings, "TEST", False):
        target = getattr(settings, "TEST_DISCORD_USER_ID", "")
        if not target or not getattr(settings, "DISCORD_BOT_TOKEN", ""):
            return None
        rows = rows.filter(dm__discord_user_id=target)

    # Bound the request, even if a subject was removed or its rendered view
    # hasn't changed for many recipients. Beat continues on the next pass.
    for _ in range(CLAIM_SCAN_LIMIT):
        now = timezone.now()
        due = rows.filter(next_attempt_at__lte=now)
        row = due.order_by("next_attempt_at", "pk").first()
        if row is None:
            return None

        token = str(uuid4())
        if not due.filter(
            pk=row.pk,
            lease_token=row.lease_token,
            next_attempt_at=row.next_attempt_at,
            applied_hash=row.applied_hash,
        ).update(
            lease_token=token,
            lease_revision=F("revision"),
            lease_hash="",
            next_attempt_at=now + EDIT_LEASE,
        ):
            continue

        owned = LiveDiscordMessage.objects.filter(pk=row.pk, lease_token=token)
        try:
            payload = render_live_message(row.renderer, row.subject_id)
            if payload is None:
                owned.update(
                    state=LiveMessageState.SOURCE_GONE,
                    next_attempt_at=None,
                    lease_token=None,
                    lease_hash="",
                )
                continue
            digest = live_component_digest(payload["components"])
        except Exception:
            log.exception(
                "live_message_render_failed",
                system="discord",
                subsystem="live_messages",
                renderer=row.renderer,
                live_message_id=row.pk,
            )
            finish_live_edit(row.pk, token, "retry")
            continue

        if not owned.update(lease_hash=digest):
            continue
        # With an expired lease, the previous PATCH may have succeeded without
        # an ACK. Reconcile even if this payload matches the last *known* edit.
        if row.lease_token is None and row.applied_hash == digest:
            _finish_success(row.pk, token, patched=False)
            continue
        return {
            "id": row.pk,
            "token": token,
            "channel_id": row.channel_id,
            "message_id": row.message_id,
            "payload": payload,
        }
    return None


def _finish_success(pk: int, token: str, *, patched: bool) -> bool:
    with transaction.atomic():
        owned = (
            LiveDiscordMessage.objects.select_for_update()
            .nocache()
            .filter(pk=pk, lease_token=token)
        )
        row = owned.first()
        now = timezone.now()
        if row is None:
            if patched:
                # An expired worker could have reached Discord after the new
                # worker did. It cannot acknowledge the new lease; mark the
                # address dirty to repair the visible layout on a later pass.
                LiveDiscordMessage.objects.filter(
                    pk=pk, state=LiveMessageState.ACTIVE
                ).update(
                    revision=F("revision") + 1,
                    applied_hash="",
                    next_attempt_at=Coalesce("next_attempt_at", now),
                )
            return False
        dirty = row.revision != row.lease_revision
        owned.update(
            applied_revision=row.lease_revision,
            # A stale success may have dirtied this row while the PATCH was
            # in flight. In that case the next pass must reach Discord.
            applied_hash="" if dirty else row.lease_hash,
            lease_token=None,
            lease_hash="",
            failures=0,
            error_code=None,
            next_attempt_at=now if dirty else None,
            last_edited_at=now if patched else row.last_edited_at,
        )
        return True


def finish_live_edit(
    pk: int,
    token: str,
    outcome: EditOutcome,
    *,
    error_code: int | None = None,
    retry_after: float | None = None,
) -> bool:
    """Acknowledge exactly one lease; later invalidations stay pending."""
    if outcome == "edited":
        return _finish_success(pk, token, patched=True)
    if outcome not in ("retry", "missing", "blocked"):
        raise ValueError("unknown live edit outcome")

    with transaction.atomic():
        owned = (
            LiveDiscordMessage.objects.select_for_update()
            .nocache()
            .filter(pk=pk, lease_token=token)
        )
        row = owned.first()
        if row is None:
            return False
        due = None
        state = outcome
        if outcome == "retry":
            state = LiveMessageState.ACTIVE
            backoff = min(3600, 5 * 2 ** min(row.failures, 10))
            # Discord delays are seconds. Keep malformed, enormous upstream
            # values representable in both Python and the database.
            delay = min(365 * 24 * 3600, max(backoff, retry_after or 0))
            due = timezone.now() + timedelta(seconds=delay)
        elif outcome == "blocked" and row.revision != row.lease_revision:
            # The rejected PATCH used an older snapshot. Allow a changed
            # payload to proceed, as for invalidations after a rejection.
            state = LiveMessageState.ACTIVE
            due = timezone.now()
        owned.update(
            state=state,
            next_attempt_at=due,
            applied_hash="",
            lease_hash="",
            lease_token=None,
            failures=row.failures + 1,
            error_code=error_code,
        )
        return True
