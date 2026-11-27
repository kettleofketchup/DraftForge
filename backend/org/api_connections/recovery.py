from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.models import CustomUser
from org.api_connections.audit import audit_connection
from org.api_connections.authority import (
    ConnectionAuthorityLost,
    assert_connection_authority,
)
from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.mmr_delivery import UNSENT_STATES, enqueue_mmr_delivery
from org.api_connections.mutations import lock_memberships
from org.api_connections.revisions import lock_revision_counters, next_revision
from org.api_connections.schemas import ConnectionConfigError
from org.feature_errors import not_permitted, require_org_admin
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgMmrSyncState,
    OrgUserGameMmr,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

State = OrgApiMmrDelivery.State
RESUME_LIMIT = 500
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
        now = timezone.now()
        canceled = OrgApiMmrDelivery.objects.filter(
            connection=current, state__in=UNSENT_STATES
        ).update(
            state=State.CANCELED,
            last_reason="resynced",
            lease_token=None,
            lease_expires_at=None,
            updated_at=now,
        )
        values = OrgUserGameMmr.objects.nocache().filter(
            org_user__organization_id=current.organization_id, mmr__gt=0
        )
        if current.game_type is not None:
            values = values.filter(game_type=current.game_type)
        members = lock_memberships(
            sorted(set(values.values_list("org_user_id", flat=True))), required=False
        )
        lock_revision_counters(members)
        enqueued = 0
        for row in values.select_related("org_user__user").order_by(
            "org_user_id", "game_type"
        ):
            state, _ = OrgMmrSyncState.objects.update_or_create(
                org_user=row.org_user,
                game_type=row.game_type,
                defaults={
                    "revision": next_revision(current.organization_id, row.game_type),
                    "value": row.mmr,
                    "verified_at": row.verified_at,
                },
            )
            if enqueue_mmr_delivery(current, state, origin_connection_id=None):
                enqueued += 1
        audit_connection(
            current, actor=actor, action="resync_mmr_deliveries", fields=[]
        )
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
