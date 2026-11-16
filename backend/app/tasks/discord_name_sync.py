"""Celery tasks that sync Discord names through the internal API."""

from celery import shared_task


@shared_task(ignore_result=True)
def sync_org_discord_names(org_id: int) -> None:
    return None
