# backend/discordbot/tasks.py
"""Celery tasks for Discord bot scheduled operations."""

from datetime import datetime, timedelta

from celery import shared_task

from telemetry.logging import get_logger

log = get_logger(__name__)


@shared_task
def check_scheduled_events():
    """
    Check for and post scheduled events that are due.
    Runs every 60 seconds via Celery beat.

    All reads via internal HTTP API. Embeds built from template data.
    """
    from app.internal_client import get_due_scheduled_events, update_scheduled_event
    from discordbot.utils import sync_add_reactions, sync_send_embed

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

        # Update via internal API
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
def sweep_stale_discord_leases():
    """Reap stuck DiscordMessageLog rows so the partial unique constraint
    doesn't permanently brick reminders.

    Two recovery cases:
    - NULL pending leases >5 min old: worker crashed between claim and
      finalize. Delete so the next poll can re-claim.
    - False failed rows >1 hour old: Discord transient 5xx, rate-limit, or
      auth issue has likely passed. Delete so the next poll can retry.
      Admins should investigate via the original failed log row before it
      ages out.

    The 60-second beat cadence keeps total worker-crash recovery latency
    below ~1.5 min (5min sweep threshold + 30s next poll).

    Both deletes happen server-side via the internal endpoint — the
    worker stays ORM-free.
    """
    from app.internal_client import sweep_discord_leases

    result = sweep_discord_leases(
        pending_threshold_minutes=5, failed_threshold_hours=1
    )
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
