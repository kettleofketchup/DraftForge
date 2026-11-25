"""Celery tasks for leadership. Workers have no ORM: data comes over the internal API."""

from collections import Counter

from celery import Task, shared_task

from discordbot.dm import V2_FLAG, DMRequest, send_dm
from discordbot.dm_keys import leadership_review_key
from discordbot.internal_client.leadership_actions import plan_review_dms
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import PlannedMessage
from telemetry.logging import get_logger

log = get_logger(__name__)

PLAN_RETRY_DELAY_S = 60
PLAN_MAX_RETRIES = 5


def _request(msg: PlannedMessage) -> DMRequest:
    return DMRequest(
        kind=DMKind.LEADERSHIP_REVIEW,
        idempotency_key=leadership_review_key(
            snapshot_id=msg.snapshot_id,
            rater_org_user_id=msg.rater_org_user_id,
            part=msg.part,
        ),
        discord_user_id=msg.discord_user_id,
        recipient_user_id=msg.recipient_user_id,
        organization_id=msg.organization_id,
        subject=(DMSubject.CAPTAIN_SNAPSHOT, msg.snapshot_id),
        context={
            "snapshot_id": msg.snapshot_id,
            "part": msg.part,
            "parts": msg.parts,
            "trait_ids": list(msg.trait_ids),
        },
        components=msg.payload["components"],
        flags=V2_FLAG,
        skip_status=DMStatus.SKIPPED_DISABLED if msg.skip == "disabled" else None,
    )


@shared_task(
    bind=True,
    acks_late=True,
    max_retries=PLAN_MAX_RETRIES,
    default_retry_delay=PLAN_RETRY_DELAY_S,
)
def send_leadership_review_dms(
    self: Task, event_id: int, snapshot_ids: list[int]
) -> dict[str, int]:
    messages = plan_review_dms(event_id, snapshot_ids)
    if messages is None:
        raise self.retry()
    counts: Counter[str] = Counter(planned=len(messages))
    for msg in messages:
        outcome = send_dm(_request(msg))
        counts[str(outcome.status)] += 1
        if outcome.auth_rejected:
            counts["auth_rejected"] += 1
            break
    log.info(
        "leadership_review_dms_sent",
        system="org",
        subsystem="leadership",
        event_id=event_id,
        snapshots=len(snapshot_ids),
        **counts,
    )
    return dict(counts)
