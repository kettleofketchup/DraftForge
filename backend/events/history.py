"""Keyset cursor and queryset for the staff signup history (#497)."""

import binascii
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.db.models import Q, QuerySet
from pydantic import ValidationError

from events.models import Event, SignupLedgerEntry
from events.schemas import SignupSnapshot
from telemetry.logging import get_logger

log = get_logger(__name__)

HISTORY_PAGE_SIZE: int = 50
HISTORY_MAX_PAGE_SIZE: int = 100
MAX_DB_INT: int = 2**63 - 1

HISTORY_EXTRA_KEYS: frozenset[str] = frozenset(
    {
        "staff_power",
        "mmr_override",
        "game_type",
        "from_user_id",
        "discarded_duplicate",
        "discarded_signup_id",
        "event_id",
    }
)

CURSOR_MESSAGE = "Invalid cursor."


@dataclass(frozen=True)
class HistoryCursor:
    """Keyset position in history order (occurred_at desc, pk desc)."""

    occurred_at: datetime
    pk: int

    @property
    def token(self) -> str:
        raw = f"{self.occurred_at.astimezone(UTC).isoformat()}|{self.pk}"
        return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_history_cursor(token: str) -> HistoryCursor:
    if not token:
        raise ValueError(CURSOR_MESSAGE)
    try:
        raw = urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        occurred_text, pk_text = raw.split("|")
        occurred_at = datetime.fromisoformat(occurred_text)
        pk = int(pk_text)
        if occurred_at.tzinfo is None or not 1 <= pk <= MAX_DB_INT:
            raise ValueError(CURSOR_MESSAGE)
        occurred_at = occurred_at.astimezone(UTC)
    except (binascii.Error, UnicodeDecodeError, ValueError, OverflowError) as exc:
        raise ValueError(CURSOR_MESSAGE) from exc
    return HistoryCursor(occurred_at, pk)


def history_after_q(cursor: HistoryCursor) -> Q:
    """Rows strictly after ``cursor`` in history order."""
    return Q(occurred_at__lt=cursor.occurred_at) | Q(
        occurred_at=cursor.occurred_at, pk__lt=cursor.pk
    )


def signup_history_queryset(
    event: Event, *, user_id: int | None = None, action: str | None = None
) -> QuerySet[SignupLedgerEntry]:
    qs = SignupLedgerEntry.objects.filter(event_id=event.pk)
    if user_id is not None:
        qs = qs.filter(subject_user_id=user_id)
    if action is not None:
        qs = qs.filter(action=action)
    return qs.select_related(
        "subject_user__base_profile", "actor_user__base_profile"
    ).order_by("-occurred_at", "-pk")


def reduce_history_snapshot(value: Any, *, entry_id: int) -> dict[str, Any] | None:
    """Validated snapshot with ``extra`` limited to ``HISTORY_EXTRA_KEYS``."""
    if value is None:
        return None
    try:
        if not isinstance(value, dict):
            raise TypeError(type(value).__name__)
        data = SignupSnapshot.model_validate(value).model_dump(mode="json")
    except (ValidationError, TypeError):
        log.warning(
            "signup_history_snapshot_invalid",
            system="events",
            subsystem="ledger",
            entry_id=entry_id,
        )
        return None
    data["extra"] = {k: v for k, v in data["extra"].items() if k in HISTORY_EXTRA_KEYS}
    return data
