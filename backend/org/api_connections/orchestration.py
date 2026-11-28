import time
from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from app.models import CustomUser
from common.game import GameType
from org.api_connections.authority import (
    ConnectionAuthorityLost,
    assert_connection_authority,
    denial_code,
)
from org.api_connections.crypto import (
    CredentialError,
    canonical_origin,
    open_credential,
)
from org.api_connections.limits import (
    OUTBOUND_REQUESTS_PER_ORG,
    PAGE_BYTES,
    REQUEST_SECONDS,
    REQUESTS_PER_RUN,
    RUN_SECONDS,
)
from org.api_connections.mapping import MappingError, map_page
from org.api_connections.pagination import first_page
from org.api_connections.pull import (
    MEMBER_BATCH,
    connection_config,
    create_pull_run,
    status_error,
    step_pull,
)
from org.api_connections.push import acquire_delivery_lease, step_mmr_delivery
from org.api_connections.runs import (
    ACTIVE_STATES,
    LEASE_SECONDS,
    acquire_lease,
    add_issues,
    fenced_runs,
    finish_run,
    holds_fence,
    lock_fenced_run,
    lock_organization,
    outbound_busy,
    renew_lease,
)
from org.api_connections.safe_http import request_bytes, request_json
from org.api_connections.schemas import ConnectionConfigError
from org.api_connections.templates import TemplateError, render_request
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import (
    ConnectionConfig,
    MappedRow,
    MemberSnapshot,
    SafeHttpRequest,
    SnapshotMember,
    StepResult,
    WorkClaim,
)
from org.api_tokens.sync import match_member, to_account_id
from org.integration.dispatch import dispatch_due
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiPromotionAdoption,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgUser,
)
from org.models_promotion_sync import OutboxState, PromotionContactOutbox
from telemetry.logging import get_logger

log = get_logger(__name__)

STEP_SECONDS = 25
CLIENT_TIMEOUT_SECONDS = 30
WORKER_UNAVAILABLE_SECONDS = 120
RETENTION_DAYS = 90
PURGE_BATCH = 500
PURGE_BATCHES = 20
HEALTH_PATH = "/health"
HEALTH_BYTES = 4096
ABANDON_SECONDS = 6 * RUN_SECONDS
TEST_DIRECTIONS = ("mmr_pull", "mmr_push", "promotion_push")
TERMINAL_STATES = ("succeeded", "failed", "canceled")
Kind = OrgApiSyncRun.Kind
RunState = OrgApiSyncRun.State
Delivery = OrgApiMmrDelivery.State


class _Stop(Exception):
    def __init__(
        self,
        code: str,
        *,
        state: str = RunState.FAILED,
        lost: ConnectionAuthorityLost | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.state = state
        self.lost = lost


def _member_count(connection: OrgApiConnection) -> int:
    return (
        OrgUser.objects.nocache()
        .filter(organization_id=connection.organization_id)
        .count()
    )


def _check_per_member(connection: OrgApiConnection, config: ConnectionConfig) -> None:
    pull = config.mmr_pull_config
    if (
        pull.request_mode == "per_member"
        and not pull.acknowledge_per_member
        and _member_count(connection) > REQUESTS_PER_RUN
    ):
        raise ConnectionConfigError("per_member_acknowledgement_required")


def enqueue_manual_pull(
    connection: OrgApiConnection, *, requester: CustomUser
) -> OrgApiSyncRun:
    if connection.archived_at is not None:
        raise ConnectionConfigError("connection_archived")
    _check_per_member(connection, connection_config(connection))
    return create_pull_run(connection, requester=requester)


def create_test_run(
    connection: OrgApiConnection, *, requester: CustomUser, direction: str
) -> OrgApiSyncRun:
    if direction not in TEST_DIRECTIONS:
        raise ConnectionConfigError("invalid_request")
    current = OrgApiConnection.objects.get(pk=connection.pk)
    if current.archived_at is not None:
        raise ConnectionConfigError("connection_archived")
    try:
        assert_connection_authority(
            current, direction=direction, requester=requester, testing=True
        )
    except ConnectionAuthorityLost as lost:
        lost.cleanup()
        raise
    config = connection_config(current)
    if not current.outbound_base_url:
        raise ConnectionConfigError("invalid_url")
    if direction == "mmr_pull":
        _check_per_member(current, config)
    with transaction.atomic():
        locked = OrgApiConnection.objects.select_for_update().get(pk=current.pk)
        if locked.archived_at is not None:
            raise ConnectionConfigError("connection_archived")
        active = OrgApiSyncRun.objects.filter(
            connection=locked,
            kind=Kind.TEST,
            state__in=ACTIVE_STATES,
            config_snapshot__direction=direction,
        ).first()
        if active is not None:
            return active
        run = OrgApiSyncRun.objects.create(
            organization_id=locked.organization_id,
            connection=locked,
            kind=Kind.TEST,
            requester=requester,
            config_version=locked.config_version,
            config_snapshot={
                "trigger": "manual",
                "direction": direction,
                "health_only": direction != "mmr_pull",
            },
        )
        OrgApiRunCheckpoint.objects.create(run=run)
    log.info(
        "api_connection_test_queued",
        system="org",
        subsystem="api_connections",
        org_id=run.organization_id,
        connection_id=run.connection_id,
        run_id=str(run.pk),
        direction=direction,
    )
    return run


def schedule_due_pulls(
    *, now: datetime, limit: int, skip_org_ids: Collection[int] = ()
) -> int:
    scheduled = 0
    due = (
        OrgApiConnection.objects.filter(
            enabled=True,
            mmr_pull_enabled=True,
            archived_at__isnull=True,
            interval_minutes__isnull=False,
            next_due_at__lte=now,
        )
        .exclude(organization_id__in=skip_org_ids)
        .order_by("next_due_at", "pk")[:limit]
    )
    for connection in due:
        assert connection.interval_minutes is not None
        following = now + timedelta(minutes=connection.interval_minutes)
        if not OrgApiConnection.objects.filter(
            pk=connection.pk, next_due_at=connection.next_due_at
        ).update(next_due_at=following):
            continue
        try:
            with transaction.atomic():
                _check_per_member(connection, connection_config(connection))
                create_pull_run(connection, requester=None, scheduled=True)
        except (PermissionDenied, ConnectionConfigError) as exc:
            code = (
                exc.code
                if isinstance(exc, ConnectionConfigError)
                else (denial_code(exc))
            )
            log.warning(
                "api_connection_schedule_skipped",
                system="org",
                subsystem="api_connections",
                org_id=connection.organization_id,
                connection_id=connection.pk,
                error_code=code,
            )
            continue
        except Exception:
            log.exception(
                "api_connection_schedule_failed",
                system="org",
                subsystem="api_connections",
                org_id=connection.organization_id,
                connection_id=connection.pk,
            )
            continue
        scheduled += 1
    return scheduled


def abandon_stale_runs(*, now: datetime, limit: int = PURGE_BATCH) -> int:
    cutoff = now - timedelta(seconds=ABANDON_SECONDS)
    run_ids = list(
        OrgApiSyncRun.objects.filter(state__in=ACTIVE_STATES, created_at__lt=cutoff)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    abandoned = 0
    for run_id in run_ids:
        fence = uuid4()
        if not OrgApiSyncRun.objects.filter(pk=run_id, state__in=ACTIVE_STATES).update(
            lease_token=fence,
            lease_expires_at=timezone.now() + timedelta(seconds=LEASE_SECONDS),
        ):
            continue
        if finish_run(run_id, fence, state=RunState.FAILED, error_code="run_abandoned"):
            abandoned += 1
    if abandoned:
        log.warning(
            "api_connection_runs_abandoned",
            system="org",
            subsystem="api_connections",
            abandoned=abandoned,
        )
    return abandoned


def claim_work(
    *, now: datetime, limit: int = 20, skip_org_ids: Collection[int] = ()
) -> list[WorkClaim]:
    abandon_stale_runs(now=now)
    if settings.ORG_API_SCHEDULED_PULLS:
        try:
            schedule_due_pulls(now=now, limit=limit, skip_org_ids=skip_org_ids)
        except Exception:
            log.exception(
                "api_connection_schedule_sweep_failed",
                system="org",
                subsystem="api_connections",
            )
    claims: list[WorkClaim] = []
    run_ids = list(
        OrgApiSyncRun.objects.filter(state__in=ACTIVE_STATES)
        .exclude(organization_id__in=skip_org_ids)
        .filter(Q(lease_token__isnull=True) | Q(lease_expires_at__lte=now))
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    for run_id in run_ids:
        fence = acquire_lease(run_id, now=now)
        if fence is not None:
            claims.append(WorkClaim(run_id=run_id, fence=fence))
    if len(claims) >= limit:
        return claims
    delivery_ids = list(
        OrgApiMmrDelivery.objects.filter(
            Q(state__in=(Delivery.PENDING, Delivery.RETRY), due_at__lte=now)
            | Q(state=Delivery.IN_FLIGHT, lease_expires_at__lte=now)
        )
        .exclude(connection__organization_id__in=skip_org_ids)
        .order_by("due_at", "pk")
        .values_list("delivery_id", flat=True)[: limit * 2]
    )
    for delivery_id in delivery_ids:
        if len(claims) >= limit:
            break
        fence = acquire_delivery_lease(delivery_id, now=now)
        if fence is not None:
            claims.append(
                WorkClaim(run_id=delivery_id, fence=fence, kind="mmr_delivery")
            )
    return claims


def step_run(run_id: UUID, *, fence: UUID) -> StepResult:
    run = OrgApiSyncRun.objects.filter(pk=run_id).only("kind", "state").first()
    if run is None:
        return StepResult("missing", False, "not_found")
    following = uuid4()
    if not fenced_runs(run_id, fence).update(
        lease_token=following,
        lease_expires_at=timezone.now() + timedelta(seconds=LEASE_SECONDS),
    ):
        run.refresh_from_db(fields=["state"])
        return StepResult(run.state, False, "stale_fence")
    if run.kind == Kind.MMR_PULL:
        result = step_pull(run_id, fence=following)
    elif run.kind == Kind.TEST:
        result = _step_test(run_id, following)
    else:
        finished = finish_run(
            run_id, following, state=RunState.FAILED, error_code="unsupported_kind"
        )
        result = StepResult(
            finished.state if finished else run.state, False, "unsupported_kind"
        )
    return replace(result, fence=following if result.continuation else None)


def step_delivery(delivery_id: UUID, *, fence: UUID) -> StepResult:
    delivery = OrgApiMmrDelivery.objects.filter(delivery_id=delivery_id).first()
    if delivery is None:
        return StepResult("missing", False, "not_found")
    following = uuid4()
    if not OrgApiMmrDelivery.objects.filter(
        pk=delivery.pk,
        lease_token=fence,
        state=Delivery.IN_FLIGHT,
        lease_expires_at__gt=timezone.now(),
    ).update(lease_token=following):
        return StepResult(delivery.state, False, "stale_fence")
    return replace(step_mmr_delivery(delivery_id, fence=following), fence=None)


def _promotion_orgs(now: datetime, skip_org_ids: Collection[int] = ()) -> list[int]:
    adopted = (
        OrgApiPromotionAdoption.objects.filter(
            connection__enabled=True,
            connection__promotion_push_enabled=True,
            connection__archived_at__isnull=True,
        )
        .exclude(organization_id__in=skip_org_ids)
        .values_list("organization_id", flat=True)
    )
    return [
        org_id
        for org_id in adopted
        if outbound_busy(org_id, now) < OUTBOUND_REQUESTS_PER_ORG
    ]


def _promotion_due_rows(now: datetime, org_ids: list[int]) -> bool:
    return (
        PromotionContactOutbox.objects.filter(organization_id__in=org_ids)
        .filter(
            Q(state__in=(OutboxState.PENDING, OutboxState.RETRY), due_at__lte=now)
            | Q(state=OutboxState.IN_FLIGHT, lease_expires_at__lte=now)
        )
        .exists()
    )


def promotion_due(*, now: datetime, skip_org_ids: Collection[int] = ()) -> bool:
    org_ids = _promotion_orgs(now, skip_org_ids)
    return bool(org_ids) and _promotion_due_rows(now, org_ids)


def step_promotion(
    *, now: datetime | None = None, skip_org_ids: Collection[int] = ()
) -> StepResult:
    now = now or timezone.now()
    org_ids = _promotion_orgs(now, skip_org_ids)
    if not org_ids or not _promotion_due_rows(now, org_ids):
        return StepResult("idle", False)
    report = dispatch_due(limit=1, organization_ids=org_ids)
    if not report.leased:
        return StepResult("idle", False)
    return StepResult(
        "dispatched", promotion_due(now=timezone.now(), skip_org_ids=skip_org_ids)
    )


def _expired_runs(now: datetime) -> QuerySet[OrgApiSyncRun]:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    return OrgApiSyncRun.objects.filter(state__in=TERMINAL_STATES).filter(
        Q(finished_at__lt=cutoff) | Q(finished_at__isnull=True, created_at__lt=cutoff)
    )


def purge_expired_runs(
    *, now: datetime, batch: int = PURGE_BATCH, dry_run: bool = False
) -> int:
    if dry_run:
        return _expired_runs(now).count()
    deleted = 0
    for _ in range(PURGE_BATCHES):
        ids = list(_expired_runs(now).values_list("pk", flat=True)[:batch])
        if not ids:
            break
        OrgApiSyncRun.objects.filter(pk__in=ids).delete()
        deleted += len(ids)
    if deleted:
        log.info(
            "api_connection_runs_purged",
            system="org",
            subsystem="api_connections",
            deleted=deleted,
        )
    return deleted


def worker_status(run: OrgApiSyncRun, now: datetime) -> str | None:
    if (
        run.state != RunState.QUEUED
        or run.started_at is not None
        or now - run.created_at <= timedelta(seconds=WORKER_UNAVAILABLE_SECONDS)
    ):
        return None
    if run.lease_expires_at is not None and run.lease_expires_at > now:
        return "waiting_for_capacity"
    return "worker_unavailable"


RUN_FIELDS = (
    "kind",
    "state",
    "config_version",
    "created_at",
    "started_at",
    "finished_at",
    "error_code",
    "request_count",
    "row_count",
    "response_bytes",
    "updated_count",
    "unchanged_count",
    "unmatched_count",
    "invalid_count",
    "conflict_count",
    "skipped_policy_count",
    "missing_identifier_count",
    "verified_count",
    "issue_count",
)


def run_row(
    run: OrgApiSyncRun, *, now: datetime, detail: bool = False
) -> dict[str, Any]:
    snapshot = run.config_snapshot or {}
    row: dict[str, Any] = {
        "id": str(run.pk),
        **{field: getattr(run, field) for field in RUN_FIELDS},
        "requester": run.requester_id,
        "trigger": snapshot.get("trigger"),
        "direction": snapshot.get("direction"),
        "health_only": bool(snapshot.get("health_only", False)),
        "worker_status": worker_status(run, now),
    }
    if detail:
        row["issues"] = list(run.issues)
    return row


def _game_type(config: ConnectionConfig) -> int:
    return config.game_type if config.game_type is not None else GameType.DOTA2


def _members(organization_id: int) -> list[SnapshotMember]:
    return [
        SnapshotMember(
            org_user_id=member.pk,
            steam_account_id=member.user.steam_account_id,
            discord_id=member.user.discordId or None,
        )
        for member in OrgUser.objects.nocache()
        .filter(organization_id=organization_id)
        .select_related("user")
        .order_by("pk")
    ]


def _credential(connection: OrgApiConnection, config: ConnectionConfig) -> str | None:
    if config.outbound_auth == "none":
        return None
    try:
        return open_credential(
            connection.outbound_credential_ciphertext,
            org_id=connection.organization_id,
            connection_id=connection.pk,
            origin=canonical_origin(config.outbound_base_url),
        )
    except CredentialError as exc:
        raise _Stop(exc.code) from None


def _check_test(run: OrgApiSyncRun, direction: str) -> OrgApiConnection:
    connection = OrgApiConnection.objects.get(pk=run.connection_id)
    if connection.archived_at is not None:
        raise _Stop("connection_archived", state=RunState.CANCELED)
    if connection.config_version != run.config_version:
        raise _Stop("configuration_changed", state=RunState.CANCELED)
    requester = CustomUser.objects.filter(pk=run.requester_id).first()
    if requester is None:
        raise _Stop("not_permitted", state=RunState.CANCELED)
    try:
        assert_connection_authority(
            connection, direction=direction, requester=requester, testing=True
        )
    except ConnectionAuthorityLost as lost:
        raise _Stop("authority_lost", state=RunState.CANCELED, lost=lost) from None
    except PermissionDenied as denied:
        raise _Stop(denial_code(denied), state=RunState.CANCELED) from None
    return connection


def _test_request(
    run: OrgApiSyncRun,
    connection: OrgApiConnection,
    config: ConnectionConfig,
    direction: str,
    members: list[SnapshotMember],
) -> SafeHttpRequest:
    credential = _credential(connection, config)
    if direction == "mmr_pull":
        pull = config.mmr_pull_config
        size = 1 if pull.request_mode == "per_member" else MEMBER_BATCH
        batch = MemberSnapshot(
            organization_id=run.organization_id,
            game_type=_game_type(config),
            members=tuple(members[:size]),
        )
        try:
            return render_request(
                config,
                batch,
                page=first_page(config),
                cursor=None,
                credential=credential,
            )
        except TemplateError as exc:
            raise _Stop(exc.code) from None
    field = (
        config.mmr_push_config.credential_field
        if direction == "mmr_push" and config.outbound_auth == "api_key_field"
        else None
    )
    if config.outbound_auth == "api_key_field" and (
        field is None or field.location != "query"
    ):
        raise _Stop("unsupported_auth")
    return SafeHttpRequest(
        url=config.outbound_base_url.rstrip("/") + HEALTH_PATH,
        method="GET",
        auth=config.outbound_auth,
        credential=credential,
        credential_origin=(
            canonical_origin(config.outbound_base_url) if credential else None
        ),
        credential_field=field,
    )


def _step_test(run_id: UUID, fence: UUID) -> StepResult:
    run = OrgApiSyncRun.objects.get(pk=run_id)
    direction = str((run.config_snapshot or {}).get("direction", ""))
    try:
        if direction not in TEST_DIRECTIONS:
            raise _Stop("invalid_request")
        return _execute_test(run, fence, direction)
    except _Stop as stop:
        finished = finish_run(run_id, fence, state=stop.state, error_code=stop.code)
        if stop.lost is not None:
            stop.lost.cleanup()
        if finished is None:
            return StepResult(run.state, False, "stale_fence")
        return StepResult(finished.state, False, stop.code)


def _execute_test(run: OrgApiSyncRun, fence: UUID, direction: str) -> StepResult:
    if timezone.now() - run.created_at > timedelta(seconds=RUN_SECONDS):
        raise _Stop("run_deadline_exceeded")
    connection = _check_test(run, direction)
    try:
        config = connection_config(connection)
    except ConnectionConfigError as exc:
        raise _Stop(exc.code) from None
    members = _members(run.organization_id) if direction == "mmr_pull" else []
    request = _test_request(run, connection, config, direction, members)
    checkpoint, _ = OrgApiRunCheckpoint.objects.get_or_create(run=run)
    if checkpoint.phase == "fetch_inflight" and request.method == "POST":
        raise _Stop("pull_ambiguous")
    with transaction.atomic():
        lock_organization(run.organization_id)
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return StepResult(run.state, False, "stale_fence")
        if (
            outbound_busy(run.organization_id, timezone.now(), exclude_run=run.pk)
            >= OUTBOUND_REQUESTS_PER_ORG
        ):
            return StepResult(locked.state, True, "org_busy")
        if locked.request_count >= REQUESTS_PER_RUN:
            raise _Stop("pull_incomplete")
        locked.state = RunState.RUNNING
        locked.started_at = locked.started_at or timezone.now()
        locked.request_count += 1
        renew_lease(locked)
        locked.save(
            update_fields=["state", "started_at", "request_count", "lease_expires_at"]
        )
        OrgApiRunCheckpoint.objects.filter(pk=checkpoint.pk).update(
            phase="fetch_inflight"
        )
    deadline = time.monotonic() + REQUEST_SECONDS
    try:
        if direction == "mmr_pull":
            response = request_json(request, deadline=deadline, max_bytes=PAGE_BYTES)
            status, received, data = (
                response.status,
                response.bytes_received,
                response.data,
            )
        else:
            raw = request_bytes(request, deadline=deadline, max_bytes=HEALTH_BYTES)
            status, received, data = raw.status, len(raw.body), None
    except SafeHttpError as exc:
        raise _Stop(exc.code) from None
    del request
    if code := status_error(status):
        raise _Stop(code)
    run.refresh_from_db()
    if not holds_fence(run, fence):
        return StepResult(run.state, False, "stale_fence")
    _check_test(run, direction)
    counts: dict[str, int] = {"row_count": 0, "invalid_count": 0, "unmatched_count": 0}
    issues: list[dict[str, Any]] = []
    if direction == "mmr_pull":
        try:
            mapped = map_page(data, config, page=1)
        except MappingError as exc:
            raise _Stop(exc.code) from None
        counts, issues = _sample(config, members, mapped.rows)
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return StepResult(run.state, False, "stale_fence")
        locked.response_bytes += received
        for field, value in counts.items():
            setattr(locked, field, getattr(locked, field) + value)
        add_issues(locked, issues)
        renew_lease(locked)
        locked.save()
        OrgApiRunCheckpoint.objects.filter(run=locked).update(phase="done")
    finished = finish_run(run.pk, fence, state=RunState.SUCCEEDED)
    if finished is None:
        return StepResult(run.state, False, "stale_fence")
    return StepResult(finished.state, False)


def _sample(
    config: ConnectionConfig, members: list[SnapshotMember], rows: Sequence[MappedRow]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    id_type = config.mmr_pull_config.mapping.player_id_type
    by_steam = {m.steam_account_id: m for m in members if m.steam_account_id}
    by_discord = {m.discord_id: m for m in members if m.discord_id}
    counts = {"row_count": len(rows), "invalid_count": 0, "unmatched_count": 0}
    issues: list[dict[str, Any]] = []
    for row in rows:
        if row.error is not None:
            counts["invalid_count"] += 1
            issues.append({"code": row.error, "page": row.page, "index": row.index})
            continue
        assert row.player_id is not None
        member = match_member(
            by_steam,
            by_discord,
            steam_account_id=(
                None if id_type == "discord_id" else to_account_id(int(row.player_id))
            ),
            discord_id=row.player_id if id_type == "discord_id" else None,
            identity=lambda item: item.org_user_id,
        )
        if not isinstance(member, SnapshotMember):
            counts["unmatched_count"] += 1
            issues.append(
                {
                    "code": "unmatched",
                    "page": row.page,
                    "index": row.index,
                    "player_id": row.player_id,
                }
            )
    return counts, issues
