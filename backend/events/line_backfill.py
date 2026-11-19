"""Stamp line position and add ``backfilled`` ledger entries for existing signups.

Shared by migration 0027 and the ``backfill_signup_line`` command. Models are
resolved from the registry passed in, never imported, and every read and write
goes through ``_base_manager`` so the live ``first_*`` guards do not apply. If a
later schema change breaks this module, freeze its current body into 0027.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from django.apps.registry import Apps
from django.conf import settings
from django.db.models import Model
from django.utils import timezone

from events.constants import (
    ActorRole,
    Commitment,
    RsvpClass,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.schemas import SignupSnapshot
from telemetry.logging import get_logger

log = get_logger(__name__)

BATCH_SIZE = 500
DECLINE_ONLY_WINDOW = timedelta(seconds=1)
STAMPED_FIELDS: list[str] = [
    "line_seq",
    "signed_up_at",
    "commitment",
    "rsvp_class",
    "first_signed_up_at",
    "first_commitment",
    "first_rsvp_class",
]
EVENT_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "scheduled_at",
    "ends_at",
    "state",
    "organization_id",
    "event_repeater_id",
    "tournament_id",
)


@dataclass(frozen=True)
class BackfillResult:
    events: int
    signups_stamped: int
    ledger_entries: int
    rerun: bool


def _created_key(signup: Model) -> tuple[datetime, int]:
    return (signup.created_at, signup.pk)


def _waitlist_key(signup: Model) -> tuple[bool, int, datetime, int]:
    position = signup.waitlist_position
    return (position is None, position or 0, signup.created_at, signup.pk)


def _declined_without_signing_up(signup: Model) -> bool:
    return (
        signup.status == SignupStatus.CANCELLED
        and signup.updated_at - signup.created_at < DECLINE_ONLY_WINDOW
    )


def _stamp(signup: Model, seq: int, signed_up_at: datetime) -> None:
    commitment = (
        Commitment.MAYBE if signup.status == SignupStatus.TENTATIVE else Commitment.MAIN
    )
    signup.line_seq = seq
    signup.signed_up_at = signed_up_at
    signup.commitment = commitment
    signup.rsvp_class = RsvpClass.STANDARD
    if _declined_without_signing_up(signup):
        signup.first_signed_up_at = None
        signup.first_commitment = None
        signup.first_rsvp_class = None
        return
    signup.first_signed_up_at = signup.created_at
    signup.first_commitment = commitment
    signup.first_rsvp_class = RsvpClass.STANDARD


def _stamp_first_run(rows: list[Model]) -> None:
    slots = sorted(rows, key=_created_key)
    waitlisted_slots = [
        i for i, s in enumerate(slots) if s.status == SignupStatus.WAITLISTED
    ]
    placed = list(slots)
    waitlist_order = sorted((slots[i] for i in waitlisted_slots), key=_waitlist_key)
    for i, signup in zip(waitlisted_slots, waitlist_order):
        placed[i] = signup
    for i, signup in enumerate(placed):
        _stamp(signup, i + 1, slots[i].created_at)


def _stamp_rerun(rows: list[Model]) -> list[Model]:
    current = max((s.line_seq for s in rows if s.line_seq is not None), default=0)
    unstamped = sorted((s for s in rows if s.line_seq is None), key=_created_key)
    for offset, signup in enumerate(unstamped, start=1):
        _stamp(signup, current + offset, signup.created_at)
    return unstamped


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _event_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "name": event["name"],
        "scheduled_at": _iso(event["scheduled_at"]),
        "ends_at": _iso(event["ends_at"]),
        "state": event["state"],
        "organization_id": event["organization_id"],
        "series_id": event["event_repeater_id"],
        "tournament_id": event["tournament_id"],
    }


def _signup_snapshot(signup: Model) -> dict[str, Any]:
    return SignupSnapshot(
        status=signup.status,
        commitment=signup.commitment,
        rsvp_class=signup.rsvp_class,
        signed_up_at=signup.signed_up_at,
        line_seq=signup.line_seq,
        waitlist_position=signup.waitlist_position,
        event_team_id=signup.event_team_id,
    ).model_dump(mode="json")


def _user_snapshots(apps: Apps, user_ids: set[int]) -> dict[int, dict[str, Any]]:
    User = apps.get_model(settings.AUTH_USER_MODEL)
    BaseUserProfile = apps.get_model("user", "BaseUserProfile")
    nicknames = dict(
        BaseUserProfile._base_manager.nocache()
        .filter(user_id__in=user_ids)
        .values_list("user_id", "nickname")
    )
    return {
        row["pk"]: {
            "user_id": row["pk"],
            "username": row["username"],
            "nickname": nicknames.get(row["pk"]),
            "discord_id": row["discordId"],
        }
        for row in User._base_manager.nocache()
        .filter(pk__in=user_ids)
        .values("pk", "username", "discordId")
    }


def backfill_signup_line(apps: Apps) -> BackfillResult:
    Event = apps.get_model("events", "Event")
    EventSignup = apps.get_model("events", "EventSignup")
    SignupLedgerEntry = apps.get_model("events", "SignupLedgerEntry")

    events = {e["id"]: e for e in Event._base_manager.nocache().values(*EVENT_FIELDS)}
    by_event: dict[int, list[Model]] = defaultdict(list)
    for signup in EventSignup._base_manager.nocache().order_by("event_id", "pk"):
        by_event[signup.event_id].append(signup)

    rerun = False
    stamped: list[Model] = []
    for rows in by_event.values():
        if any(s.line_seq is not None for s in rows):
            rerun = True
            stamped.extend(_stamp_rerun(rows))
        else:
            _stamp_first_run(rows)
            stamped.extend(rows)
    EventSignup._base_manager.bulk_update(
        stamped, STAMPED_FIELDS, batch_size=BATCH_SIZE
    )

    backfilled = set(
        SignupLedgerEntry._base_manager.nocache()
        .filter(action=SignupAction.BACKFILLED, signup_id__isnull=False)
        .values_list("signup_id", flat=True)
    )
    missing = [s for s in stamped if s.pk not in backfilled]
    users = _user_snapshots(apps, {s.user_id for s in missing})
    correlation_id = f"backfill-{uuid4().hex[:12]}"
    occurred_at = timezone.now()
    entries = [
        SignupLedgerEntry(
            event_id=s.event_id,
            organization_id=events[s.event_id]["organization_id"],
            signup_id=s.pk,
            event_snapshot=_event_snapshot(events[s.event_id]),
            subject_user_id=s.user_id,
            subject_snapshot=users.get(s.user_id),
            actor_user=None,
            actor_snapshot=None,
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            on_behalf=False,
            action=SignupAction.BACKFILLED,
            before=None,
            after=_signup_snapshot(s),
            correlation_id=correlation_id,
            occurred_at=occurred_at,
        )
        for s in missing
    ]
    SignupLedgerEntry._base_manager.bulk_create(entries, batch_size=BATCH_SIZE)

    result = BackfillResult(
        events=len(events),
        signups_stamped=len(stamped),
        ledger_entries=len(entries),
        rerun=rerun,
    )
    log.info(
        "signup_line_backfilled",
        system="events",
        subsystem="migration",
        events=result.events,
        signups_stamped=result.signups_stamped,
        ledger_entries=result.ledger_entries,
        rerun=result.rerun,
    )
    return result


def unbackfill_signup_line(apps: Apps) -> None:
    """Reverse of 0027 only; never call it on the live registry."""
    EventSignup = apps.get_model("events", "EventSignup")
    SignupLedgerEntry = apps.get_model("events", "SignupLedgerEntry")
    SignupLedgerEntry._base_manager.filter(action=SignupAction.BACKFILLED).delete()
    EventSignup._base_manager.update(line_seq=None)
