# backend/discordbot/tasks.py
"""Celery tasks for Discord bot scheduled operations."""

from datetime import datetime, timedelta
from typing import Any

import requests
from celery import shared_task
from pydantic import ValidationError

from app.internal_client import (
    get_due_scheduled_events,
    sweep_discord_leases,
    update_scheduled_event,
)
from discordbot.activity_launch_gateway import prepare_launch_payload
from discordbot.internal_client.leadership_actions import SAVE_FAILED, review_click
from discordbot.schemas import ReviewClickBody
from discordbot.utils import sync_add_reactions, sync_send_embed
from telemetry.logging import get_logger

log = get_logger(__name__)


@shared_task
def check_scheduled_events() -> str:
    """
    Check for and post scheduled events that are due.
    Runs every 60 seconds via Celery beat.

    All reads via internal HTTP API. Embeds built from template data.
    """

    due_events = get_due_scheduled_events()
    processed = 0

    for se in due_events:
        tpl = se.template
        log.info(
            "scheduled_event_posting",
            system="events",
            subsystem="scheduling",
            scheduled_event_id=se.pk,
            template=tpl.name,
        )

        # Build embed from template data (same fields as event_announcement_embed)
        color = int(tpl.color.lstrip("#"), 16) if tpl.color else 0x7289DA
        response = sync_send_embed(
            channel_id=tpl.channel_id,
            title=tpl.title,
            description=tpl.description,
            color=color,
            footer=(
                {"text": "React: \u2705 Yes | \u2753 Maybe | \u274c No"}
                if tpl.include_rsvp
                else None
            ),
            source="scheduled_event",
            source_id=se.pk,
        )

        if response and "id" in response:
            message_id = response["id"]

            if tpl.include_rsvp:
                sync_add_reactions(tpl.channel_id, message_id)

            log.info(
                "scheduled_event_posted",
                system="events",
                subsystem="scheduling",
                scheduled_event_id=se.pk,
                template=tpl.name,
                message_id=message_id,
            )
        else:
            log.error(
                "scheduled_event_post_failed",
                system="events",
                subsystem="scheduling",
                scheduled_event_id=se.pk,
                template=tpl.name,
            )
            continue

        if se.is_recurring and se.next_post_at:
            dt = datetime.fromisoformat(se.next_post_at) + timedelta(days=7)
            update_scheduled_event(
                se.pk,
                discord_message_id=None,
                next_post_at=dt.isoformat(),
            )
            log.info(
                "scheduled_event_recurrence_set",
                system="events",
                subsystem="scheduling",
                scheduled_event_id=se.pk,
                template=tpl.name,
                next_post_at=dt.isoformat(),
            )
        else:
            update_scheduled_event(se.pk, discord_message_id=message_id)
        processed += 1

    return f"Processed {processed} scheduled events"


@shared_task
def sweep_stale_discord_leases() -> int:
    """Reap stuck DiscordMessageLog rows so the partial unique constraint
    doesn't permanently brick reminders.

    Two recovery cases:
    - NULL pending leases >5 min old: worker crashed between claim and
      finalize. Delete so the next poll can re-claim.
    - False failed rows >1 hour old: Discord transient 5xx, rate-limit, or
      auth issue has likely passed. Delete so the next poll can retry.
      Admins should investigate via the original failed log row before it
      ages out.

    The 60-second beat sweeps pending leases after the 5-minute threshold;
    reminder retries then wait for the next 30-second poll.

    Both deletes happen server-side via the internal endpoint — the
    worker stays ORM-free.
    """

    result = sweep_discord_leases(pending_threshold_minutes=5, failed_threshold_hours=1)
    pending_swept = result.get("pending_swept", 0)
    failed_swept = result.get("failed_swept", 0)
    total = pending_swept + failed_swept
    if total:
        log.warning(
            "discord_leases_swept",
            system="discord",
            subsystem="lease",
            pending_swept=pending_swept,
            failed_swept=failed_swept,
            total=total,
        )
    return total


@shared_task
def complete_activity_launch(
    application_id: str,
    interaction_token: str,
    discord_user_id: str,
    kind: str,
    draft_id: int,
) -> None:
    """Finish an authenticated Discord interaction without touching the ORM."""

    # Only signed HTTP interactions enqueue this task. Values are still
    # constrained before using them in a URL; tokens must never enter logs.
    if (
        not application_id.isdigit()
        or not interaction_token
        or "/" in interaction_token
    ):
        return
    payload = prepare_launch_payload(discord_user_id, kind, draft_id)
    try:
        response = requests.patch(
            f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original",
            json={
                "content": payload["content"],
                "components": payload["components"],
                "allowed_mentions": {"parse": []},
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        # Request exceptions include the URL (and interaction credential).
        log.warning(
            "activity_launch_followup_failed", system="discord", subsystem="activity"
        )


def _interaction_webhook(payload: dict[str, Any]) -> str | None:
    application_id = str(payload.get("application_id", ""))
    token = str(payload.get("interaction_token", ""))
    if not application_id.isdigit() or not token or "/" in token:
        return None
    return f"https://discord.com/api/v10/webhooks/{application_id}/{token}"


def _review_followup(webhook: str, content: str) -> None:
    try:
        requests.post(
            webhook,
            json={"content": content, "flags": 64, "allowed_mentions": {"parse": []}},
            timeout=10,
        ).raise_for_status()
    except requests.RequestException:
        log.warning(
            "leadership_review_followup_failed",
            system="discord",
            subsystem="leadership",
        )


@shared_task
def complete_review_click(payload: dict[str, Any]) -> None:
    """HTTP-interactions mode: apply an ``lr:`` click and re-render, without the ORM."""
    webhook = _interaction_webhook(payload)
    if webhook is None:
        return
    try:
        body = ReviewClickBody.model_validate(payload.get("click") or {})
    except ValidationError:
        log.warning(
            "leadership_review_click_invalid", system="discord", subsystem="leadership"
        )
        _review_followup(webhook, SAVE_FAILED)
        return
    result = review_click(body)
    if result is None:
        _review_followup(webhook, SAVE_FAILED)
        return
    if result.message is not None:
        try:
            requests.patch(
                f"{webhook}/messages/@original",
                json={
                    "flags": result.message["flags"],
                    "components": result.message["components"],
                    "allowed_mentions": {"parse": []},
                },
                timeout=10,
            ).raise_for_status()
        except requests.RequestException:
            # Request exceptions include the URL (and interaction credential).
            log.warning(
                "leadership_review_rerender_failed",
                system="discord",
                subsystem="leadership",
            )
    if result.ephemeral:
        _review_followup(webhook, result.ephemeral)
