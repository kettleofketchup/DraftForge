from celery import shared_task

from app.internal_client import purge_mmr_screenshots
from telemetry.logging import get_logger

log = get_logger(__name__)


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def purge_expired_mmr_screenshots() -> None:
    if purge_mmr_screenshots() is None:
        log.warning(
            "mmr_screenshot_purge_failed", system="org", subsystem="mmr_requests"
        )
