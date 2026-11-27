import time
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from app.models import CustomUser
from common.game import GameType
from events.eligibility import refresh_members_eligibility
from org.api_connections.authority import (
    ConnectionAuthorityLost,
    assert_connection_authority,
)
from org.api_connections.config import CONFIG_FIELDS
from org.api_connections.crypto import (
    CredentialError,
    canonical_origin,
    open_credential,
)
from org.api_connections.limits import (
    PAGE_BYTES,
    REQUEST_SECONDS,
    REQUESTS_PER_RUN,
    ROWS_PER_RUN,
    RUN_BYTES,
    RUN_SECONDS,
)
from org.api_connections.mapping import MappingError, map_page
from org.api_connections.mutations import MmrMutationContext, lock_memberships
from org.api_connections.pagination import PaginationError, first_page, next_position
from org.api_connections.runs import (
    ACTIVE_STATES,
    add_issues,
    finish_run,
    holds_fence,
    lock_fenced_run,
    renew_lease,
)
from org.api_connections.safe_http import request_json
from org.api_connections.schemas import (
    ConnectionConfigError,
    validate_connection_config,
)
from org.api_connections.templates import (
    TemplateError,
    identifier_kinds,
    member_identifier,
    render_request,
)
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import (
    ConnectionConfig,
    MappedPage,
    MemberSnapshot,
    SnapshotMember,
    StepResult,
)
from org.api_tokens.sync import match_member, to_account_id
from org.feature_errors import not_permitted, require_org_admin
from org.mmr import set_org_mmr
from org.mmr_official import apply_official_org_mmr
from org.models import (
    OrgApiConnection,
    OrgApiMmrPullTarget,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgLog,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

COMMIT_CHUNK = 500
MEMBER_BATCH = 100
MEMBER_SNAPSHOT_LIMIT = 10_000
MMR_PULL = OrgApiSyncRun.Kind.MMR_PULL
SNAPSHOT_FIELDS = {
    "outbound_base_url",
    "outbound_auth",
    "mmr_pull_config",
    "game_type",
    "overwrite_policy",
    "mark_verified",
    "interval_minutes",
}


class _Stop(Exception):
    def __init__(self, code: str, *, state: str = OrgApiSyncRun.State.FAILED) -> None:
        self.code = code
        self.state = state
        super().__init__(code)


def connection_config(connection: OrgApiConnection) -> ConnectionConfig:
    return validate_connection_config(
        {field: getattr(connection, field) for field in CONFIG_FIELDS}
    )


def _game_type(config: ConnectionConfig) -> int:
    return config.game_type if config.game_type is not None else GameType.DOTA2


def _authorize(connection: OrgApiConnection) -> None:
    try:
        assert_connection_authority(connection, direction="mmr_pull")
    except ConnectionAuthorityLost as exc:
        exc.cleanup()
        raise


def create_pull_run(
    connection: OrgApiConnection,
    *,
    requester: CustomUser | None,
    scheduled: bool = False,
) -> OrgApiSyncRun:
    if not scheduled:
        if requester is None or not requester.is_active:
            raise not_permitted()
        require_org_admin(requester, connection.organization, None)
    _authorize(connection)
    for _ in range(2):
        try:
            with transaction.atomic():
                current = OrgApiConnection.objects.select_for_update().get(
                    pk=connection.pk, organization_id=connection.organization_id
                )
                active = OrgApiSyncRun.objects.filter(
                    connection=current, kind=MMR_PULL, state__in=ACTIVE_STATES
                ).first()
                if active is not None:
                    return active
                try:
                    config = connection_config(current)
                except ConnectionConfigError as exc:
                    raise PermissionDenied(
                        {"code": exc.code, "detail": exc.code}
                    ) from None
                run = OrgApiSyncRun.objects.create(
                    organization_id=current.organization_id,
                    connection=current,
                    kind=MMR_PULL,
                    requester=requester,
                    config_version=current.config_version,
                    config_snapshot={
                        **config.model_dump(mode="json", include=SNAPSHOT_FIELDS),
                        "trigger": "scheduled" if scheduled else "manual",
                    },
                )
                OrgApiRunCheckpoint.objects.create(run=run)
        except IntegrityError:
            continue
        log.info(
            "api_connection_pull_queued",
            system="org",
            subsystem="api_connections",
            org_id=run.organization_id,
            connection_id=run.connection_id,
            run_id=str(run.pk),
            scheduled=scheduled,
        )
        return run
    return OrgApiSyncRun.objects.get(
        connection_id=connection.pk, kind=MMR_PULL, state__in=ACTIVE_STATES
    )


def _check_connection(run: OrgApiSyncRun) -> OrgApiConnection:
    connection = OrgApiConnection.objects.get(pk=run.connection_id)
    if (
        connection.archived_at is not None
        or connection.config_version != run.config_version
    ):
        raise _Stop("configuration_changed", state=OrgApiSyncRun.State.CANCELED)
    try:
        assert_connection_authority(connection, direction="mmr_pull")
    except ConnectionAuthorityLost as exc:
        raise _AuthorityLost(exc) from None
    except PermissionDenied as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code", "not_permitted"))
        raise _Stop(code, state=OrgApiSyncRun.State.CANCELED) from None
    return connection


class _AuthorityLost(_Stop):
    def __init__(self, lost: ConnectionAuthorityLost) -> None:
        super().__init__("authority_lost", state=OrgApiSyncRun.State.CANCELED)
        self.lost = lost


def step_pull(run_id: UUID, *, fence: UUID) -> StepResult:
    run = OrgApiSyncRun.objects.filter(pk=run_id, kind=MMR_PULL).first()
    if run is None:
        return StepResult("missing", False, "not_found")
    if run.state not in ACTIVE_STATES:
        return StepResult(run.state, False, run.error_code or None)
    if not holds_fence(run, fence):
        return StepResult(run.state, False, "stale_fence")
    try:
        connection = _check_connection(run)
        checkpoint = OrgApiRunCheckpoint.objects.get(run=run)
        if checkpoint.phase == "snapshot":
            return _snapshot(run, fence)
        if checkpoint.phase in ("fetch", "fetch_inflight"):
            return _fetch(run, fence, connection, checkpoint)
        return _commit(run, fence, connection)
    except _Stop as stop:
        finished = finish_run(run_id, fence, state=stop.state, error_code=stop.code)
        if isinstance(stop, _AuthorityLost):
            stop.lost.cleanup()
        if finished is None:
            return StepResult(run.state, False, "stale_fence")
        return StepResult(finished.state, False, stop.code)


def _stale(run: OrgApiSyncRun) -> StepResult:
    return StepResult(run.state, False, "stale_fence")


def _snapshot(run: OrgApiSyncRun, fence: UUID) -> StepResult:
    config = connection_config(run.connection)
    game_type = _game_type(config)
    members = list(
        OrgUser.objects.nocache()
        .filter(organization_id=run.organization_id)
        .select_related("user")
        .order_by("pk")
    )
    if len(members) > MEMBER_SNAPSHOT_LIMIT:
        raise _Stop("member_limit_exceeded")
    revisions = dict(
        OrgMmrSyncState.objects.filter(
            org_user__organization_id=run.organization_id, game_type=game_type
        ).values_list("org_user_id", "revision")
    )
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        OrgApiRunCheckpoint.objects.filter(run=locked).update(
            phase="fetch",
            page=first_page(config) or 0,
            cursor="",
            seen_cursors=[],
            member_offset=0,
            member_snapshot=[
                {
                    "id": member.pk,
                    "s": member.user.steam_account_id,
                    "d": member.user.discordId or None,
                    "r": revisions.get(member.pk, 0),
                }
                for member in members
            ],
        )
        locked.state = OrgApiSyncRun.State.RUNNING
        locked.started_at = timezone.now()
        renew_lease(locked)
        locked.save(update_fields=["state", "started_at", "lease_expires_at"])
    return StepResult(locked.state, True)


def _members(checkpoint: OrgApiRunCheckpoint) -> list[SnapshotMember]:
    return [
        SnapshotMember(
            org_user_id=item["id"],
            steam_account_id=item["s"],
            discord_id=item["d"],
            revision=item["r"],
        )
        for item in checkpoint.member_snapshot
    ]


def _batch_end(config: ConnectionConfig, offset: int, total: int) -> int | None:
    mode = config.mmr_pull_config.request_mode
    if mode == "org":
        return max(total, 1) if offset == 0 else None
    if offset >= total:
        return None
    return min(total, offset + (1 if mode == "per_member" else MEMBER_BATCH))


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


def _status_code(status: int) -> str | None:
    if 200 <= status < 300:
        return None
    if status in (401, 403):
        return "remote_auth_failed"
    if status == 429:
        return "remote_rate_limited"
    if status >= 500:
        return "remote_error"
    return "remote_rejected"


def _advance_missing(
    run: OrgApiSyncRun,
    fence: UUID,
    checkpoint: OrgApiRunCheckpoint,
    skipped: list[int],
    offset: int,
) -> StepResult:
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        locked.missing_identifier_count += len(skipped)
        add_issues(
            locked,
            [{"code": "missing_identifier", "org_user_id": pk} for pk in skipped],
        )
        renew_lease(locked)
        locked.save()
        OrgApiRunCheckpoint.objects.filter(pk=checkpoint.pk).update(
            member_offset=offset, phase="fetch"
        )
    return StepResult(locked.state, True)


def _fetch(
    run: OrgApiSyncRun,
    fence: UUID,
    connection: OrgApiConnection,
    checkpoint: OrgApiRunCheckpoint,
) -> StepResult:
    config = connection_config(connection)
    pull = config.mmr_pull_config
    game_type = _game_type(config)
    members = _members(checkpoint)
    if run.started_at and timezone.now() - run.started_at > timedelta(
        seconds=RUN_SECONDS
    ):
        raise _Stop("run_deadline_exceeded")
    if checkpoint.phase == "fetch_inflight" and pull.method == "POST":
        raise _Stop("pull_ambiguous")
    offset = checkpoint.member_offset
    skipped: list[int] = []
    credential = _credential(connection, config)
    while True:
        end = _batch_end(config, offset, len(members))
        if end is None:
            if skipped:
                return _advance_missing(run, fence, checkpoint, skipped, offset)
            return _begin_commit(run, fence, checkpoint)
        batch = MemberSnapshot(
            organization_id=run.organization_id,
            game_type=game_type,
            members=tuple(members[offset:end]),
        )
        cursor = (
            checkpoint.seen_cursors[-1]
            if pull.pagination.kind == "cursor" and checkpoint.seen_cursors
            else None
        )
        try:
            request = render_request(
                config,
                batch,
                page=checkpoint.page if pull.pagination.kind == "page" else None,
                cursor=cursor,
                credential=credential,
            )
        except TemplateError as exc:
            if exc.code == "missing_identifier" and pull.request_mode == "per_member":
                skipped.extend(member.org_user_id for member in batch.members)
                offset = end
                continue
            raise _Stop(exc.code) from None
        if skipped:
            return _advance_missing(run, fence, checkpoint, skipped, offset)
        break
    if run.request_count >= REQUESTS_PER_RUN:
        raise _Stop("pull_incomplete")
    budget = min(PAGE_BYTES, RUN_BYTES - run.response_bytes)
    if budget <= 0:
        raise _Stop("pull_incomplete")
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        locked.request_count += 1
        renew_lease(locked)
        locked.save(update_fields=["request_count", "lease_expires_at"])
        OrgApiRunCheckpoint.objects.filter(pk=checkpoint.pk).update(
            phase="fetch_inflight"
        )
    report_page = locked.request_count
    try:
        response = request_json(
            request, deadline=time.monotonic() + REQUEST_SECONDS, max_bytes=budget
        )
    except SafeHttpError as exc:
        raise _Stop(exc.code) from None
    del credential, request
    if code := _status_code(response.status):
        raise _Stop(code)
    run.refresh_from_db()
    if not holds_fence(run, fence):
        return _stale(run)
    connection = _check_connection(run)
    try:
        mapped = map_page(response.data, config, page=report_page)
    except MappingError as exc:
        raise _Stop(exc.code) from None
    if run.row_count + len(mapped.rows) > ROWS_PER_RUN:
        raise _Stop("pull_incomplete")
    try:
        position = next_position(
            config, mapped, page=checkpoint.page, seen=list(checkpoint.seen_cursors)
        )
    except PaginationError as exc:
        raise _Stop(exc.code) from None
    if position is not None and run.request_count >= REQUESTS_PER_RUN:
        raise _Stop("pull_incomplete")
    batch_start = checkpoint.page == (first_page(config) or 0) and not (
        checkpoint.seen_cursors
    )
    missing: list[int] = []
    kinds = identifier_kinds(config)
    if batch_start and kinds and pull.request_mode != "per_member":
        missing = [
            member.org_user_id
            for member in batch.members
            if not any(member_identifier(member, kind) for kind in kinds)
        ]
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        locked.response_bytes += response.bytes_received
        locked.row_count += len(mapped.rows)
        locked.missing_identifier_count += len(missing)
        add_issues(
            locked,
            [{"code": "missing_identifier", "org_user_id": pk} for pk in missing],
        )
        _stage(locked, config, members, mapped, game_type)
        if position is not None:
            updates: dict[str, Any] = {
                "phase": "fetch",
                "page": position.page,
                "seen_cursors": position.seen,
            }
        else:
            done = _batch_end(config, end, len(members)) is None
            updates = {
                "phase": "commit" if done else "fetch",
                "page": first_page(config) or 0,
                "seen_cursors": [],
                "member_offset": end,
            }
            if done:
                locked.state = OrgApiSyncRun.State.PARTIAL
        renew_lease(locked)
        locked.save()
        OrgApiRunCheckpoint.objects.filter(pk=checkpoint.pk).update(**updates)
    log.info(
        "api_connection_pull_page",
        system="org",
        subsystem="api_connections",
        org_id=locked.organization_id,
        connection_id=locked.connection_id,
        run_id=str(locked.pk),
        request_count=locked.request_count,
        rows=len(mapped.rows),
    )
    return StepResult(locked.state, True)


def _stage(
    run: OrgApiSyncRun,
    config: ConnectionConfig,
    members: list[SnapshotMember],
    mapped: MappedPage,
    game_type: int,
) -> None:
    id_type = config.mmr_pull_config.mapping.player_id_type
    by_steam = {m.steam_account_id: m for m in members if m.steam_account_id}
    by_discord = {m.discord_id: m for m in members if m.discord_id}
    issues: list[dict[str, Any]] = []
    matched: list[tuple[SnapshotMember, int, int, int]] = []
    for row in mapped.rows:
        if row.error is not None:
            run.invalid_count += 1
            issues.append({"code": row.error, "page": row.page, "index": row.index})
            continue
        assert row.player_id is not None
        if id_type == "discord_id":
            member = match_member(
                by_steam,
                by_discord,
                steam_account_id=None,
                discord_id=row.player_id,
                identity=lambda item: item.org_user_id,
            )
        else:
            member = match_member(
                by_steam,
                by_discord,
                steam_account_id=to_account_id(int(row.player_id)),
                discord_id=None,
                identity=lambda item: item.org_user_id,
            )
        if not isinstance(member, SnapshotMember):
            run.unmatched_count += 1
            issues.append(
                {
                    "code": "unmatched",
                    "page": row.page,
                    "index": row.index,
                    "player_id": row.player_id,
                }
            )
            continue
        matched.append((member, row.mmr or 0, row.page, row.index))
    existing = {
        target.org_user_id: target
        for target in OrgApiMmrPullTarget.objects.filter(
            run=run, org_user_id__in=[m.org_user_id for m, *_ in matched]
        )
    }
    for member, value, page, index in matched:
        target = existing.get(member.org_user_id)
        if target is None:
            existing[member.org_user_id] = OrgApiMmrPullTarget.objects.create(
                run=run,
                org_user_id=member.org_user_id,
                game_type=game_type,
                source_page=page,
                source_index=index,
                identifier_snapshot={
                    "steam_account_id": member.steam_account_id,
                    "discord_id": member.discord_id,
                },
                expected_revision=member.revision,
                proposed_value=value,
            )
            continue
        if target.outcome_code != "ambiguous_duplicate":
            if target.proposed_value == value:
                continue
            target.outcome_code = "ambiguous_duplicate"
            target.save(update_fields=["outcome_code"])
            run.invalid_count += 1
            issues.append(
                {
                    "code": "ambiguous_duplicate",
                    "page": target.source_page,
                    "index": target.source_index,
                }
            )
        run.invalid_count += 1
        issues.append({"code": "ambiguous_duplicate", "page": page, "index": index})
    add_issues(run, issues)


def _begin_commit(
    run: OrgApiSyncRun, fence: UUID, checkpoint: OrgApiRunCheckpoint
) -> StepResult:
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        locked.state = OrgApiSyncRun.State.PARTIAL
        renew_lease(locked)
        locked.save(update_fields=["state", "lease_expires_at"])
        OrgApiRunCheckpoint.objects.filter(pk=checkpoint.pk).update(phase="commit")
    return StepResult(locked.state, True)


def _principal(connection: OrgApiConnection) -> CustomUser:
    principal_id = (
        connection.outbound_authorizer_id
        if connection.outbound_auth == "none"
        else connection.outbound_credential_owner_id
    )
    return CustomUser.objects.get(pk=principal_id)


def _evaluate(
    target: OrgApiMmrPullTarget,
    user: CustomUser,
    revision: int,
    current: tuple[int, object],
    policy: str,
) -> str | None:
    snapshot = target.identifier_snapshot
    if (
        snapshot.get("steam_account_id") != user.steam_account_id
        or snapshot.get("discord_id") != (user.discordId or None)
        or revision != target.expected_revision
    ):
        return "conflict"
    value, verified_at = current
    if policy == "missing_only" and value != 0:
        return "skipped_policy"
    if policy == "unverified_only" and verified_at is not None:
        return "skipped_policy"
    return None


def _commit(
    run: OrgApiSyncRun, fence: UUID, connection: OrgApiConnection
) -> StepResult:
    config = connection_config(connection)
    game_type = _game_type(config)
    principal = _principal(connection)
    pending = list(
        OrgApiMmrPullTarget.objects.filter(run=run, outcome_code="").order_by("pk")[
            :COMMIT_CHUNK
        ]
    )
    if not pending:
        finished = finish_run(run.pk, fence, state=OrgApiSyncRun.State.SUCCEEDED)
        if finished is None:
            return _stale(run)
        return StepResult(finished.state, False)
    changed: list[OrgUser] = []
    with transaction.atomic():
        locked = lock_fenced_run(run.pk, fence)
        if locked is None:
            return _stale(run)
        current = OrgApiConnection.objects.select_for_update().get(pk=connection.pk)
        if current.config_version != locked.config_version:
            raise _Stop("configuration_changed", state=OrgApiSyncRun.State.CANCELED)
        members = {
            member.pk: member
            for member in lock_memberships(
                [target.org_user_id for target in pending], required=False
            )
        }
        users = CustomUser.objects.in_bulk(
            [member.user_id for member in members.values()]
        )
        revisions = dict(
            OrgMmrSyncState.objects.filter(
                org_user_id__in=members, game_type=game_type
            ).values_list("org_user_id", "revision")
        )
        values = {
            row.org_user_id: (row.mmr, row.verified_at)
            for row in OrgUserGameMmr.objects.nocache().filter(
                org_user_id__in=members, game_type=game_type
            )
        }
        for target in pending:
            member = members[target.org_user_id]
            outcome = _evaluate(
                target,
                users[member.user_id],
                revisions.get(member.pk, 0),
                values.get(member.pk, (0, None)),
                config.overwrite_policy,
            )
            if outcome is not None:
                target.outcome_code = outcome
                if outcome == "conflict":
                    locked.conflict_count += 1
                else:
                    locked.skipped_policy_count += 1
                continue
            outcome, verified = _apply(locked, target, member, principal, config)
            target.outcome_code = outcome
            target.applied_revision = (
                OrgMmrSyncState.objects.filter(org_user=member, game_type=game_type)
                .values_list("revision", flat=True)
                .first()
            )
            if outcome == "updated":
                locked.updated_count += 1
                changed.append(member)
            else:
                locked.unchanged_count += 1
            locked.verified_count += int(verified)
        OrgApiMmrPullTarget.objects.bulk_update(
            pending, ["outcome_code", "applied_revision"]
        )
        if changed and not config.mark_verified:
            refresh_members_eligibility(changed)
        renew_lease(locked)
        locked.save()
    if not OrgApiMmrPullTarget.objects.filter(run=run, outcome_code="").exists():
        finished = finish_run(run.pk, fence, state=OrgApiSyncRun.State.SUCCEEDED)
        if finished is None:
            return _stale(run)
        return StepResult(finished.state, False)
    return StepResult(locked.state, True)


def _apply(
    run: OrgApiSyncRun,
    target: OrgApiMmrPullTarget,
    member: OrgUser,
    principal: CustomUser,
    config: ConnectionConfig,
) -> tuple[str, bool]:
    context = MmrMutationContext(
        origin_connection_id=run.connection_id,
        run_id=run.pk,
        expected_revision=target.expected_revision,
    )
    value = target.proposed_value
    if config.mark_verified:
        result = apply_official_org_mmr(
            member,
            target.game_type,
            value,
            actor=principal,
            source="api_pull",
            extra_log={"connection_id": run.connection_id, "run_id": str(run.pk)},
            sync_context=context,
        )
        return ("updated" if result.changed else "unchanged"), result.verified
    previous = (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user=member, game_type=target.game_type)
        .values_list("mmr", flat=True)
        .first()
    ) or 0
    if previous == value:
        return "unchanged", False
    set_org_mmr(
        member,
        target.game_type,
        value or None,
        mark_verified=False,
        sync_context=context,
    )
    OrgLog.objects.create(
        organization_id=run.organization_id,
        actor=principal,
        action="set_mmr",
        target_user_id=member.user_id,
        details={
            "game_type": target.game_type,
            "mmr": value,
            "old_mmr": previous,
            "source": "api_pull",
            "connection_id": run.connection_id,
            "run_id": str(run.pk),
        },
    )
    return "updated", False
