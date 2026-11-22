from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from events.capacity import seat_holding_statuses
from events.constants import SignupAction
from events.ledger import SignupActor, record_signup_change, snapshot
from events.models import EventSignup, SignupLedgerEntry
from events.services import _promote_from_waitlist

if TYPE_CHECKING:
    from app.models import CustomUser

__all__ = ["merge_user_signups"]


@transaction.atomic
def merge_user_signups(
    drop: CustomUser, keep: CustomUser, *, actor: SignupActor
) -> int:
    drop_rows = list(
        EventSignup.objects.nocache()
        .filter(user=drop)
        .select_related("event", "user__base_profile")
    )
    keep_rows = {
        row.event_id: row
        for row in EventSignup.objects.nocache()
        .filter(user=keep, event_id__in=[row.event_id for row in drop_rows])
        .select_related("user__base_profile")
    }
    origin = {"from_user_id": drop.pk}
    written = 0
    for row in drop_rows:
        event = row.event
        kept = keep_rows.get(row.event_id)
        freed_seat = False
        seats = seat_holding_statuses(event)
        if kept is None:
            before = snapshot(row, extra=origin)
        else:
            # A seat beats a row that holds none, whichever account it is on.
            seated_drop = row.status in seats and kept.status not in seats
            discarded = kept if seated_drop else row
            before = snapshot(
                discarded,
                extra={
                    **origin,
                    "discarded_signup_id": discarded.pk,
                    "discarded_duplicate": True,
                },
            )
            freed_seat = discarded.status in seats
            discarded.delete()
            if seated_drop:
                kept = None
        if kept is None:
            row.user = keep
            row.save(update_fields=["user", "updated_at"])
            signup, after = row, snapshot(row, extra=origin)
        else:
            signup, after = kept, snapshot(kept)
        entry = record_signup_change(
            event=event,
            subject=keep,
            actor=actor,
            action=SignupAction.ACCOUNT_MERGED,
            signup=signup,
            before=before,
            after=after,
        )
        if freed_seat:
            _promote_from_waitlist(event, cause=entry)
        written += 1
    SignupLedgerEntry.objects.filter(subject_user=drop).update(subject_user=keep)
    SignupLedgerEntry.objects.filter(actor_user=drop).update(actor_user=keep)
    return written
