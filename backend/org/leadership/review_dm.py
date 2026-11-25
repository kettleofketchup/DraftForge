"""Leadership review DMs: what to send when review windows open (spec §7.1)."""

from collections.abc import Sequence
from datetime import datetime

from django.conf import settings
from django.db.models import Prefetch

from discordbot.schemas import PlannedMessage
from org.leadership.review_dm_render import (
    MAX_TRAITS_PER_MESSAGE,
    TraitRow,
    render_part,
)
from org.leadership.settings import get_leadership_settings
from org.leadership.traits import materialize_traits
from org.models import OrgUser
from org.models_leadership import EventCaptain
from telemetry.logging import get_logger
from user.display_names import user_display_name

log = get_logger(__name__)


def review_url(event_id: int, snapshot_id: int) -> str:
    return f"{settings.SITE_URL}/events/{event_id}?review={snapshot_id}"


def _discord_id(raw: str | None) -> str | None:
    return raw if raw and raw.isdigit() and len(raw) <= 20 else None


def _chunks(rows: list[TraitRow]) -> list[list[TraitRow]]:
    return [
        rows[i : i + MAX_TRAITS_PER_MESSAGE]
        for i in range(0, len(rows), MAX_TRAITS_PER_MESSAGE)
    ]


def plan(
    event_id: int, snapshot_ids: Sequence[int], *, now: datetime
) -> list[PlannedMessage]:
    snaps = list(
        EventCaptain.objects.nocache()
        .filter(
            pk__in=list(snapshot_ids),
            event_id=event_id,
            voided_at__isnull=True,
            window_closes_at__gt=now,
        )
        .select_related("event", "captain__user")
        .prefetch_related(
            Prefetch(
                "teammates",
                queryset=OrgUser.objects.nocache().select_related("user"),
            )
        )
        .order_by("pk")
    )
    if not snaps:
        return []
    org_id = snaps[0].organization_id
    skip = None if get_leadership_settings(org_id).review_dms_enabled else "disabled"
    active = sorted(
        (t for t in materialize_traits(org_id) if t.active),
        key=lambda t: (t.order, t.pk),
    )
    parts = _chunks(
        [TraitRow(trait_id=t.pk, label=t.label, active=True) for t in active]
    )
    messages: list[PlannedMessage] = []
    for snap in snaps:
        captain_name = user_display_name(snap.captain.user)
        mates = sorted(
            (m for m in snap.teammates.all() if m.pk != snap.captain_id),
            key=lambda m: m.pk,
        )
        for mate in mates:
            for index, rows in enumerate(parts, start=1):
                messages.append(
                    PlannedMessage(
                        snapshot_id=snap.pk,
                        part=index,
                        parts=len(parts),
                        trait_ids=[r.trait_id for r in rows],
                        rater_org_user_id=mate.pk,
                        recipient_user_id=mate.user_id,
                        organization_id=org_id,
                        discord_user_id=_discord_id(mate.user.discordId),
                        skip=skip,
                        payload=render_part(
                            captain_name=captain_name,
                            event_name=snap.event.name,
                            close_at=snap.window_closes_at,
                            part=index,
                            parts=len(parts),
                            traits=rows,
                            scores={},
                            snapshot_id=snap.pk,
                            site_url=review_url(snap.event_id, snap.pk),
                            state="progress",
                        ),
                    )
                )
    log.info(
        "leadership_review_dms_planned",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=event_id,
        snapshots=len(snaps),
        messages=len(messages),
        disabled=skip is not None,
    )
    return messages
