from typing import Any
from uuid import UUID

from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from org.api_connections.audit import audit_connection
from org.api_connections.authority import denial_code
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
from org.api_connections.limits import (
    MANUAL_ACTIONS_PER_MINUTE,
    TEST_ACTIONS_PER_DAY,
)
from org.api_connections.orchestration import (
    TEST_DIRECTIONS,
    create_test_run,
    enqueue_manual_pull,
    run_row,
)
from org.api_connections.promotion_config import (
    PromotionStreamError,
    check_promotion_grants,
    describe,
    lock_org,
    parse_event_bindings,
    resolve_promotion_config,
    set_promotion_binding,
    stream_archive_locked,
    stream_destination_locked,
)
from org.api_connections.recovery import (
    promotion_outbox_summary,
    release_promotion_backlog,
    resume_mmr_deliveries,
    resume_promotion_outbox,
    resync_mmr_deliveries,
)
from org.api_connections.schemas import (
    ConnectionConfigError,
    validate_connection_config,
)
from org.api_connections.serializers import ConnectionSerializer
from org.api_tokens.operations import entitlements_for
from org.feature_errors import require_feature, require_org_admin
from org.feature_keys import FeatureKey
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiPromotionAdoption,
    OrgApiSyncRun,
    OrgApiToken,
)

DELIVERY_PAGE_SIZE = 50
DELIVERY_STATES = ("pending", "retry", "paused")
DELIVERY_CURSOR_SALT = "org-api-connections.deliveries"
RUN_PAGE_SIZE = 50
RUN_CURSOR_SALT = "org-api-connections.runs"
CONFLICT_CODES = frozenset(
    {
        "configuration_changed",
        "binding_locked",
        "promotion_stream_exists",
        "promotion_stream_in_use",
        "backlog_changed",
    }
)


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
    limit = 30 if kind == "admin" else MANUAL_ACTIONS_PER_MINUTE
    namespace = "admin" if kind == "admin" else "manual"
    for scope in (f"org:{org_id}", f"actor:{actor_id}"):
        _increment_budget(
            f"org-api:{namespace}:{scope}:{bucket}", limit=limit, timeout=120
        )
    if kind == "test":
        _increment_budget(
            f"org-api:test:{org_id}:{timezone.now().date().isoformat()}",
            limit=TEST_ACTIONS_PER_DAY,
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
        status=409 if exc.code in CONFLICT_CODES else 400,
    )


def _check_patch(connection: OrgApiConnection, patch: dict[str, Any]) -> None:
    if type(patch) is not dict or set(patch) - set(CONFIG_FIELDS) - WRITE_ONLY_FIELDS:
        raise ConnectionConfigError("invalid_config")
    raw = {field: getattr(connection, field) for field in CONFIG_FIELDS}
    raw.update({key: value for key, value in patch.items() if key in CONFIG_FIELDS})
    config = validate_connection_config(raw)
    if config.promotion_push_enabled and not connection.promotion_push_enabled:
        if (
            connection.pk is None
            or not OrgApiPromotionAdoption.objects.filter(
                connection_id=connection.pk
            ).exists()
        ):
            raise ConnectionConfigError("not_promotion_stream")
        if config.outbound_auth != "bearer":
            raise ConnectionConfigError("unsupported_auth")
    added = set(config.operations) - set(connection.operations)
    try:
        check_promotion_grants(connection.organization_id, connection.pk, added)
    except PromotionStreamError as exc:
        raise ConnectionConfigError(exc.code) from None
    required = set(entitlements_for(added))
    if (config.enabled and not connection.enabled) or (
        config.inbound_enabled and not connection.inbound_enabled
    ):
        required.update(entitlements_for(config.operations))
        if config.mmr_push_enabled or config.mmr_pull_enabled:
            required.add(FeatureKey.MMR_SYNC)
        if config.promotion_push_enabled:
            required.add(FeatureKey.PROMOTION)
    if config.mmr_push_enabled and not connection.mmr_push_enabled:
        required.add(FeatureKey.MMR_SYNC)
    if config.promotion_push_enabled and not connection.promotion_push_enabled:
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
            ConnectionSerializer(
                org.api_connections.order_by("pk")
                .select_related("promotion_adoption")
                .prefetch_related(
                    Prefetch("tokens", queryset=OrgApiToken.objects.order_by("pk"))
                ),
                many=True,
            ).data
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
    disable_fields = {
        "enabled",
        "inbound_enabled",
        "mmr_push_enabled",
        "mmr_pull_enabled",
        "promotion_push_enabled",
    }
    disable_only = (
        type(request.data) is dict
        and bool(set(request.data) & disable_fields)
        and not (set(request.data) - disable_fields - {"config_version"})
        and all(
            value is False
            for field, value in request.data.items()
            if field != "config_version"
        )
    )
    if request.method != "DELETE" and not disable_only:
        check_action_budget(org.pk, request.user.pk)
    try:
        with transaction.atomic():
            if type(request.data) is dict and "operations" in request.data:
                lock_org(org.pk)
            current = OrgApiConnection.objects.select_for_update().get(pk=connection.pk)
            if request.method == "DELETE":
                if current.archived_at is None and stream_archive_locked(current):
                    raise ConnectionConfigError("promotion_stream_in_use")
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
                if "outbound_base_url" in patch and stream_destination_locked(
                    current, str(patch["outbound_base_url"])
                ):
                    raise ConnectionConfigError("binding_locked")
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
    allowed = set() if action == "revoke" else {"confirmed_operations"}
    if type(request.data) is not dict or set(request.data) - allowed:
        return Response({"code": "invalid_config"}, status=400)
    if action != "revoke":
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
            connection,
            actor=request.user,
            rotate=action == "rotate",
            confirmed_operations=request.data.get("confirmed_operations"),
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


def _delivery_row(delivery: OrgApiMmrDelivery) -> dict[str, Any]:
    entry = (delivery.payload.get("entries") or [{}])[0]
    return {
        "delivery_id": str(delivery.delivery_id),
        "org_user_id": delivery.org_user_id,
        "game_type": delivery.game_type,
        "revision": delivery.revision,
        "state": delivery.state,
        "attempts": delivery.attempts,
        "due_at": delivery.due_at,
        "last_reason": delivery.last_reason,
        "mmr": entry.get("mmr"),
        "steam_id": entry.get("steam_id"),
        "discord_id": entry.get("discord_id"),
        "destination_origin": delivery.destination_origin,
        "created_at": delivery.created_at,
    }


def _invalid(code: str = "invalid_request") -> Response:
    return Response({"code": code, "detail": code}, status=400)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_deliveries(
    request: Request, org_id: int, connection_id: int
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    params = request.query_params
    if set(params) - {"state", "cursor"}:
        return _invalid()
    state = params.get("state", "")
    if state and state not in DELIVERY_STATES:
        return _invalid()
    rows = OrgApiMmrDelivery.objects.filter(connection=connection)
    counts = dict(
        rows.filter(state__in=(*DELIVERY_STATES, "in_flight"))
        .values("state")
        .annotate(total=Count("pk"))
        .values_list("state", "total")
    )
    rows = rows.filter(state=state) if state else rows.filter(state__in=DELIVERY_STATES)
    if cursor := params.get("cursor"):
        try:
            position = signing.loads(cursor, salt=DELIVERY_CURSOR_SALT)
        except signing.BadSignature:
            return _invalid("invalid_cursor")
        if (
            type(position) is not dict
            or position.get("c") != connection.pk
            or position.get("s") != state
            or type(position.get("p")) is not int
        ):
            return _invalid("invalid_cursor")
        rows = rows.filter(pk__gt=position["p"])
    page = list(rows.order_by("pk")[: DELIVERY_PAGE_SIZE + 1])
    more = len(page) > DELIVERY_PAGE_SIZE
    page = page[:DELIVERY_PAGE_SIZE]
    return Response(
        {
            "counts": {
                name: counts.get(name, 0) for name in (*DELIVERY_STATES, "in_flight")
            },
            "items": [_delivery_row(delivery) for delivery in page],
            "next_cursor": signing.dumps(
                {"c": connection.pk, "s": state, "p": page[-1].pk},
                salt=DELIVERY_CURSOR_SALT,
            )
            if more
            else None,
        }
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_delivery_recovery(
    request: Request, org_id: int, connection_id: int, action: str
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    allowed = {"config_version"} | ({"confirm"} if action == "resync" else set())
    if type(request.data) is not dict or set(request.data) - allowed:
        return _invalid()
    version = request.data.get("config_version")
    check_action_budget(org.pk, request.user.pk, kind="manual")
    try:
        if action == "resume":
            resumed = resume_mmr_deliveries(
                connection, actor=request.user, expected_version=version
            )
            return Response({"resumed": resumed})
        enqueued = resync_mmr_deliveries(
            connection,
            actor=request.user,
            expected_version=version,
            confirmed=request.data.get("confirm") is True,
        )
        return Response({"enqueued": enqueued})
    except ConnectionConfigError as exc:
        return _error(exc)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def promotion_stream(request: Request, org_id: int) -> Response:
    org = _org(request, org_id)
    return Response(describe(resolve_promotion_config(org.pk)))


@api_view(["PUT"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_promotion_binding(
    request: Request, org_id: int, connection_id: int
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if type(request.data) is not dict or set(request.data) != {"events"}:
        return _invalid()
    require_feature(org, FeatureKey.PROMOTION)
    check_action_budget(org.pk, request.user.pk)
    try:
        resolved = set_promotion_binding(
            connection,
            actor=request.user,
            events=parse_event_bindings(request.data["events"]),
        )
    except PromotionStreamError as exc:
        return Response({"code": exc.code, "detail": exc.code}, status=exc.status)
    return Response(describe(resolved))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_promotion_outbox(
    request: Request, org_id: int, connection_id: int
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if request.query_params:
        return _invalid()
    try:
        return Response(promotion_outbox_summary(connection))
    except ConnectionConfigError as exc:
        return _error(exc)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_promotion_recovery(
    request: Request, org_id: int, connection_id: int, action: str
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    allowed = {"confirmed_count"} if action == "send-backlog" else set()
    if type(request.data) is not dict or set(request.data) != allowed:
        return _invalid()
    check_action_budget(org.pk, request.user.pk, kind="manual")
    try:
        if action == "resume":
            return Response(
                {"resumed": resume_promotion_outbox(connection, actor=request.user)}
            )
        released = release_promotion_backlog(
            connection,
            actor=request.user,
            confirmed_count=request.data["confirmed_count"],
        )
        return Response({"released": released})
    except ConnectionConfigError as exc:
        return _error(exc)


def _denied(exc: PermissionDenied) -> Response:
    code = denial_code(exc)
    return Response({"code": code, "detail": code}, status=403)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_test(request: Request, org_id: int, connection_id: int) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if (
        type(request.data) is not dict
        or set(request.data) != {"direction"}
        or request.data["direction"] not in TEST_DIRECTIONS
    ):
        return _invalid()
    check_action_budget(org.pk, request.user.pk, kind="test")
    try:
        run = create_test_run(
            connection, requester=request.user, direction=request.data["direction"]
        )
    except ConnectionConfigError as exc:
        return _error(exc)
    except PermissionDenied as exc:
        return _denied(exc)
    return Response({"run_id": str(run.pk), "state": run.state}, status=202)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_pull(request: Request, org_id: int, connection_id: int) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if type(request.data) is not dict or request.data:
        return _invalid()
    check_action_budget(org.pk, request.user.pk, kind="manual")
    try:
        run = enqueue_manual_pull(connection, requester=request.user)
    except ConnectionConfigError as exc:
        return _error(exc)
    except PermissionDenied as exc:
        return _denied(exc)
    return Response(run_row(run, now=timezone.now()), status=202)


def _not_found() -> Response:
    return Response({"code": "not_found", "detail": "not_found"}, status=404)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_runs(request: Request, org_id: int, connection_id: int) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    params = request.query_params
    if set(params) - {"cursor"}:
        return _invalid()
    runs = OrgApiSyncRun.objects.filter(connection=connection)
    if cursor := params.get("cursor"):
        try:
            position = signing.loads(cursor, salt=RUN_CURSOR_SALT)
        except signing.BadSignature:
            return _not_found()
        if (
            type(position) is not dict
            or position.get("c") != connection.pk
            or type(position.get("t")) is not str
            or type(position.get("p")) is not str
        ):
            return _not_found()
        created = parse_datetime(position["t"])
        if created is None:
            return _not_found()
        runs = runs.filter(
            Q(created_at__lt=created) | Q(created_at=created, pk__lt=position["p"])
        )
    page = list(runs.order_by("-created_at", "-pk")[: RUN_PAGE_SIZE + 1])
    more = len(page) > RUN_PAGE_SIZE
    page = page[:RUN_PAGE_SIZE]
    now = timezone.now()
    return Response(
        {
            "items": [run_row(run, now=now) for run in page],
            "next_cursor": signing.dumps(
                {
                    "c": connection.pk,
                    "t": page[-1].created_at.isoformat(),
                    "p": str(page[-1].pk),
                },
                salt=RUN_CURSOR_SALT,
            )
            if more
            else None,
        }
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def connection_run_detail(
    request: Request, org_id: int, connection_id: int, run_id: UUID
) -> Response:
    org = _org(request, org_id)
    connection = _connection(org, connection_id)
    if request.query_params:
        return _invalid()
    run = OrgApiSyncRun.objects.filter(connection=connection, pk=run_id).first()
    if run is None:
        return _not_found()
    return Response(run_row(run, now=timezone.now(), detail=True))
