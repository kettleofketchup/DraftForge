from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

from django.db.models import F, Max, OrderBy, QuerySet
from django.utils import timezone

from events.exceptions import ImmutableFieldError
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from events.models import Event, EventSignup

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
