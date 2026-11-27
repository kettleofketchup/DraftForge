import random
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from pydantic import JsonValue
from rest_framework.exceptions import PermissionDenied

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
from org.api_connections.limits import OUTBOUND_REQUESTS_PER_ORG, REQUEST_SECONDS
from org.api_connections.pull import connection_config
from org.api_connections.safe_http import request_json
from org.api_connections.schemas import ConnectionConfigError
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRequest, SafeHttpResponse, StepResult
from org.models import Organization, OrgApiConnection, OrgApiMmrDelivery
from telemetry.logging import get_logger

log = get_logger(__name__)

State = OrgApiMmrDelivery.State
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 1800
LEASE_SECONDS = 60
ACK_BYTES = 64 * 1024
RETRYABLE_TRANSPORT = frozenset({"deadline_exceeded", "network_failed", "dns_failed"})
ACK_STATUSES = frozenset({"applied", "unchanged"})


class _Hold(Exception):
    def __init__(
        self, state: str, reason: str, lost: ConnectionAuthorityLost | None = None
    ) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason
        self.lost = lost


def retry_delay(attempts: int) -> timedelta:
    exponent = min(max(attempts, 1) - 1, 16)
    ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2**exponent)
    return timedelta(seconds=ceiling * (0.5 + random.random() / 2))


def _siblings(delivery: OrgApiMmrDelivery) -> QuerySet[OrgApiMmrDelivery]:
    return OrgApiMmrDelivery.objects.filter(
        connection_id=delivery.connection_id,
        org_user_id=delivery.org_user_id,
        game_type=delivery.game_type,
    ).exclude(pk=delivery.pk)


def _settle(delivery: OrgApiMmrDelivery, state: str, reason: str) -> None:
    delivery.state = state
    delivery.last_reason = reason
    delivery.lease_token = None
    delivery.lease_expires_at = None
    delivery.save(
        update_fields=[
            "state",
            "last_reason",
            "lease_token",
            "lease_expires_at",
            "due_at",
            "updated_at",
        ]
    )


def acquire_delivery_lease(
    delivery_id: UUID, *, now: datetime | None = None
) -> UUID | None:
    now = now or timezone.now()
    organization_id = (
        OrgApiMmrDelivery.objects.filter(delivery_id=delivery_id)
        .values_list("connection__organization_id", flat=True)
        .first()
    )
    if organization_id is None:
        return None
    with transaction.atomic():
        list(
            Organization.objects.nocache()
            .select_for_update()
            .filter(pk=organization_id)
            .values_list("pk", flat=True)
        )
        delivery = (
            OrgApiMmrDelivery.objects.select_for_update()
            .filter(delivery_id=delivery_id)
            .first()
        )
        if delivery is None:
            return None
        due = delivery.state in (State.PENDING, State.RETRY) and delivery.due_at <= now
        abandoned = delivery.state == State.IN_FLIGHT and (
            delivery.lease_expires_at is None or delivery.lease_expires_at <= now
        )
        if not (due or abandoned):
            return None
        if delivery.org_user_id is None:
            _settle(delivery, State.CANCELED, "membership_removed")
            return None
        siblings = _siblings(delivery)
        if siblings.filter(revision__gt=delivery.revision).exists():
            _settle(delivery, State.SUPERSEDED, "superseded")
            return None
        if siblings.filter(
            revision__lt=delivery.revision,
            state=State.IN_FLIGHT,
            lease_expires_at__gt=now,
        ).exists():
            return None
        if delivery.attempts >= MAX_ATTEMPTS:
            _settle(delivery, State.PAUSED, "retries_exhausted")
            return None
        busy = (
            OrgApiMmrDelivery.objects.filter(
                connection__organization_id=organization_id,
                state=State.IN_FLIGHT,
                lease_expires_at__gt=now,
            )
            .exclude(pk=delivery.pk)
            .count()
        )
        if busy >= OUTBOUND_REQUESTS_PER_ORG:
            return None
        fence = uuid4()
        delivery.state = State.IN_FLIGHT
        delivery.lease_token = fence
        delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        delivery.attempts += 1
        delivery.save(
            update_fields=[
                "state",
                "lease_token",
                "lease_expires_at",
                "attempts",
                "updated_at",
            ]
        )
    return fence


def _holds(delivery: OrgApiMmrDelivery, fence: UUID) -> bool:
    return (
        delivery.state == State.IN_FLIGHT
        and delivery.lease_token == fence
        and delivery.lease_expires_at is not None
        and delivery.lease_expires_at > timezone.now()
    )


def _render_query(
    query: dict[str, JsonValue], *, skip: str | None, org_id: int, game_type: int
) -> dict[str, JsonValue]:
    rendered: dict[str, JsonValue] = {}
    for key, value in query.items():
        if key == skip:
            continue
        if value == "{{org.id}}":
            rendered[key] = org_id
        elif value == "{{game_type}}":
            rendered[key] = game_type
        elif isinstance(value, str) and ("{{" in value or "}}" in value):
            raise _Hold(State.PAUSED, "invalid_config")
        else:
            rendered[key] = value
    return rendered


def _prepare(
    delivery: OrgApiMmrDelivery, connection: OrgApiConnection
) -> SafeHttpRequest:
    if connection.archived_at is not None:
        raise _Hold(State.CANCELED, "connection_archived")
    if delivery.org_user_id is None:
        raise _Hold(State.CANCELED, "membership_removed")
    try:
        origin = canonical_origin(connection.outbound_base_url)
    except CredentialError:
        origin = ""
    if origin != delivery.destination_origin:
        raise _Hold(State.PAUSED, "origin_changed")
    if connection.config_version != delivery.config_version:
        raise _Hold(State.PAUSED, "configuration_changed")
    if not (connection.enabled and connection.mmr_push_enabled):
        raise _Hold(State.PAUSED, "direction_disabled")
    try:
        assert_connection_authority(connection, direction="mmr_push")
    except ConnectionAuthorityLost as lost:
        raise _Hold(State.PAUSED, "authority_lost", lost) from None
    except PermissionDenied as denied:
        raise _Hold(State.PAUSED, denial_code(denied)) from None
    try:
        config = connection_config(connection)
    except ConnectionConfigError:
        raise _Hold(State.PAUSED, "invalid_config") from None
    push = config.mmr_push_config
    field = push.credential_field if config.outbound_auth == "api_key_field" else None
    body: dict[str, JsonValue] = dict(delivery.payload)
    if field is not None and field.location == "body" and field.key in body:
        raise _Hold(State.PAUSED, "invalid_config")
    credential = None
    if config.outbound_auth != "none":
        try:
            credential = open_credential(
                connection.outbound_credential_ciphertext,
                org_id=connection.organization_id,
                connection_id=connection.pk,
                origin=origin,
            )
        except CredentialError as exc:
            raise _Hold(State.PAUSED, exc.code) from None
    path = push.path.replace("{org_id}", str(connection.organization_id)).replace(
        "{game_type}", str(delivery.game_type)
    )
    return SafeHttpRequest(
        url=connection.outbound_base_url.rstrip("/") + path,
        method="POST",
        query=_render_query(
            push.query,
            skip=field.key if field is not None and field.location == "query" else None,
            org_id=connection.organization_id,
            game_type=delivery.game_type,
        ),
        body=body,
        auth=config.outbound_auth,
        credential=credential,
        credential_origin=origin if credential is not None else None,
        credential_field=field,
        idempotency_key=str(delivery.delivery_id),
    )


def _classify(
    delivery: OrgApiMmrDelivery, response: SafeHttpResponse
) -> tuple[str, str]:
    status = response.status
    if status in (401, 403):
        return State.PAUSED, "auth_failed"
    if status in (408, 429) or status >= 500:
        return State.RETRY, f"http_{status}"
    if not 200 <= status < 300:
        return State.PAUSED, "schema_rejected"
    data = response.data
    if (
        isinstance(data, dict)
        and data.get("delivery_id") == str(delivery.delivery_id)
        and data.get("status") in ACK_STATUSES
    ):
        return State.APPLIED, str(data["status"])
    return State.PAUSED, "invalid_acknowledgement"


def _finalize(
    delivery: OrgApiMmrDelivery, fence: UUID, state: str, reason: str
) -> StepResult:
    now = timezone.now()
    with transaction.atomic():
        locked = (
            OrgApiMmrDelivery.objects.select_for_update()
            .filter(
                pk=delivery.pk,
                lease_token=fence,
                state=State.IN_FLIGHT,
                lease_expires_at__gt=now,
            )
            .first()
        )
        if locked is None:
            delivery.refresh_from_db()
            return StepResult(delivery.state, False, "stale_fence")
        if state == State.RETRY:
            connection = OrgApiConnection.objects.get(pk=locked.connection_id)
            if _siblings(locked).filter(revision__gt=locked.revision).exists():
                state, reason = State.SUPERSEDED, "superseded"
            elif (
                connection.archived_at is not None
                or connection.config_version != locked.config_version
            ):
                state, reason = State.PAUSED, "configuration_changed"
            elif locked.attempts >= MAX_ATTEMPTS:
                state, reason = State.PAUSED, "retries_exhausted"
            else:
                locked.due_at = now + retry_delay(locked.attempts)
        _settle(locked, state, reason)
    log.info(
        "api_connection_delivery",
        system="org",
        subsystem="api_connections",
        org_id=delivery.payload.get("org_id"),
        connection_id=locked.connection_id,
        delivery_id=str(locked.delivery_id),
        state=state,
        reason=reason,
        attempts=locked.attempts,
    )
    return StepResult(state, False, None if state == State.APPLIED else reason)


def step_mmr_delivery(delivery_id: UUID, *, fence: UUID) -> StepResult:
    delivery = OrgApiMmrDelivery.objects.filter(delivery_id=delivery_id).first()
    if delivery is None:
        return StepResult("missing", False, "not_found")
    if not _holds(delivery, fence):
        return StepResult(delivery.state, False, "stale_fence")
    connection = OrgApiConnection.objects.get(pk=delivery.connection_id)
    try:
        request = _prepare(delivery, connection)
    except _Hold as hold:
        result = _finalize(delivery, fence, hold.state, hold.reason)
        if hold.lost is not None:
            hold.lost.cleanup()
        return result
    try:
        response = request_json(
            request,
            deadline=time.monotonic() + REQUEST_SECONDS,
            max_bytes=ACK_BYTES,
        )
    except SafeHttpError as exc:
        if exc.code in RETRYABLE_TRANSPORT:
            state, reason = State.RETRY, exc.code
        elif exc.code == "invalid_json":
            state, reason = State.PAUSED, "invalid_acknowledgement"
        else:
            state, reason = State.PAUSED, exc.code
    else:
        state, reason = _classify(delivery, response)
    del request
    return _finalize(delivery, fence, state, reason)
