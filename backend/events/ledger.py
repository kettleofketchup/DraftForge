from __future__ import annotations

import time
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, OuterRef, QuerySet, Subquery
from django.http import HttpRequest
from django.utils import timezone as tz
from structlog.contextvars import get_contextvars

from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import (
    PURGE_BATCH_SIZE,
    Event,
    EventSignup,
    ReadyCheck,
    SignupLedgerEntry,
)
from events.permissions import has_event_staff_access
from events.schemas import SignupSnapshot
from org.models import OrgSettings
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser

__all__ = [
    "LEDGER_STATE_DELETED",
    "LEDGER_STATE_MOVED",
    "PLACEMENT_ACTIONS",
    "RESOLVE_CHUNK_SIZE",
    "LedgerEvent",
    "RecordsWindow",
    "SignupPurgeResult",
    "ActorRole",
    "SignupAction",
    "SignupActor",
    "SignupMeans",
    "current_interaction_id",
    "event_snapshot",
    "parse_snapshot_time",
    "purge_expired",
    "record_ready_check_transition",
    "record_signup_change",
    "resolve_ledger_events",
    "snapshot",
    "user_snapshot",
]

log = get_logger(__name__)

PLACEMENT_ACTIONS: frozenset[str] = frozenset()

CORRELATION_ID_MAX_LENGTH = 64


def current_interaction_id() -> str:
    return str(get_contextvars().get("interaction_id") or "")[
        :CORRELATION_ID_MAX_LENGTH
    ]


@dataclass(frozen=True)
class SignupActor:
    user: CustomUser | None
    role: ActorRole
    means: SignupMeans
    correlation_id: str = ""
    staff_power: bool = False

    @classmethod
    def system(cls, *, correlation_id: str = "") -> SignupActor:
        return cls(
            user=None,
            role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            correlation_id=correlation_id,
        )

    @classmethod
    def voice(cls, user: CustomUser, *, correlation_id: str = "") -> SignupActor:
        return cls(
            user=user,
            role=ActorRole.MEMBER,
            means=SignupMeans.DISCORD_VOICE,
            correlation_id=correlation_id,
        )

    @classmethod
    def from_request(
        cls, request: HttpRequest, *, role: ActorRole = ActorRole.MEMBER
    ) -> SignupActor:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            user = None
        return cls(user=user, role=role, means=SignupMeans.WEB)

    @classmethod
    def discord(
        cls,
        user: CustomUser,
        *,
        means: SignupMeans = SignupMeans.DISCORD_BUTTON,
        role: ActorRole = ActorRole.MEMBER,
        correlation_id: str | None = None,
    ) -> SignupActor:
        return cls(
            user=user,
            role=role,
            means=means,
            correlation_id=(
                current_interaction_id() if correlation_id is None else correlation_id
            ),
        )

    @classmethod
    def for_request_on(
        cls,
        request: HttpRequest,
        subject: CustomUser,
        event: Event,
        *,
        staff_only: bool = False,
    ) -> SignupActor:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return cls(user=None, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        is_self = user.pk == subject.pk
        is_staff = has_event_staff_access(user, event)
        return cls(
            user=user,
            role=ActorRole.STAFF if is_staff and not is_self else ActorRole.MEMBER,
            means=SignupMeans.WEB,
            staff_power=staff_only and is_staff and is_self,
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def snapshot(
    signup: EventSignup, *, extra: dict[str, Any] | None = None
) -> SignupSnapshot:
    return SignupSnapshot(
        status=signup.status,
        commitment=signup.commitment,
        rsvp_class=signup.rsvp_class,
        signed_up_at=signup.signed_up_at,
        line_seq=signup.line_seq,
        waitlist_position=signup.waitlist_position,
        event_team_id=signup.event_team_id,
        extra=dict(extra) if extra else {},
    )


def event_snapshot(event: Event) -> dict[str, Any]:
    return {
        "id": event.pk,
        "name": event.name,
        "scheduled_at": _iso(event.scheduled_at),
        "ends_at": _iso(event.ends_at),
        "state": event.state,
        "organization_id": event.organization_id,
        "series_id": event.event_repeater_id,
        "tournament_id": event.tournament_id,
    }


def user_snapshot(user: CustomUser | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "user_id": user.pk,
        "username": user.username,
        "nickname": user.nickname,
        "discord_id": user.discordId,
    }


def _dump(value: SignupSnapshot | None) -> dict[str, Any] | None:
    return value.model_dump(mode="json") if value is not None else None


def record_signup_change(
    *,
    event: Event,
    subject: CustomUser,
    actor: SignupActor,
    action: SignupAction,
    signup: EventSignup | None = None,
    before: SignupSnapshot | None = None,
    after: SignupSnapshot | None = None,
    reason: str = "",
    rules_overridden: Sequence[str] = (),
    caused_by: SignupLedgerEntry | None = None,
    correlation_id: str = "",
    occurred_at: datetime | None = None,
) -> SignupLedgerEntry:
    if actor.staff_power and after is not None:
        after = after.model_copy(update={"extra": {**after.extra, "staff_power": True}})
    entry = SignupLedgerEntry.objects.create(
        event=event,
        organization_id=event.organization_id,
        signup=signup,
        event_snapshot=event_snapshot(event),
        subject_user=subject,
        subject_snapshot=user_snapshot(subject),
        actor_user=actor.user,
        actor_snapshot=user_snapshot(actor.user),
        actor_role=actor.role,
        means=actor.means,
        on_behalf=actor.user is not None and actor.user.pk != subject.pk,
        action=action,
        before=_dump(before),
        after=_dump(after),
        reason=reason,
        rules_overridden=list(rules_overridden),
        caused_by=caused_by,
        correlation_id=correlation_id or actor.correlation_id,
        occurred_at=occurred_at if occurred_at is not None else tz.now(),
    )
    fields: dict[str, Any] = {
        "entry_id": entry.pk,
        "event_id": entry.event_id,
        "signup_id": entry.signup_id,
        "subject_user_id": entry.subject_user_id,
        "actor_user_id": entry.actor_user_id,
        "actor_role": str(entry.actor_role),
        "means": str(entry.means),
        "action": str(entry.action),
        "correlation_id": entry.correlation_id,
    }
    transaction.on_commit(
        lambda: log.info(
            "signup_ledger_entry_recorded",
            system="events",
            subsystem="ledger",
            **fields,
        )
    )
    return entry


def record_ready_check_transition(
    *,
    event: Event,
    actor: SignupActor,
    check: ReadyCheck,
    step: str,
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> SignupLedgerEntry:
    entry = SignupLedgerEntry.objects.create(
        event=event,
        organization_id=event.organization_id,
        signup=None,
        event_snapshot=event_snapshot(event),
        subject_user=None,
        subject_snapshot={},
        actor_user=actor.user,
        actor_snapshot=user_snapshot(actor.user),
        actor_role=actor.role,
        means=actor.means,
        on_behalf=False,
        action=SignupAction.READY_CHECK_TRANSITION,
        before=None,
        after={
            "extra": {
                "step": step,
                "phase": check.phase,
                "outcome": check.outcome,
                **(extra or {}),
            }
        },
        reason=reason or step,
        correlation_id=f"rc{check.pk}:{step}",
        occurred_at=tz.now(),
    )
    fields: dict[str, Any] = {
        "entry_id": entry.pk,
        "event_id": entry.event_id,
        "ready_check_id": check.pk,
        "step": step,
        "phase": check.phase,
        "outcome": check.outcome,
        "actor_user_id": entry.actor_user_id,
        "actor_role": str(entry.actor_role),
        "means": str(entry.means),
        "action": str(entry.action),
        "correlation_id": entry.correlation_id,
    }
    transaction.on_commit(
        lambda: log.info(
            "signup_ledger_entry_recorded",
            system="events",
            subsystem="ledger",
            **fields,
        )
    )
    return entry


LEDGER_STATE_DELETED = "deleted"
LEDGER_STATE_MOVED = "moved"
RESOLVE_CHUNK_SIZE: int = 500

_LIVE_FIELDS = (
    "pk",
    "name",
    "scheduled_at",
    "ends_at",
    "state",
    "event_repeater_id",
    "organization_id",
)


@dataclass(frozen=True, slots=True)
class RecordsWindow:
    since: datetime | None = None
    until: datetime | None = None
    series_id: int | None = None
    event_id: int | None = None

    @property
    def has_time_bounds(self) -> bool:
        return self.since is not None or self.until is not None

    def admits(self, event: LedgerEvent) -> bool:
        if self.event_id is not None and event.event_id != self.event_id:
            return False
        if self.series_id is not None and event.series_id != self.series_id:
            return False
        if not self.has_time_bounds:
            return True
        if event.scheduled_at is None:
            return False
        if self.since is not None and event.scheduled_at < self.since:
            return False
        return not (self.until is not None and event.scheduled_at >= self.until)


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_id: int
    name: str
    scheduled_at: datetime | None
    ends_at: datetime | None
    state: str
    series_id: int | None
    organization_id: int | None

    @property
    def end(self) -> datetime | None:
        return self.ends_at or self.scheduled_at


def parse_snapshot_time(
    value: object, *, event_id: int | None = None, field: str = ""
) -> datetime | None:
    if value is None or value == "":
        return None
    parsed: datetime | None = None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
    if parsed is None or parsed.tzinfo is None:
        log.debug(
            "signup_ledger_snapshot_unparsed",
            system="events",
            subsystem="ledger",
            event_id=event_id,
            field=field,
        )
        return None
    return parsed.astimezone(UTC)


def _chunks(ids: Sequence[int]) -> Iterator[list[int]]:
    size = RESOLVE_CHUNK_SIZE
    for start in range(0, len(ids), size):
        yield list(ids[start : start + size])


def _snapshot_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _from_snapshot(
    event_id: int, snap: object, *, state: str, organization_id: int
) -> LedgerEvent:
    data: dict[str, Any] = snap if isinstance(snap, dict) else {}
    name = data.get("name")
    return LedgerEvent(
        event_id=event_id,
        name=name if isinstance(name, str) else "",
        scheduled_at=parse_snapshot_time(
            data.get("scheduled_at"), event_id=event_id, field="scheduled_at"
        ),
        ends_at=parse_snapshot_time(
            data.get("ends_at"), event_id=event_id, field="ends_at"
        ),
        state=state,
        series_id=_snapshot_int(data.get("series_id")),
        organization_id=organization_id,
    )


def _live_query(
    ids: list[int], organization_id: int, window: RecordsWindow | None
) -> QuerySet[Any]:
    qs = Event.objects.nocache().filter(pk__in=ids, organization_id=organization_id)
    if window is not None:
        if window.since is not None:
            qs = qs.filter(scheduled_at__gte=window.since)
        if window.until is not None:
            qs = qs.filter(scheduled_at__lt=window.until)
        if window.series_id is not None:
            qs = qs.filter(event_repeater_id=window.series_id)
    return qs.values_list(*_LIVE_FIELDS)


def _latest_snapshots(organization_id: int, ids: list[int]) -> dict[int, object]:
    rows = SignupLedgerEntry.objects.nocache().filter(organization_id=organization_id)
    latest = (
        rows.filter(event_id=OuterRef("event_id"))
        .order_by("-occurred_at", "-pk")
        .values("pk")[:1]
    )
    return dict(
        rows.filter(event_id__in=ids)
        .annotate(latest_pk=Subquery(latest))
        .filter(pk=F("latest_pk"))
        .order_by()
        .values_list("event_id", "event_snapshot")
    )


def resolve_ledger_events(
    organization_id: int,
    *,
    event_ids: Collection[int] | None = None,
    window: RecordsWindow | None = None,
) -> dict[int, LedgerEvent]:
    ids: set[int] = set(
        SignupLedgerEntry.objects.nocache()
        .filter(organization_id=organization_id)
        .order_by()
        .values_list("event_id", flat=True)
        .distinct()
    )
    if event_ids is not None:
        ids &= set(event_ids)
    if window is not None and window.event_id is not None:
        ids &= {window.event_id}
    ordered = sorted(ids)
    if not ordered:
        return {}

    result: dict[int, LedgerEvent] = {}
    snapshot_ids: dict[int, str] = {}
    for chunk in _chunks(ordered):
        owners = dict(
            Event.objects.nocache()
            .filter(pk__in=chunk)
            .order_by()
            .values_list("pk", "organization_id")
        )
        live_ids = [pk for pk in chunk if owners.get(pk) == organization_id]
        for pk in chunk:
            if pk not in owners:
                snapshot_ids[pk] = LEDGER_STATE_DELETED
            elif owners[pk] != organization_id:
                snapshot_ids[pk] = LEDGER_STATE_MOVED
        if not live_ids:
            continue
        for pk, name, scheduled_at, ends_at, state, series_id, org_id in _live_query(
            live_ids, organization_id, window
        ):
            result[pk] = LedgerEvent(
                event_id=pk,
                name=name,
                scheduled_at=scheduled_at,
                ends_at=ends_at,
                state=str(state),
                series_id=series_id,
                organization_id=org_id,
            )

    pending = sorted(snapshot_ids)
    for chunk in _chunks(pending):
        for pk, snap in _latest_snapshots(organization_id, chunk).items():
            resolved = _from_snapshot(
                pk, snap, state=snapshot_ids[pk], organization_id=organization_id
            )
            if window is None or window.admits(resolved):
                result[pk] = resolved
    return result


@dataclass(frozen=True, slots=True)
class SignupPurgeResult:
    purged: int
    organizations: int
    events: int
    skipped_unknown_end: int
    per_org: dict[int, int]
    more: bool


def purge_expired(
    *,
    now: datetime | None = None,
    batch_size: int = PURGE_BATCH_SIZE,
    time_budget_s: float | None = None,
) -> SignupPurgeResult:
    now = now or tz.now()
    budget = (
        settings.SIGNUP_RECORDS_PURGE_BUDGET_S
        if time_budget_s is None
        else time_budget_s
    )
    deadline = time.monotonic() + budget
    purged = events = skipped = 0
    per_org: dict[int, int] = {}
    more = False
    retention = (
        OrgSettings.objects.nocache()
        .filter(signup_record_retention_days__isnull=False)
        .order_by("organization_id")
        .values_list("organization_id", "signup_record_retention_days")
    )
    for org_id, days in retention:
        if time.monotonic() >= deadline:
            more = True
            break
        cutoff = now - timedelta(days=days)
        expired: list[int] = []
        for event_id, resolved in resolve_ledger_events(org_id).items():
            end = resolved.end
            if end is None:
                skipped += 1
            elif end < cutoff:
                expired.append(event_id)
        if not expired:
            continue
        outcome = (
            SignupLedgerEntry.objects.nocache()
            .filter(organization_id=org_id)
            .purge(
                organization_id=org_id,
                event_ids=expired,
                batch_size=batch_size,
                deadline=deadline,
                extra_log={"retention_days": days},
            )
        )
        per_org[org_id] = outcome.count
        purged += outcome.count
        events += outcome.events
        if not outcome.complete:
            more = True
            break

    result = SignupPurgeResult(
        purged=purged,
        organizations=len(per_org),
        events=events,
        skipped_unknown_end=skipped,
        per_org=per_org,
        more=more,
    )
    log.info(
        "signup_records_purge_completed",
        system="events",
        subsystem="ledger",
        purged=purged,
        organizations=result.organizations,
        events=events,
        skipped_unknown_end=skipped,
        more=more,
    )
    return result
