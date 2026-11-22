from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.dispatch import Signal

from telemetry.logging import get_logger

__all__ = [
    "ReadyCheckChange",
    "ready_check_chase_due",
    "ready_check_closed",
    "ready_check_escalated",
    "ready_check_held",
    "ready_check_member_confirmed",
    "ready_check_member_dropped",
    "ready_check_opened",
    "ready_check_went_non_binding",
    "send_on_commit",
]

log = get_logger(__name__)


@dataclass(frozen=True)
class ReadyCheckChange:
    event_id: int
    ready_check_id: int
    phase: str
    outcome: str
    user_ids: tuple[int, ...] = ()
    actor_user_id: int | None = None


ready_check_opened: Signal = Signal()
ready_check_escalated: Signal = Signal()
ready_check_chase_due: Signal = Signal()
ready_check_member_confirmed: Signal = Signal()
ready_check_held: Signal = Signal()
ready_check_went_non_binding: Signal = Signal()
ready_check_closed: Signal = Signal()
ready_check_member_dropped: Signal = Signal()


def _receiver_name(receiver: Any) -> str:
    return getattr(receiver, "__qualname__", None) or repr(receiver)


def send_on_commit(signal: Signal, change: ReadyCheckChange) -> None:
    def _send() -> None:
        results = signal.send_robust(sender=ReadyCheckChange, change=change)
        for receiver, result in results:
            if isinstance(result, Exception):
                log.warning(
                    "ready_check_signal_receiver_failed",
                    system="events",
                    subsystem="ready_check",
                    event_id=change.event_id,
                    ready_check_id=change.ready_check_id,
                    phase=change.phase,
                    outcome=change.outcome,
                    receiver=_receiver_name(receiver),
                    error=repr(result),
                )

    transaction.on_commit(_send)
