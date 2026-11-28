from collections import defaultdict

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from app.models import CustomUser
from org.api_connections.audit import audit_connection
from org.api_connections.authority import (
    ConnectionAuthorityLost,
    assert_connection_authority,
)
from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.mmr_delivery import (
    UNSENT_STATES,
    build_mmr_delivery,
    supersede_unsent,
)
from org.api_connections.mutations import lock_memberships
from org.api_connections.schemas import ConnectionConfigError
from org.feature_errors import not_permitted, require_org_admin
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUserGameMmr,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

State = OrgApiMmrDelivery.State
RESUME_LIMIT = 500
RESYNC_CHUNK = 500
CONDITIONAL_REASONS = ("auth_failed", "schema_rejected", "origin_changed")


def _authorize(connection: OrgApiConnection, actor: CustomUser) -> None:
    if not actor.is_active:
        raise not_permitted()
    require_org_admin(actor, connection.organization, None)
    try:
        assert_connection_authority(connection, direction="mmr_push")
    except ConnectionAuthorityLost as lost:
        lost.cleanup()
        raise


def _lock(connection: OrgApiConnection, expected_version: int) -> OrgApiConnection:
    current = OrgApiConnection.objects.select_for_update().get(
        pk=connection.pk, organization_id=connection.organization_id
    )
    if current.archived_at is not None:
        raise ConnectionConfigError("connection_archived")
    if type(expected_version) is not int or current.config_version != expected_version:
        raise ConnectionConfigError("configuration_changed")
    return current


def _recoverable(current: OrgApiConnection) -> Q:
    recoverable = ~Q(last_reason__in=CONDITIONAL_REASONS) | Q(
        last_reason="schema_rejected", config_version__lt=current.config_version
    )
    if current.outbound_auth == "none":
        recoverable |= Q(
            last_reason="auth_failed", config_version__lt=current.config_version
        )
    elif current.outbound_credential_set_at is not None:
        recoverable |= Q(
            last_reason="auth_failed",
            updated_at__lt=current.outbound_credential_set_at,
        )
    return recoverable


def resume_mmr_deliveries(
    connection: OrgApiConnection, *, actor: CustomUser, expected_version: int
) -> int:
    _authorize(connection, actor)
    with transaction.atomic():
        current = _lock(connection, expected_version)
        try:
            origin = canonical_origin(current.outbound_base_url)
        except CredentialError:
            return 0
        ids = list(
            OrgApiMmrDelivery.objects.filter(
                connection=current,
                state=State.PAUSED,
                destination_origin=origin,
                org_user__isnull=False,
            )
            .filter(_recoverable(current))
            .order_by("pk")
            .values_list("pk", flat=True)[:RESUME_LIMIT]
        )
        OrgApiMmrDelivery.objects.filter(pk__in=ids).update(
            state=State.RETRY,
            due_at=timezone.now(),
            attempts=0,
            lease_token=None,
            lease_expires_at=None,
            last_reason="",
            config_version=current.config_version,
            updated_at=timezone.now(),
        )
        audit_connection(
            current, actor=actor, action="resume_mmr_deliveries", fields=[]
        )
    log.info(
        "api_connection_deliveries_resumed",
        system="org",
        subsystem="api_connections",
        org_id=current.organization_id,
        connection_id=current.pk,
        count=len(ids),
    )
    return len(ids)


def _resync_values(current: OrgApiConnection) -> QuerySet[OrgUserGameMmr]:
    values = OrgUserGameMmr.objects.nocache().filter(
        org_user__organization_id=current.organization_id, mmr__gt=0
    )
    if current.game_type is not None:
        values = values.filter(game_type=current.game_type)
    return values


def _resync_chunk(
    connection: OrgApiConnection, expected_version: int, member_ids: list[int]
) -> int:
    with transaction.atomic():
        current = _lock(connection, expected_version)
        assert_connection_authority(current, direction="mmr_push")
        members = lock_memberships(member_ids, required=False)
        rows = list(
            _resync_values(current)
            .filter(org_user_id__in=[member.pk for member in members])
            .select_related("org_user__user")
            .order_by("org_user_id", "game_type")
        )
        by_game: defaultdict[int, list[OrgUserGameMmr]] = defaultdict(list)
        for row in rows:
            by_game[row.game_type].append(row)
        existing = {
            (state.org_user_id, state.game_type): state
            for state in OrgMmrSyncState.objects.filter(
                org_user_id__in=[row.org_user_id for row in rows],
                game_type__in=list(by_game),
            )
        }
        now = timezone.now()
        updated: list[OrgMmrSyncState] = []
        created: list[OrgMmrSyncState] = []
        deliveries: list[OrgApiMmrDelivery] = []
        for game_type in sorted(by_game):
            group = by_game[game_type]
            counter, _ = (
                OrgMmrRevisionCounter.objects.select_for_update().get_or_create(organization_id=current.organization_id, game_type=game_type)
            )
            first = counter.revision + 1
            counter.revision += len(group)
            counter.save(update_fields=["revision"])
            for offset, row in enumerate(group):
                state = existing.get((row.org_user_id, game_type))
                if state is None:
                    state = OrgMmrSyncState(org_user=row.org_user, game_type=game_type)
                    created.append(state)
                else:
                    state.org_user = row.org_user
                    updated.append(state)
                state.revision = first + offset
                state.value = row.mmr
                state.verified_at = row.verified_at
                state.updated_at = now
                deliveries.append(
                    build_mmr_delivery(current, state, origin_connection_id=None)
                )
            supersede_unsent(
                current,
                game_type=game_type,
                org_user_ids=[row.org_user_id for row in group],
                below_revision=first,
            )
        OrgMmrSyncState.objects.bulk_update(
            updated, ["revision", "value", "verified_at", "updated_at"]
        )
        OrgMmrSyncState.objects.bulk_create(created)
        OrgApiMmrDelivery.objects.bulk_create(deliveries)
    return len(deliveries)


def resync_mmr_deliveries(
    connection: OrgApiConnection,
    *,
    actor: CustomUser,
    expected_version: int,
    confirmed: bool,
) -> int:
    if confirmed is not True:
        raise ConnectionConfigError("confirmation_required")
    _authorize(connection, actor)
    with transaction.atomic():
        current = _lock(connection, expected_version)
        canceled = OrgApiMmrDelivery.objects.filter(
            connection=current, state__in=UNSENT_STATES
        ).update(
            state=State.CANCELED,
            last_reason="resynced",
            lease_token=None,
            lease_expires_at=None,
            updated_at=timezone.now(),
        )
        member_ids = sorted(
            set(_resync_values(current).values_list("org_user_id", flat=True))
        )
        audit_connection(
            current, actor=actor, action="resync_mmr_deliveries", fields=[]
        )
    enqueued = 0
    try:
        for start in range(0, len(member_ids), RESYNC_CHUNK):
            enqueued += _resync_chunk(
                current, expected_version, member_ids[start : start + RESYNC_CHUNK]
            )
    except ConnectionAuthorityLost as lost:
        lost.cleanup()
        raise
    log.info(
        "api_connection_deliveries_resynced",
        system="org",
        subsystem="api_connections",
        org_id=current.organization_id,
        connection_id=current.pk,
        canceled=canceled,
        count=enqueued,
    )
    return enqueued
