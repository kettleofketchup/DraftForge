"""One serialization point for every mutation of an event's promotion state.

A local record-send and an external contact import both read "has this
recipient been contacted for this event?" and then write. They run their
whole read-check-write through ``with_event_mutation`` so the check and the
write cannot interleave:

- PostgreSQL: ``SELECT ... FOR UPDATE`` on the event row.
- SQLite: no row locks, so the transaction writes to the event row first,
  taking the database write lock before the suppression read. (Settings
  already open transactions ``IMMEDIATE``; the early write keeps this true
  under any transaction mode.)

On SQLite a lock wait can still time out as ``database is locked``. The
whole operation, a fresh transaction each time, is then retried at most
``MAX_ATTEMPTS`` times in total. Nothing is retried inside an outer atomic
block, where a retry could not roll back cleanly, and no other error is
retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final, TypeVar

from django.db import OperationalError, connection, transaction

from events.models import Event
from telemetry.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS: Final[int] = 3
_LOCK_MESSAGES: Final[tuple[str, ...]] = (
    "database is locked",
    "database table is locked",
)


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    return connection.vendor == "sqlite" and any(
        text in str(exc).lower() for text in _LOCK_MESSAGES
    )


def _backoff(attempt: int) -> None:
    time.sleep(0.05 * attempt)


def lock_event(event_id: int) -> None:
    """Take the event's mutation lock in the current transaction.

    Raises ``Event.DoesNotExist`` for an unknown event.
    """
    if connection.vendor == "sqlite":
        table = connection.ops.quote_name(Event._meta.db_table)
        column = connection.ops.quote_name(Event._meta.pk.column)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {column} = {column} WHERE {column} = %s",  # noqa: S608
                [event_id],
            )
            found = cursor.rowcount
    else:
        found = len(
            Event.objects.nocache()
            .select_for_update()
            .filter(pk=event_id)
            .values_list("pk", flat=True)
        )
    if not found:
        raise Event.DoesNotExist(f"event {event_id} does not exist")


def with_event_mutation(event_id: int, operation: Callable[[], T]) -> T:
    """Run ``operation`` in one transaction holding the event's lock."""
    retryable = not connection.in_atomic_block
    attempt = 1
    while True:
        try:
            with transaction.atomic():
                lock_event(event_id)
                return operation()
        except OperationalError as exc:
            if not (
                retryable and attempt < MAX_ATTEMPTS and _is_sqlite_lock_error(exc)
            ):
                raise
            log.warning(
                "promo_event_mutation_retry",
                system="org",
                subsystem="promotion",
                event_id=event_id,
                attempt=attempt,
            )
            _backoff(attempt)
            attempt += 1
