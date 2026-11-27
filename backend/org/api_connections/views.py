from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from org.api_connections.audit import audit_connection
from org.api_connections.config import (
    CONFIG_FIELDS,
    WRITE_ONLY_FIELDS,
    apply_config_patch,
)
from org.api_connections.crypto import CredentialError
from org.api_connections.lifecycle import (
    invalidate_work,
    issue_connection_key,
    revoke_connection_keys,
)
from org.api_connections.schemas import (
    ConnectionConfigError,
    validate_connection_config,
)
from org.api_connections.serializers import ConnectionSerializer
from org.api_tokens.operations import entitlements_for
from org.feature_errors import require_feature, require_org_admin
from org.feature_keys import FeatureKey
from org.models import Organization, OrgApiConnection


class ConnectionRateLimited(APIException):
    status_code = 429

    def __init__(self) -> None:
        super().__init__(
            {
                "code": "rate_limited",
                "detail": "Administrative request budget exhausted.",
            }
        )


def _increment_budget(key: str, *, limit: int, timeout: int) -> None:
    cache.add(key, 0, timeout=timeout)
    if cache.incr(key) > limit:
        raise ConnectionRateLimited()


def check_action_budget(org_id: int, actor_id: int, *, kind: str = "admin") -> None:
    bucket = int(timezone.now().timestamp()) // 60
    limit = 30 if kind == "admin" else 5
    namespace = "admin" if kind == "admin" else "manual"
    for scope in (f"org:{org_id}", f"actor:{actor_id}"):
        _increment_budget(
            f"org-api:{namespace}:{scope}:{bucket}", limit=limit, timeout=120
        )
    if kind == "test":
        _increment_budget(
            f"org-api:test:{org_id}:{timezone.now().date().isoformat()}",
            limit=100,
            timeout=172800,
        )


def _org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, None)
    return org


def _connection(org: Organization, connection_id: int) -> OrgApiConnection:
    return get_object_or_404(OrgApiConnection, organization=org, pk=connection_id)


def _error(exc: ConnectionConfigError | CredentialError) -> Response:
    return Response(
        {"code": exc.code, "detail": exc.code},
        status=409 if exc.code == "configuration_changed" else 400,
    )


def _check_patch(connection: OrgApiConnection, patch: dict[str, Any]) -> None:
    if type(patch) is not dict or set(patch) - set(CONFIG_FIELDS) - WRITE_ONLY_FIELDS:
        raise ConnectionConfigError("invalid_config")
    raw = {field: getattr(connection, field) for field in CONFIG_FIELDS}
    raw.update({key: value for key, value in patch.items() if key in CONFIG_FIELDS})
    config = validate_connection_config(raw)
    directions = ("mmr_push_enabled", "mmr_pull_enabled", "promotion_push_enabled")
    if any(patch.get(field) is True for field in directions):
        raise ConnectionConfigError("direction_unavailable")
    added = set(config.operations) - set(connection.operations)
    required = set(entitlements_for(added))
    if (config.enabled and not connection.enabled) or (
        config.inbound_enabled and not connection.inbound_enabled
    ):
        required.update(entitlements_for(config.operations))
        if config.mmr_push_enabled or config.mmr_pull_enabled:
            required.add(FeatureKey.MMR_SYNC)
        if config.promotion_push_enabled:
            required.add(FeatureKey.PROMOTION)
    for feature in required:
        require_feature(connection.organization, feature)
    if config.outbound_auth != "none" and (
        config.mmr_push_enabled
        or config.mmr_pull_enabled
        or config.promotion_push_enabled
    ):
        if not patch.get("outbound_credential") and (
            not connection.outbound_credential_ciphertext
            or patch.get("clear_outbound_credential")
        ):
            raise ConnectionConfigError("credential_required")


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connections(request: Request, org_id: int) -> Response:
    org = _org(request, org_id)
    if request.method == "GET":
        return Response(
            ConnectionSerializer(org.api_connections.order_by("pk"), many=True).data
        )
    check_action_budget(org.pk, request.user.pk)
    try:
        with transaction.atomic():
            pending = OrgApiConnection(organization=org)
            _check_patch(pending, request.data)
            connection = OrgApiConnection.objects.create(
                organization=org,
                name="Connection",
                created_by=request.user,
                updated_by=request.user,
            )
            connection = apply_config_patch(
                connection,
                actor=request.user,
                patch=dict(request.data),
                expected_version=1,
            )
            connection.config_version = 1
            connection.save(update_fields=["config_version"])
            audit_connection(
                connection,
                actor=request.user,
                action="create_api_connection",
                fields=list(request.data),
                credential_changed="outbound_credential" in request.data,
            )
    except (ConnectionConfigError, CredentialError) as exc:
        return _error(exc)
    return Response(ConnectionSerializer(connection).data, status=201)


@api_view(["GET", "PATCH", "DELETE"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_detail(request: Request, org_id: int, connection_id: int) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if request.method == "GET":
        return Response(ConnectionSerializer(connection).data)
    check_action_budget(org.pk, request.user.pk)
    try:
        with transaction.atomic():
            current = OrgApiConnection.objects.select_for_update().get(pk=connection.pk)
            if request.method == "DELETE":
                if current.archived_at is None:
                    current.archived_at = timezone.now()
                    current.enabled = current.inbound_enabled = False
                    current.mmr_push_enabled = current.mmr_pull_enabled = (
                        current.promotion_push_enabled
                    ) = False
                    current.outbound_credential_ciphertext = (
                        current.outbound_credential_key_id
                    ) = ""
                    current.outbound_credential_owner = current.outbound_authorizer = (
                        None
                    )
                    current.outbound_credential_set_at = current.next_due_at = None
                    current.config_version += 1
                    current.updated_by = request.user
                    current.save()
                    revoke_connection_keys(current, actor=request.user)
                    invalidate_work(current)
                    audit_connection(
                        current,
                        actor=request.user,
                        action="archive_api_connection",
                        credential_changed=True,
                    )
            else:
                if type(request.data) is not dict:
                    raise ConnectionConfigError("invalid_config")
                patch = dict(request.data)
                version = patch.pop("config_version", None)
                if type(version) is not int:
                    raise ConnectionConfigError("invalid_config")
                if version != current.config_version:
                    raise ConnectionConfigError("configuration_changed")
                _check_patch(current, patch)
                grants_changed = "operations" in patch and set(
                    patch["operations"]
                ) != set(current.operations)
                flag_changes = {
                    field: patch[field]
                    for field in (
                        "enabled",
                        "inbound_enabled",
                        "mmr_push_enabled",
                        "mmr_pull_enabled",
                        "promotion_push_enabled",
                    )
                    if field in patch and patch[field] != getattr(current, field)
                }
                current = apply_config_patch(
                    current, actor=request.user, patch=patch, expected_version=version
                )
                if grants_changed:
                    revoke_connection_keys(current, actor=request.user)
                invalidate_work(current)
                audit_connection(
                    current,
                    actor=request.user,
                    action="edit_api_connection",
                    fields=[field for field in patch if field not in WRITE_ONLY_FIELDS],
                    credential_changed=bool(WRITE_ONLY_FIELDS & patch.keys()),
                )
                for enabled in (True, False):
                    fields = [
                        field
                        for field, value in flag_changes.items()
                        if value is enabled
                    ]
                    if fields:
                        audit_connection(
                            current,
                            actor=request.user,
                            action=(
                                "enable_api_connection"
                                if enabled
                                else "disable_api_connection"
                            ),
                            fields=fields,
                        )
    except (ConnectionConfigError, CredentialError) as exc:
        return _error(exc)
    return Response(ConnectionSerializer(current).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_key(
    request: Request, org_id: int, connection_id: int, action: str
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if request.data:
        return Response({"code": "invalid_config"}, status=400)
    check_action_budget(org.pk, request.user.pk)
    if action == "revoke":
        with transaction.atomic():
            current = OrgApiConnection.objects.select_for_update().get(pk=connection.pk)
            revoke_connection_keys(current, actor=request.user)
            current.key_version += 1
            current.save(update_fields=["key_version", "updated_at"])
            audit_connection(
                current,
                actor=request.user,
                action="revoke_connection_key",
                credential_changed=True,
            )
        response = Response(ConnectionSerializer(current).data)
    else:
        token, raw = issue_connection_key(
            connection, actor=request.user, rotate=action == "rotate"
        )
        connection.refresh_from_db()
        response = Response(
            {
                "connection": ConnectionSerializer(connection).data,
                "credential": {"id": token.pk, "prefix": token.prefix, "token": raw},
            },
            status=201,
        )
    response["Cache-Control"] = "no-store"
    return response
