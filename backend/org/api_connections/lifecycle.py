import secrets

from django.db import transaction
from django.db.models import Exists, Q
from django.utils import timezone
from rest_framework.exceptions import APIException

from app.models import CustomUser
from org.api_connections.audit import audit_connection
from org.api_tokens.operations import entitlements_for, parse_operations
from org.api_tokens.tokens import (
    PREFIX_BYTES,
    SECRET_BYTES,
    TOKEN_SCHEME,
    hash_secret,
    revoke_token,
)
from org.feature_errors import require_feature, require_org_admin
from org.models import OrgApiConnection, OrgApiSyncRun, OrgApiToken


class ConnectionConflict(APIException):
    status_code = 409
    default_code = "configuration_changed"

    def __init__(
        self,
        code: str = "configuration_changed",
        *,
        operations: list[str] | None = None,
    ) -> None:
        detail: dict[str, object] = {"code": code, "detail": code}
        if operations is not None:
            detail["operations"] = operations
        super().__init__(detail)


def invalidate_work(connection: OrgApiConnection) -> None:
    OrgApiSyncRun.objects.filter(
        connection=connection, state__in=["queued", "running", "partial"]
    ).update(
        state="canceled", error_code="configuration_changed", finished_at=timezone.now()
    )


def revoke_connection_keys(connection: OrgApiConnection, *, actor: CustomUser) -> None:
    OrgApiToken.objects.filter(connection=connection, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_by=actor
    )


def issue_connection_key(
    connection: OrgApiConnection,
    *,
    actor: CustomUser,
    rotate: bool,
    confirmed_operations: list[str] | None = None,
) -> tuple[OrgApiToken, str]:
    with transaction.atomic():
        current = (
            OrgApiConnection.objects.select_for_update()
            .select_related("organization")
            .get(pk=connection.pk)
        )
        require_org_admin(actor, current.organization, None)
        if not actor.is_active:
            raise ConnectionConflict("authority_lost")
        if (
            current.config_version != connection.config_version
            or current.key_version != connection.key_version
        ):
            raise ConnectionConflict()
        if current.archived_at or not current.inbound_enabled:
            raise ConnectionConflict("inbound_disabled")
        try:
            operations = parse_operations(current.operations)
        except ValueError:
            raise ConnectionConflict("operations_required") from None
        for feature in entitlements_for(operations):
            require_feature(current.organization, feature)
        active = current.tokens.filter(revoked_at__isnull=True).exists()
        if active and not rotate and not current.legacy_multi_credential:
            raise ConnectionConflict("credential_exists")
        if current.legacy_multi_credential:
            try:
                confirmed = parse_operations(confirmed_operations)
            except ValueError:
                confirmed = []
            if set(confirmed) != set(operations):
                raise ConnectionConflict(
                    "grant_confirmation_required", operations=operations
                )
        revoke_connection_keys(current, actor=actor)
        while True:
            prefix = secrets.token_hex(PREFIX_BYTES)
            if not OrgApiToken.objects.filter(prefix=prefix).exists():
                break
        secret = secrets.token_urlsafe(SECRET_BYTES)
        token = OrgApiToken.objects.create(
            organization_id=current.organization_id,
            connection=current,
            user=actor,
            issued_by=actor,
            name=current.name,
            prefix=prefix,
            secret_hash=hash_secret(secret),
            operations=operations,
        )
        current.legacy_multi_credential = False
        current.key_version += 1
        current.save(
            update_fields=["legacy_multi_credential", "key_version", "updated_at"]
        )
        audit_connection(
            current,
            actor=actor,
            action="rotate_connection_key" if rotate else "issue_connection_key",
            credential_changed=True,
        )
        return token, f"{TOKEN_SCHEME}_{prefix}_{secret}"


def handle_credential_owner_loss(
    user: CustomUser, *, organization_id: int | None = None
) -> None:
    tokens = OrgApiToken.objects.filter(user=user, revoked_at__isnull=True)
    principals = OrgApiConnection.objects.filter(
        Q(outbound_credential_owner=user) | Q(outbound_authorizer=user)
    )
    if organization_id is not None:
        tokens = tokens.filter(organization_id=organization_id)
        principals = principals.filter(organization_id=organization_id)
    if (
        not CustomUser.objects.filter(pk=user.pk)
        .filter(Exists(tokens) | Exists(principals))
        .exists()
    ):
        return
    with transaction.atomic():
        unattached = OrgApiToken.objects.filter(
            user=user, connection__isnull=True, revoked_at__isnull=True
        )
        if organization_id is not None:
            unattached = unattached.filter(organization_id=organization_id)
        for token in unattached:
            revoke_token(token, user)
        affected = OrgApiConnection.objects.filter(
            Q(outbound_credential_owner=user)
            | Q(outbound_authorizer=user)
            | Q(tokens__user=user, tokens__revoked_at__isnull=True)
        )
        if organization_id is not None:
            affected = affected.filter(organization_id=organization_id)
        affected = affected.values_list("pk", flat=True)
        for connection in (
            OrgApiConnection.objects.select_for_update()
            .filter(pk__in=affected)
            .order_by("pk")
        ):
            owned_outbound = user.pk in (
                connection.outbound_credential_owner_id,
                connection.outbound_authorizer_id,
            )
            OrgApiToken.objects.filter(
                connection=connection, user=user, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
            if owned_outbound:
                connection.outbound_credential_ciphertext = ""
                connection.outbound_credential_key_id = ""
                connection.outbound_credential_owner = None
                connection.outbound_credential_set_at = None
                connection.outbound_authorizer = None
                connection.mmr_push_enabled = False
                connection.mmr_pull_enabled = False
                connection.promotion_push_enabled = False
                connection.next_due_at = None
                connection.last_error_code = "authority_lost"
                connection.config_version += 1
                invalidate_work(connection)
            connection.key_version += 1
            connection.save()
            audit_connection(
                connection,
                actor=user,
                action="api_connection_owner_lost",
                credential_changed=owned_outbound,
            )


def disable_orphaned_outbound(connection_id: int) -> None:
    with transaction.atomic():
        connection = (
            OrgApiConnection.objects.select_for_update()
            .filter(pk=connection_id)
            .first()
        )
        if connection is None:
            return
        principal_id = (
            connection.outbound_authorizer_id
            if connection.outbound_auth == "none"
            else connection.outbound_credential_owner_id
        )
        if principal_id is not None or not (
            connection.mmr_push_enabled
            or connection.mmr_pull_enabled
            or connection.promotion_push_enabled
        ):
            return
        connection.outbound_credential_ciphertext = ""
        connection.outbound_credential_key_id = ""
        connection.outbound_credential_set_at = None
        connection.mmr_push_enabled = False
        connection.mmr_pull_enabled = False
        connection.promotion_push_enabled = False
        connection.next_due_at = None
        connection.last_error_code = "authority_lost"
        connection.config_version += 1
        connection.save()
        invalidate_work(connection)
        audit_connection(
            connection,
            actor=None,
            action="api_connection_owner_lost",
            credential_changed=True,
        )
