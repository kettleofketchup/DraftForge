from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from org.mmr_requests.storage import private_media_storage
from org.models import MmrChangeRequest, OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)


def delete_screenshots_on_commit(names: list[str]) -> None:
    names = [n for n in names if n]
    if not names:
        return
    storage = private_media_storage()

    def _delete() -> None:
        for name in names:
            storage.delete(name)

    transaction.on_commit(_delete)


def cancel_pending_for_membership(field: str, membership_id: int) -> int:
    pending = MmrChangeRequest.objects.filter(
        **{field: membership_id}, status=MmrChangeRequest.Status.PENDING
    )
    rows = list(pending.values_list("pk", "screenshot"))
    if not rows:
        return 0
    cancelled = MmrChangeRequest.objects.filter(
        pk__in=[pk for pk, _ in rows], status=MmrChangeRequest.Status.PENDING
    ).update(
        status=MmrChangeRequest.Status.CANCELLED,
        screenshot="",
        updated_at=timezone.now(),
    )
    delete_screenshots_on_commit([name for _, name in rows])
    log.info(
        "mmr_requests_cancelled_membership_deleted",
        system="org",
        subsystem="mmr_requests",
        membership_field=field,
        membership_id=membership_id,
        cancelled=cancelled,
    )
    return cancelled


@receiver(
    post_delete, sender=MmrChangeRequest, dispatch_uid="mmr_request_delete_screenshot"
)
def delete_screenshot_file(
    sender: type[MmrChangeRequest], instance: MmrChangeRequest, **kwargs: Any
) -> None:
    delete_screenshots_on_commit([instance.screenshot.name or ""])


@receiver(pre_delete, sender=OrgUser, dispatch_uid="mmr_request_cancel_on_orguser")
def cancel_on_org_user_delete(
    sender: type[OrgUser], instance: OrgUser, **kwargs: Any
) -> None:
    cancel_pending_for_membership("org_user_id", instance.pk)


@receiver(
    pre_delete,
    sender="league.LeagueUser",
    dispatch_uid="mmr_request_cancel_on_leagueuser",
)
def cancel_on_league_user_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    cancel_pending_for_membership("league_user_id", instance.pk)
