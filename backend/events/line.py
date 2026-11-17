from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

from django.db import transaction
from django.db.models import F, Max, OrderBy, QuerySet
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from events.exceptions import ImmutableFieldError
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from events.models import Event, EventSignup
    from events.schemas import SignupSnapshot

log = get_logger(__name__)

FIRST_FIELDS: tuple[str, ...] = (
    "first_signed_up_at",
    "first_commitment",
    "first_rsvp_class",
)


def next_line_seq(event: Event) -> int:
    current = event.signups.nocache().aggregate(m=Max("line_seq"))["m"]
    return (current or 0) + 1


def stamp(event: Event, *, at: datetime | None = None) -> dict[str, Any]:
    return {"line_seq": next_line_seq(event), "signed_up_at": at or timezone.now()}


def line_order_by() -> list[OrderBy]:
    return [F("line_seq").asc(nulls_last=True), F("pk").asc()]


RESTORED_FIELDS: tuple[str, ...] = (
    "status",
    "commitment",
    "rsvp_class",
    "signed_up_at",
    "line_seq",
    "waitlist_position",
)


def restore_place(signup: EventSignup, snap: SignupSnapshot) -> None:
    changed = [
        name for name in RESTORED_FIELDS if getattr(signup, name) != getattr(snap, name)
    ]
    if not changed:
        return
    for name in changed:
        setattr(signup, name, getattr(snap, name))
    signup.save(update_fields=[*changed, "updated_at"])
    invalidate_after_commit(signup.event)
    signup_id, event_id, line_seq = signup.pk, signup.event_id, signup.line_seq
    transaction.on_commit(
        lambda: log.info(
            "signup_line_place_restored",
            system="events",
            subsystem="line",
            signup_id=signup_id,
            event_id=event_id,
            line_seq=line_seq,
        )
    )


@transaction.atomic
def swap_places(a: EventSignup, b: EventSignup) -> None:
    if a.event_id != b.event_id:
        raise ValueError(
            f"Cannot swap signups across events: {a.event_id} != {b.event_id}"
        )
    a.line_seq, b.line_seq = b.line_seq, a.line_seq
    a.signed_up_at, b.signed_up_at = b.signed_up_at, a.signed_up_at
    for signup in (a, b):
        signup.save(update_fields=["line_seq", "signed_up_at", "updated_at"])
    invalidate_after_commit(a.event)
    event_id = a.event_id
    signup_ids = [a.pk, b.pk]
    line_seqs = [a.line_seq, b.line_seq]
    transaction.on_commit(
        lambda: log.info(
            "signup_line_places_swapped",
            system="events",
            subsystem="line",
            event_id=event_id,
            signup_ids=signup_ids,
            line_seqs=line_seqs,
        )
    )


def same_gate_distance(a: EventSignup, b: EventSignup) -> bool:
    return True


class EventSignupQuerySet(QuerySet):
    def in_line_order(self) -> Self:
        return self.order_by(*line_order_by())

    def update(self, **kwargs: Any) -> int:
        _block_first_fields(kwargs)
        return super().update(**kwargs)

    def bulk_update(
        self,
        objs: Iterable[EventSignup],
        fields: Iterable[str],
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fields = list(fields)
        _block_first_fields(fields)
        return super().bulk_update(objs, fields, *args, **kwargs)


def _block_first_fields(names: Iterable[str]) -> None:
    blocked = [f for f in FIRST_FIELDS if f in names]
    if blocked:
        log.warning(
            "signup_first_fields_mutation_blocked",
            system="events",
            subsystem="line",
            signup_id=None,
            fields=blocked,
        )
        raise ImmutableFieldError(f"EventSignup fields are immutable: {blocked}")
