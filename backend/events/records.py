from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db.models import Q
from pydantic import ValidationError

from events import ledger
from events.constants import SignupStatus
from events.ledger import LedgerEvent, RecordsWindow, resolve_ledger_events
from events.models import SignupLedgerEntry
from events.schemas import SignupSnapshot
from telemetry.logging import get_logger

__all__ = [
    "RECORD_COLUMNS",
    "RecordsFilter",
    "SignupRecord",
    "TooManyRecords",
    "build_signup_records",
    "flatten_record",
    "guard_csv_cell",
    "record_to_json",
]

log = get_logger(__name__)

WITHDRAWN_STATUSES: frozenset[str] = frozenset(
    {SignupStatus.CANCELLED, SignupStatus.DROPPED}
)
CSV_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")
ROW_ITERATOR_CHUNK = 2000

RECORD_COLUMNS: tuple[str, ...] = (
    "event_id",
    "event_name",
    "scheduled_at",
    "event_state",
    "series_id",
    "user_id",
    "discord_id",
    "original_signed_up_at",
    "original_commitment",
    "original_rsvp_class",
    "original_means",
    "final_status",
    "final_commitment",
    "final_rsvp_class",
    "final_signed_up_at",
    "final_line_seq",
    "withdrawn_at",
    "change_count",
    "last_changed_at",
)

_ORIGINAL_KEYS = ("signed_up_at", "commitment", "rsvp_class", "means")
_FINAL_KEYS = ("status", "commitment", "rsvp_class", "signed_up_at", "line_seq")
_ROW_FIELDS = (
    "pk",
    "event_id",
    "subject_user_id",
    "subject_user__discordId",
    "subject_snapshot",
    "means",
    "after",
    "occurred_at",
)

type SubjectKey = tuple[str, object]
type LedgerRow = tuple[int, int, int | None, str | None, Any, str, Any, datetime]


class TooManyRecords(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RecordsFilter:
    window: RecordsWindow
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class SignupRecord:
    event_id: int
    event_name: str
    scheduled_at: datetime | None
    event_state: str
    series_id: int | None
    user_id: int | None
    discord_id: str | None
    original: dict[str, Any] | None
    final: dict[str, Any] | None
    withdrawn_at: datetime | None
    change_count: int
    last_changed_at: datetime


def _chunks(ids: list[int]) -> Iterator[list[int]]:
    size = ledger.RESOLVE_CHUNK_SIZE
    for start in range(0, len(ids), size):
        yield ids[start : start + size]


def _snapshot_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _snapshot_user_id(snap: dict[str, Any]) -> int | None:
    value = snap.get("user_id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _subject_key(row: LedgerRow) -> SubjectKey:
    subject_user_id = row[2]
    if subject_user_id is not None:
        return ("user", subject_user_id)
    return ("snap", _snapshot_user_id(_snapshot_dict(row[4])))


def _discord_id(row: LedgerRow) -> str | None:
    if row[2] is not None:
        value: object = row[3]
    else:
        value = _snapshot_dict(row[4]).get("discord_id")
    return None if value is None or value == "" else str(value)


class _Reducer:
    def __init__(self) -> None:
        self.invalid = 0

    def _parse(self, after: object) -> SignupSnapshot | None:
        if after is None:
            return None
        try:
            return SignupSnapshot.model_validate(after)
        except ValidationError:
            self.invalid += 1
            return None

    def reduce(self, event: LedgerEvent, rows: list[LedgerRow]) -> SignupRecord:
        rows.sort(key=lambda r: (r[7], r[0]))
        valid: list[tuple[int, LedgerRow, SignupSnapshot]] = []
        for index, row in enumerate(rows):
            snap = self._parse(row[6])
            if snap is not None:
                valid.append((index, row, snap))

        original: dict[str, Any] | None = None
        final: dict[str, Any] | None = None
        withdrawn_at: datetime | None = None
        change_count = len(rows)
        if valid:
            first_index, first_row, first = valid[0]
            original = {
                "signed_up_at": first.signed_up_at or first_row[7],
                "commitment": first.commitment,
                "rsvp_class": first.rsvp_class,
                "means": first_row[5],
            }
            last = valid[-1][2]
            final = {
                "status": last.status,
                "commitment": last.commitment,
                "rsvp_class": last.rsvp_class,
                "signed_up_at": last.signed_up_at,
                "line_seq": last.line_seq,
            }
            change_count = len(rows) - first_index - 1
            for _, row, snap in reversed(valid):
                if snap.status not in WITHDRAWN_STATUSES:
                    break
                withdrawn_at = row[7]

        subject = rows[-1]
        user_id = subject[2]
        if user_id is None:
            user_id = _snapshot_user_id(_snapshot_dict(subject[4]))
        return SignupRecord(
            event_id=event.event_id,
            event_name=event.name,
            scheduled_at=event.scheduled_at,
            event_state=event.state,
            series_id=event.series_id,
            user_id=user_id,
            discord_id=_discord_id(subject),
            original=original,
            final=final,
            withdrawn_at=withdrawn_at,
            change_count=change_count,
            last_changed_at=rows[-1][7],
        )


def _rows(organization_id: int, ids: list[int], user_id: int | None) -> Any:
    qs = (
        SignupLedgerEntry.objects.nocache()
        .filter(organization_id=organization_id, event_id__in=ids)
        .exclude(subject_snapshot={})
    )
    if user_id is not None:
        qs = qs.filter(
            Q(subject_user_id=user_id)
            | Q(subject_user__isnull=True, subject_snapshot__user_id=user_id)
        )
    return (
        qs.order_by("event_id", "subject_user_id", "occurred_at", "pk")
        .values_list(*_ROW_FIELDS)
        .iterator(chunk_size=ROW_ITERATOR_CHUNK)
    )


def _sort_key(record: SignupRecord) -> tuple[bool, datetime, int, bool, int]:
    return (
        record.scheduled_at is None,
        record.scheduled_at or datetime.min.replace(tzinfo=UTC),
        record.event_id,
        record.user_id is None,
        record.user_id or 0,
    )


def build_signup_records(
    organization_id: int, flt: RecordsFilter, *, max_rows: int | None = None
) -> list[SignupRecord]:
    cap = settings.SIGNUP_RECORDS_MAX_ROWS if max_rows is None else max_rows
    events = resolve_ledger_events(organization_id, window=flt.window)
    reducer = _Reducer()
    records: list[SignupRecord] = []
    for chunk in _chunks(sorted(events)):
        groups: dict[tuple[int, SubjectKey], list[LedgerRow]] = {}
        for row in _rows(organization_id, chunk, flt.user_id):
            groups.setdefault((row[1], _subject_key(row)), []).append(row)
            if len(records) + len(groups) > cap:
                raise TooManyRecords
        for (event_id, _), rows in groups.items():
            records.append(reducer.reduce(events[event_id], rows))
    if reducer.invalid:
        log.warning(
            "signup_records_snapshot_invalid",
            system="events",
            subsystem="ledger",
            organization_id=organization_id,
            count=reducer.invalid,
        )
    records.sort(key=_sort_key)
    return records


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _part(part: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if part is None:
        return None
    return {
        key: _iso(part[key]) if isinstance(part[key], datetime) else part[key]
        for key in keys
    }


def record_to_json(r: SignupRecord) -> dict[str, Any]:
    return {
        "event_id": r.event_id,
        "event_name": r.event_name,
        "scheduled_at": _iso(r.scheduled_at),
        "event_state": r.event_state,
        "series_id": r.series_id,
        "user_id": r.user_id,
        "discord_id": r.discord_id,
        "original": _part(r.original, _ORIGINAL_KEYS),
        "final": _part(r.final, _FINAL_KEYS),
        "withdrawn_at": _iso(r.withdrawn_at),
        "change_count": r.change_count,
        "last_changed_at": _iso(r.last_changed_at),
    }


def flatten_record(r: SignupRecord) -> list[str | int | None]:
    data = record_to_json(r)
    original = data["original"] or {}
    final = data["final"] or {}
    return [
        data["event_id"],
        data["event_name"],
        data["scheduled_at"],
        data["event_state"],
        data["series_id"],
        data["user_id"],
        data["discord_id"],
        *(original.get(key) for key in _ORIGINAL_KEYS),
        *(final.get(key) for key in _FINAL_KEYS),
        data["withdrawn_at"],
        data["change_count"],
        data["last_changed_at"],
    ]


def guard_csv_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value
