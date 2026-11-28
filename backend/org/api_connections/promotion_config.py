"""One promotion contact stream per org: deployment settings or an adopted connection.

An org reads ``settings.PROMOTION_SYNC`` / ``PROMOTION_ADAPTOR`` until it has an
``OrgApiPromotionAdoption`` row. From then on its connection binding is the
only source, enabled or not; the deployment settings are never consulted again.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.strict_json import parse_canonical_id
from config.promotion_sync import DRAFTFORGE_TOKEN_PREFIX, OrgPromotionBinding
from events.models import Event
from org.api_connections.audit import audit_connection
from org.api_connections.config import apply_config_patch
from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.limits import CREDENTIAL_BYTES
from org.api_connections.safe_http import public_origin
from org.api_connections.schemas import ConnectionConfigError
from org.api_connections.tls_adapter import SafeHttpError
from org.api_tokens.operations import PROMOTION_OPERATIONS
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiPromotionAdoption,
    OrgApiPromotionBinding,
    OrgApiPromotionEventBinding,
)
from org.models_promotion_sync import ExternalPromotionReceipt, ReceiptSource
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser

log = get_logger(__name__)

Source = Literal["deployment", "connection", "none"]
Transport = Literal["env", "connection", "held", "none"]

LEGACY_EFFECTIVE_AT: Final = datetime(1970, 1, 1, tzinfo=UTC)
MAX_EVENT_BINDINGS: Final = 500
STREAM_NAME: Final = "Promotion contact sync"


class PromotionStreamError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedPromotionConfig:
    org_id: int
    source: Source
    adopted: bool
    connection_id: int | None
    binding: OrgPromotionBinding | None
    effective_at: Mapping[int, datetime] = field(
        default_factory=lambda: MappingProxyType({})
    )
    transport: Transport = "none"

    @property
    def events(self) -> Mapping[int, int]:
        return self.binding.events if self.binding else MappingProxyType({})


def _env_transport(binding: OrgPromotionBinding | None) -> Transport:
    return "env" if binding and settings.PROMOTION_ADAPTOR.enabled else "none"


def resolve_promotion_config(org_id: int) -> ResolvedPromotionConfig:
    adoption = (
        OrgApiPromotionAdoption.objects.select_related("connection")
        .filter(organization_id=org_id)
        .first()
    )
    if adoption is None:
        env = settings.PROMOTION_SYNC.for_org(org_id)
        return ResolvedPromotionConfig(
            org_id=org_id,
            source="deployment" if env else "none",
            adopted=False,
            connection_id=None,
            binding=env,
            transport=_env_transport(env),
        )
    connection = adoption.connection
    row = (
        OrgApiPromotionBinding.objects.filter(connection=connection)
        .prefetch_related("events")
        .first()
    )
    binding = None
    effective: dict[int, datetime] = {}
    if row is not None:
        guild = parse_canonical_id(row.guild_id)
        events = {event.event_id: event.occasion_id for event in row.events.all()}
        effective = {event.event_id: event.effective_at for event in row.events.all()}
        if guild is not None:
            binding = OrgPromotionBinding(
                org_id=org_id, guild_id=guild, events=MappingProxyType(events)
            )
    live = (
        connection.archived_at is None
        and connection.enabled
        and connection.promotion_push_enabled
    )
    return ResolvedPromotionConfig(
        org_id=org_id,
        source="connection",
        adopted=True,
        connection_id=connection.pk,
        binding=binding,
        effective_at=MappingProxyType(effective),
        transport="connection" if live and binding else "held",
    )


def adopted_org_ids() -> set[int]:
    return set(
        OrgApiPromotionAdoption.objects.values_list("organization_id", flat=True)
    )


def env_dispatch_bindings() -> list[OrgPromotionBinding]:
    """Deployment bindings the env dispatcher may still send for."""
    adopted = adopted_org_ids()
    return [b for b in settings.PROMOTION_SYNC.bindings if b.org_id not in adopted]


def describe(resolved: ResolvedPromotionConfig) -> dict[str, Any]:
    return {
        "source": resolved.source,
        "adopted": resolved.adopted,
        "connection_id": resolved.connection_id,
        "guild_id": (str(resolved.binding.guild_id) if resolved.binding else None),
        "events": [
            {
                "event_id": str(event_id),
                "occasion_id": str(occasion_id),
                "effective_at": resolved.effective_at.get(event_id),
            }
            for event_id, occasion_id in sorted(resolved.events.items())
        ],
        "transport": resolved.transport,
    }


def lock_org(org_id: int) -> Organization:
    return Organization.objects.nocache().select_for_update().get(pk=org_id)


def holds_promotion_grants(operations: Iterable[str]) -> bool:
    return not PROMOTION_OPERATIONS.isdisjoint(operations)


def promotion_stream_holder(org_id: int) -> int | None:
    """The one connection allowed promotion grants: adopted, else legacy holder."""
    adopted = (
        OrgApiPromotionAdoption.objects.filter(organization_id=org_id)
        .values_list("connection_id", flat=True)
        .first()
    )
    if adopted is not None:
        return adopted
    candidates = (
        OrgApiConnection.objects.filter(
            organization_id=org_id, archived_at__isnull=True
        )
        .order_by("-legacy_multi_credential", "pk")
        .values_list("pk", "operations")
    )
    return next(
        (pk for pk, operations in candidates if holds_promotion_grants(operations)),
        None,
    )


def check_promotion_grants(
    org_id: int, connection_id: int | None, operations: Iterable[str]
) -> None:
    if not holds_promotion_grants(operations):
        return
    lock_org(org_id)
    holder = promotion_stream_holder(org_id)
    if holder is not None and holder != connection_id:
        raise PromotionStreamError("promotion_stream_exists")


def _has_receipts(org_id: int) -> bool:
    return ExternalPromotionReceipt.objects.filter(
        organization_id=org_id, source=ReceiptSource.CONTACT_LOG
    ).exists()


def _check_events(org_id: int, events: Mapping[int, int]) -> None:
    owned = set(
        Event.objects.nocache()
        .filter(pk__in=list(events), organization_id=org_id)
        .values_list("pk", flat=True)
    )
    if owned != set(events):
        raise PromotionStreamError("foreign_event", 400)


def parse_event_bindings(raw: Any) -> dict[int, int]:
    if not isinstance(raw, list) or len(raw) > MAX_EVENT_BINDINGS:
        raise PromotionStreamError("invalid_binding", 400)
    events: dict[int, int] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"event_id", "occasion_id"}:
            raise PromotionStreamError("invalid_binding", 400)
        event_id = parse_canonical_id(item["event_id"])
        occasion_id = parse_canonical_id(item["occasion_id"])
        if (
            event_id is None
            or occasion_id is None
            or event_id in events
            or occasion_id in events.values()
        ):
            raise PromotionStreamError("invalid_binding", 400)
        events[event_id] = occasion_id
    return events


def _locked_events(binding: OrgApiPromotionBinding, wanted: Mapping[int, int]) -> bool:
    current = {row.event_id: row.occasion_id for row in binding.events.all()}
    touched = {
        event_id
        for event_id, occasion in current.items()
        if wanted.get(event_id) != occasion
    }
    if not touched:
        return False
    return ExternalPromotionReceipt.objects.filter(
        organization_id=binding.organization_id,
        source=ReceiptSource.CONTACT_LOG,
        event_id__in=touched,
    ).exists()


def set_promotion_binding(
    connection: OrgApiConnection,
    *,
    actor: CustomUser,
    events: Mapping[int, int],
) -> ResolvedPromotionConfig:
    """Bind the org's single promotion stream to ``connection`` (org-admin route)."""
    org_id = connection.organization_id
    _check_events(org_id, events)
    try:
        with transaction.atomic():
            org = lock_org(org_id)
            current = OrgApiConnection.objects.select_for_update().get(pk=connection.pk)
            if current.archived_at is not None:
                raise PromotionStreamError("connection_archived")
            guild = (org.discord_server_id or "").strip()
            if parse_canonical_id(guild) is None:
                raise PromotionStreamError("guild_missing", 400)
            adoption = OrgApiPromotionAdoption.objects.filter(
                organization_id=org_id
            ).first()
            if adoption is None:
                if settings.PROMOTION_SYNC.for_org(org_id) is not None:
                    raise PromotionStreamError("managed_by_deployment")
                if promotion_stream_holder(org_id) not in (None, current.pk):
                    raise PromotionStreamError("promotion_stream_exists")
                OrgApiPromotionAdoption.objects.create(
                    organization_id=org_id, connection=current, adopted_by=actor
                )
            elif adoption.connection_id != current.pk:
                raise PromotionStreamError("promotion_stream_exists")
            binding, created = OrgApiPromotionBinding.objects.get_or_create(
                connection=current,
                defaults={"organization_id": org_id, "guild_id": guild},
            )
            if not created and binding.guild_id != guild:
                if _has_receipts(org_id):
                    raise PromotionStreamError("binding_locked")
                binding.guild_id = guild
                binding.save(update_fields=["guild_id"])
            if _locked_events(binding, events):
                raise PromotionStreamError("binding_locked")
            existing = {row.event_id: row for row in binding.events.all()}
            stale = [
                row.pk
                for event_id, row in existing.items()
                if events.get(event_id) != row.occasion_id
            ]
            OrgApiPromotionEventBinding.objects.filter(pk__in=stale).delete()
            now = timezone.now()
            OrgApiPromotionEventBinding.objects.bulk_create(
                [
                    OrgApiPromotionEventBinding(
                        binding=binding,
                        event_id=event_id,
                        occasion_id=occasion,
                        effective_at=now,
                    )
                    for event_id, occasion in events.items()
                    if event_id not in existing or existing[event_id].pk in stale
                ]
            )
            audit_connection(
                current,
                actor=actor,
                action="edit_promotion_binding",
                fields=["promotion_binding"],
            )
    except IntegrityError:
        raise PromotionStreamError("promotion_stream_exists") from None
    log.info(
        "promotion_binding_updated",
        system="org",
        subsystem="api_connections",
        org_id=org_id,
        connection_id=connection.pk,
        events=len(events),
    )
    return resolve_promotion_config(org_id)


def stream_destination_locked(connection: OrgApiConnection, new_base_url: str) -> bool:
    """A promotion stream with imported receipts keeps its outbound origin."""
    if not OrgApiPromotionAdoption.objects.filter(connection=connection).exists():
        return False

    def origin(url: str) -> str | None:
        try:
            return canonical_origin(url) if url else None
        except CredentialError:
            return url

    current = origin(connection.outbound_base_url)
    if current is None or current == origin(new_base_url):
        return False
    return _has_receipts(connection.organization_id)


def _check_credential(credential: str) -> None:
    if (
        not isinstance(credential, str)
        or not credential
        or len(credential.encode()) > CREDENTIAL_BYTES
        or not (credential.isascii() and credential.isprintable())
        or " " in credential
        or credential.startswith(DRAFTFORGE_TOKEN_PREFIX)
    ):
        raise PromotionStreamError("invalid_credential", 400)
    shared = settings.PROMOTION_ADAPTOR.api_key
    if shared and credential == shared:
        raise PromotionStreamError("shared_credential", 400)


class _DryRun(Exception):
    def __init__(self, connection: OrgApiConnection, created: bool) -> None:
        self.connection = connection
        self.created = created


def _stream_connection(
    org_id: int, actor: CustomUser, origin: str
) -> tuple[OrgApiConnection, bool]:
    holder = promotion_stream_holder(org_id)
    if holder is None:
        created = OrgApiConnection.objects.create(
            organization_id=org_id,
            name=STREAM_NAME,
            created_by=actor,
            updated_by=actor,
        )
        return created, True
    candidate = OrgApiConnection.objects.select_for_update().get(pk=holder)
    if candidate.outbound_base_url or candidate.outbound_credential_ciphertext:
        try:
            same = candidate.outbound_base_url and canonical_origin(
                candidate.outbound_base_url
            ) == canonical_origin(origin)
        except CredentialError:
            same = False
        if not same:
            raise PromotionStreamError("destination_conflict")
    return candidate, False


def adopt_legacy_promotion(
    *,
    org_id: int,
    actor: CustomUser,
    credential: str,
    base_url: str,
    dry_run: bool,
) -> OrgApiConnection:
    """Operator-only move of a deployment-bound org onto one connection stream."""
    if not (actor.is_active and actor.is_superuser):
        raise PromotionStreamError("operator_required", 403)
    env = settings.PROMOTION_SYNC.for_org(org_id)
    if env is None:
        raise PromotionStreamError("not_legacy_bound", 400)
    _check_credential(credential)
    try:
        origin = public_origin(base_url)
    except (SafeHttpError, CredentialError):
        raise PromotionStreamError("unsafe_destination", 400) from None
    _check_events(org_id, env.events)
    try:
        with transaction.atomic():
            org = lock_org(org_id)
            if (org.discord_server_id or "").strip() != str(env.guild_id):
                raise PromotionStreamError("binding_mismatch", 400)
            if OrgApiPromotionAdoption.objects.filter(organization_id=org_id).exists():
                raise PromotionStreamError("promotion_stream_exists")
            connection, created = _stream_connection(org_id, actor, origin)
            connection = apply_config_patch(
                connection,
                actor=actor,
                patch={
                    "outbound_base_url": origin,
                    "outbound_auth": "bearer",
                    "outbound_credential": credential,
                },
                expected_version=connection.config_version,
            )
            binding = OrgApiPromotionBinding.objects.create(
                organization_id=org_id,
                connection=connection,
                guild_id=str(env.guild_id),
            )
            OrgApiPromotionEventBinding.objects.bulk_create(
                [
                    OrgApiPromotionEventBinding(
                        binding=binding,
                        event_id=event_id,
                        occasion_id=occasion,
                        effective_at=LEGACY_EFFECTIVE_AT,
                    )
                    for event_id, occasion in env.events.items()
                ]
            )
            OrgApiPromotionAdoption.objects.create(
                organization_id=org_id, connection=connection, adopted_by=actor
            )
            audit_connection(
                connection,
                actor=actor,
                action="adopt_promotion_sync",
                fields=["outbound_base_url", "promotion_binding"],
                credential_changed=True,
            )
            if dry_run:
                raise _DryRun(connection, created)
    except _DryRun as preview:
        if preview.created:
            preview.connection.pk = None
        return preview.connection
    except ConnectionConfigError as exc:
        raise PromotionStreamError(exc.code, 400) from None
    except CredentialError as exc:
        raise PromotionStreamError(exc.code, 400) from None
    except IntegrityError:
        raise PromotionStreamError("promotion_stream_exists") from None
    log.info(
        "promotion_stream_adopted",
        system="org",
        subsystem="api_connections",
        org_id=org_id,
        connection_id=connection.pk,
        events=len(env.events),
    )
    return connection
