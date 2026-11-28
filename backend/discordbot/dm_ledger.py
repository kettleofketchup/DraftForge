"""The DM ledger service: the only code that writes DiscordDM rows."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce

from discordbot.dm_context import validate_context
from discordbot.live_messages import track_delivered_dm
from discordbot.models import DiscordDM, DMKind, DMStatus, DMSubject
from telemetry.logging import get_logger

log = get_logger(__name__)

DM_STALE_CLAIM_S: int = 600
PERMANENT_DM_ERROR_CODES: frozenset[int] = frozenset({50007, 10013, 50278})
ERROR_MAX_LEN = 300

ErrorClass = Literal[
    "pre_send", "rate_limit_timeout", "before_send_failed", "permanent"
]

_RETRYABLE_CLASSES: frozenset[str] = frozenset(
    {"pre_send", "rate_limit_timeout", "before_send_failed"}
)
_SKIP_STATUSES: frozenset[DMStatus] = frozenset(
    {
        DMStatus.SKIPPED_TEST_MODE,
        DMStatus.SKIPPED_NO_DISCORD,
        DMStatus.SKIPPED_DISABLED,
    }
)


class LedgerConflict(Exception):
    pass


class LedgerNotFound(Exception):
    pass


@dataclass(frozen=True)
class DMClaim:
    kind: DMKind
    idempotency_key: str
    claim_token: str
    discord_user_id: str
    recipient_user_id: int | None = None
    organization_id: int | None = None
    subject_type: DMSubject | None = None
    subject_id: int | None = None
    tournament_log_id: int | None = None
    context: Mapping[str, object] = field(default_factory=dict)
    has_components: bool = False
    initial_status: DMStatus | None = None

    def __post_init__(self) -> None:
        if (
            self.initial_status is not None
            and self.initial_status not in _SKIP_STATUSES
        ):
            raise ValueError(
                f"initial_status must be a skip, got {self.initial_status}"
            )


@dataclass(frozen=True)
class ClaimResult:
    id: int
    granted: bool
    status: DMStatus
    attempts: int
    created: bool


@dataclass(frozen=True)
class DMFinal:
    status: DMStatus
    error_class: ErrorClass | None = None
    discord_channel_id: str = ""
    discord_message_id: str | None = None
    http_status: int | None = None
    error_code: int | None = None
    error: str = ""


def _result(row: DiscordDM, *, granted: bool, created: bool) -> ClaimResult:
    return ClaimResult(
        id=row.pk,
        granted=granted,
        status=DMStatus(row.status),
        attempts=row.attempts,
        created=created,
    )


def _resolve_recipient(req: DMClaim) -> int | None:
    user_model = get_user_model()
    if req.recipient_user_id is None:
        if not req.discord_user_id:
            return None
        return (
            user_model.objects.filter(discordId=req.discord_user_id)
            .values_list("pk", flat=True)
            .first()
        )
    return req.recipient_user_id


def _recipient_mismatch(req: DMClaim) -> bool:
    if req.recipient_user_id is None or not req.discord_user_id:
        return False
    discord_id = (
        get_user_model()
        .objects.filter(pk=req.recipient_user_id)
        .values_list("discordId", flat=True)
        .first()
    )
    return bool(discord_id) and discord_id != req.discord_user_id


def _tournament_org(tournament_id: int | None) -> int | None:
    if tournament_id is None:
        return None
    tournament = apps.get_model("tournament", "Tournament")
    org_id = (
        tournament.objects.filter(pk=tournament_id)
        .values_list("league__organization_id", flat=True)
        .first()
    )
    if org_id is not None:
        return org_id
    event = apps.get_model("events", "Event")
    return (
        event.objects.filter(tournament_id=tournament_id)
        .order_by("pk")
        .values_list("organization_id", flat=True)
        .first()
    )


def _lobby_org(lobby_id: int) -> int | None:
    lobby = apps.get_model("lobby", "GameLobby")
    row = (
        lobby.objects.filter(pk=lobby_id)
        .values("game__tournament_id", "game__league__organization_id")
        .first()
    )
    if row is None:
        return None
    return (
        _tournament_org(row["game__tournament_id"])
        or row["game__league__organization_id"]
    )


def _resolve_org(subject_type: DMSubject | None, subject_id: int | None) -> int | None:
    if subject_type is None or subject_id is None:
        return None
    match DMSubject(subject_type):
        case DMSubject.EVENT:
            event = apps.get_model("events", "Event")
            return (
                event.objects.filter(pk=subject_id)
                .values_list("organization_id", flat=True)
                .first()
            )
        case DMSubject.TOURNAMENT:
            return _tournament_org(subject_id)
        case DMSubject.GAME_LOBBY:
            return _lobby_org(subject_id)
        case DMSubject.CAPTAIN_SNAPSHOT:
            snapshot = apps.get_model("org", "EventCaptain")
            return (
                snapshot.objects.filter(pk=subject_id)
                .values_list("organization_id", flat=True)
                .first()
            )
    return None


def _apply_initial_status(row: DiscordDM, req: DMClaim, now: datetime) -> None:
    if req.initial_status is not None:
        row.status = req.initial_status
        row.finished_at = now


_CLAIM_METADATA: tuple[str, ...] = (
    "kind",
    "discord_user_id",
    "recipient_id",
    "organization_id",
    "subject_type",
    "subject_id",
    "tournament_log_id",
    "context",
    "has_components",
)


def _grant_existing(
    row: DiscordDM, req: DMClaim, candidate: DiscordDM, now: datetime
) -> bool:
    if row.status == DMStatus.PENDING and row.claim_token == req.claim_token:
        return all(
            getattr(row, name) == getattr(candidate, name) for name in _CLAIM_METADATA
        )
    stale = (
        row.status == DMStatus.PENDING
        and row.send_started_at is None
        and row.claimed_at < now - timedelta(seconds=DM_STALE_CLAIM_S)
    )
    if not (stale or (row.status == DMStatus.FAILED and row.retryable)):
        return False
    for name in _CLAIM_METADATA:
        setattr(row, name, getattr(candidate, name))
    row.status = DMStatus.PENDING
    row.attempts += 1
    row.claim_token = req.claim_token
    row.claimed_at = now
    row.send_started_at = None
    row.finished_at = None
    row.discord_channel_id = ""
    row.discord_message_id = None
    row.http_status = None
    row.error_code = None
    row.error = ""
    row.retryable = False
    _apply_initial_status(row, req, now)
    row.save()
    return True


def claim(req: DMClaim, *, now: datetime) -> ClaimResult:
    kind = DMKind(req.kind)
    context = validate_context(kind, req.context)
    recipient_id = _resolve_recipient(req)
    organization_id = req.organization_id
    if organization_id is None:
        organization_id = _resolve_org(req.subject_type, req.subject_id)
    row = DiscordDM(
        kind=kind,
        idempotency_key=req.idempotency_key,
        claim_token=req.claim_token,
        discord_user_id=req.discord_user_id,
        recipient_id=recipient_id,
        organization_id=organization_id,
        subject_type=req.subject_type or "",
        subject_id=req.subject_id,
        tournament_log_id=req.tournament_log_id,
        context=context,
        has_components=req.has_components,
        created_at=now,
        claimed_at=now,
    )
    _apply_initial_status(row, req, now)
    with transaction.atomic():
        try:
            with transaction.atomic():
                row.save(force_insert=True)
        except IntegrityError:
            existing = (
                DiscordDM.objects.select_for_update()
                .filter(idempotency_key=req.idempotency_key)
                .first()
            )
            if existing is None:
                raise
            granted = _grant_existing(existing, req, row, now)
            log.info(
                "dm_claim_existing",
                system="discord",
                subsystem="dm",
                dm_kind=kind.value,
                ledger_id=existing.pk,
                status=existing.status,
                granted=granted,
                attempts=existing.attempts,
            )
            return _result(existing, granted=granted, created=False)
    if _recipient_mismatch(req):
        log.warning(
            "dm_claim_recipient_mismatch",
            system="discord",
            subsystem="dm",
            dm_kind=kind.value,
            ledger_id=row.pk,
            discord_user_id=req.discord_user_id,
            recipient_user_id=req.recipient_user_id,
        )
    log.info(
        "dm_claimed",
        system="discord",
        subsystem="dm",
        dm_kind=kind.value,
        ledger_id=row.pk,
        status=row.status,
    )
    return _result(row, granted=True, created=True)


def mark_sending(dm_id: int, *, claim_token: str, now: datetime) -> bool:
    mine = DiscordDM.objects.filter(
        pk=dm_id, status=DMStatus.PENDING, claim_token=claim_token
    )
    if mine.filter(send_started_at__isnull=True).update(send_started_at=now):
        return True
    return mine.exists()


def _retryable(outcome: DMFinal) -> bool:
    return (
        outcome.status == DMStatus.FAILED
        and outcome.error_class in _RETRYABLE_CLASSES
        and outcome.error_code not in PERMANENT_DM_ERROR_CODES
    )


def finalize(
    dm_id: int, outcome: DMFinal, *, claim_token: str, now: datetime
) -> DiscordDM:
    status = DMStatus(outcome.status)
    if status == DMStatus.PENDING:
        raise ValueError("finalize needs a terminal status")
    with transaction.atomic():
        row = DiscordDM.objects.select_for_update().filter(pk=dm_id).first()
        if row is None:
            raise LedgerNotFound(dm_id)
        if row.claim_token != claim_token:
            raise LedgerConflict(dm_id)
        if row.status != DMStatus.PENDING:
            if row.status == status:
                return row
            raise LedgerConflict(dm_id)
        row.status = status
        row.discord_channel_id = outcome.discord_channel_id
        row.discord_message_id = outcome.discord_message_id or None
        row.http_status = outcome.http_status
        row.error_code = outcome.error_code
        row.error = outcome.error[:ERROR_MAX_LEN]
        row.retryable = _retryable(outcome)
        row.sent_at = now if status == DMStatus.SENT else None
        row.finished_at = now
        row.save()
        track_delivered_dm(row)
    log.info(
        "dm_finalized",
        system="discord",
        subsystem="dm",
        dm_kind=row.kind,
        ledger_id=row.pk,
        status=row.status,
        error_code=row.error_code,
        retryable=row.retryable,
    )
    return row


def record_click(
    *, discord_message_id: str, discord_user_id: str, now: datetime
) -> DiscordDM | None:
    if not discord_message_id or not discord_user_id:
        return None
    rows = DiscordDM.objects.filter(
        discord_message_id=discord_message_id, discord_user_id=discord_user_id
    )
    updated = rows.update(
        click_count=F("click_count") + 1,
        first_clicked_at=Coalesce(
            "first_clicked_at", Value(now, output_field=models.DateTimeField())
        ),
        last_clicked_at=now,
    )
    if not updated:
        return None
    return rows.first()


def attach_on_click(
    dm_id: int,
    *,
    discord_user_id: str,
    discord_channel_id: str,
    discord_message_id: str,
    now: datetime,
) -> DiscordDM:
    with transaction.atomic():
        row = DiscordDM.objects.select_for_update().filter(pk=dm_id).first()
        if row is None:
            raise LedgerNotFound(dm_id)
        if not discord_user_id or row.discord_user_id != discord_user_id:
            raise LedgerConflict(dm_id)
        if row.discord_message_id:
            if row.discord_message_id != discord_message_id:
                raise LedgerConflict(dm_id)
            return row
        row.discord_channel_id = discord_channel_id
        row.discord_message_id = discord_message_id
        if row.status == DMStatus.PENDING:
            row.status = DMStatus.SENT
            row.sent_at = now
            row.finished_at = now
            row.error = "finalized_by_click"
        row.save()
    log.info(
        "dm_attached_on_click",
        system="discord",
        subsystem="dm",
        dm_kind=row.kind,
        ledger_id=row.pk,
        status=row.status,
    )
    return row


def _leadership_rows(
    *, snapshot_id: int, discord_user_id: str
) -> models.QuerySet[DiscordDM]:
    if not discord_user_id:
        return DiscordDM.objects.none()
    return DiscordDM.objects.filter(
        kind=DMKind.LEADERSHIP_REVIEW,
        subject_type=DMSubject.CAPTAIN_SNAPSHOT,
        subject_id=snapshot_id,
        discord_user_id=discord_user_id,
    ).order_by("pk")


def _trait_ids(row: DiscordDM) -> set[int]:
    raw = row.context.get("trait_ids") if isinstance(row.context, dict) else None
    if not isinstance(raw, list):
        return set()
    return {value for value in raw if isinstance(value, int)}


def find_leadership_row(
    *, snapshot_id: int, discord_user_id: str, trait_id: int
) -> DiscordDM | None:
    for row in _leadership_rows(
        snapshot_id=snapshot_id, discord_user_id=discord_user_id
    ):
        if trait_id in _trait_ids(row):
            return row
    return None


def leadership_message_of_other(
    *, snapshot_id: int, discord_message_id: str, discord_user_id: str
) -> bool:
    if not discord_message_id:
        return False
    return (
        DiscordDM.objects.filter(
            kind=DMKind.LEADERSHIP_REVIEW,
            subject_type=DMSubject.CAPTAIN_SNAPSHOT,
            subject_id=snapshot_id,
            discord_message_id=discord_message_id,
        )
        .exclude(discord_user_id=discord_user_id)
        .exists()
    )


def leadership_trait_ids(*, snapshot_id: int, discord_user_id: str) -> set[int]:
    ids: set[int] = set()
    for row in _leadership_rows(
        snapshot_id=snapshot_id, discord_user_id=discord_user_id
    ):
        ids |= _trait_ids(row)
    return ids


def scrub_rater(*, discord_user_id: str, now: datetime) -> int:
    if not discord_user_id:
        return 0
    scrubbed = 0
    with transaction.atomic():
        rows = DiscordDM.objects.select_for_update().filter(
            kind=DMKind.LEADERSHIP_REVIEW, discord_user_id=discord_user_id
        )
        for dm_id in rows.values_list("pk", flat=True):
            scrubbed += DiscordDM.objects.filter(pk=dm_id).update(
                idempotency_key=f"scrubbed:leadership_review:{dm_id}",
                discord_user_id="",
                first_clicked_at=None,
                last_clicked_at=None,
            )
    log.info(
        "dm_rater_scrubbed",
        system="discord",
        subsystem="dm",
        dm_kind=DMKind.LEADERSHIP_REVIEW.value,
        count=scrubbed,
        scrubbed_at=now.isoformat(),
    )
    return scrubbed
