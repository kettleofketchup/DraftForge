from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from org.mmr_requests.signals import delete_screenshots_on_commit
from org.models import MmrChangeRequest
from telemetry.logging import get_logger

log = get_logger(__name__)

BATCH_SIZE = 500
PURGEABLE = (
    MmrChangeRequest.Status.APPROVED,
    MmrChangeRequest.Status.REJECTED,
    MmrChangeRequest.Status.SUPERSEDED,
)


@dataclass(frozen=True, slots=True)
class PurgeResult:
    purged: int
    batches: int
    retention_days: int


def purge_expired_screenshots(
    *, retention_days: int | None = None, batch_size: int = BATCH_SIZE
) -> PurgeResult:
    days = (
        settings.MMR_SCREENSHOT_RETENTION_DAYS
        if retention_days is None
        else retention_days
    )
    now = timezone.now()
    expired = MmrChangeRequest.objects.filter(
        status__in=PURGEABLE, reviewed_at__lt=now - timedelta(days=days)
    ).exclude(screenshot="")
    purged = 0
    batches = 0
    while True:
        rows = list(expired.order_by("pk").values_list("pk", "screenshot")[:batch_size])
        if not rows:
            break
        with transaction.atomic():
            updated = expired.filter(pk__in=[pk for pk, _ in rows]).update(
                screenshot="",
                screenshot_content_type="",
                screenshot_purged_at=now,
                updated_at=now,
            )
            delete_screenshots_on_commit([name for _, name in rows])
        if not updated:
            break
        purged += updated
        batches += 1
    log.info(
        "mmr_screenshots_purged",
        system="org",
        subsystem="mmr_requests",
        purged=purged,
        batches=batches,
        retention_days=days,
    )
    return PurgeResult(purged=purged, batches=batches, retention_days=days)
