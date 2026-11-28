from datetime import timedelta
from uuid import uuid4

from django.db import connection as db_connection
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from org.api_connections.authority import assert_connection_authority
from org.api_connections.schemas import canonical_origin
from org.models import OrgApiConnection, OrgApiMmrDelivery, OrgMmrSyncState

LOOP_WINDOW = timedelta(minutes=10)
LOOP_LIMIT = 10
UNSENT_STATES = ("pending", "retry", "paused")


def _loop_suspected(connection: OrgApiConnection, state: OrgMmrSyncState) -> bool:
    recent = OrgApiMmrDelivery.objects.filter(
        connection=connection,
        org_user_id=state.org_user_id,
        game_type=state.game_type,
        origin_connection__isnull=False,
        created_at__gte=timezone.now() - LOOP_WINDOW,
    )
    return recent.count() >= LOOP_LIMIT


def build_mmr_delivery(
    connection: OrgApiConnection,
    state: OrgMmrSyncState,
    *,
    origin_connection_id: int | None,
    guarded: bool = False,
) -> OrgApiMmrDelivery:
    user = state.org_user.user
    delivery_id = uuid4()
    payload: dict[str, object] = {
        "schema_version": 1,
        "delivery_id": str(delivery_id),
        "org_id": connection.organization_id,
        "game_type": state.game_type,
        "entries": [
            {
                "org_user_id": state.org_user_id,
                "steam_id": str(user.steam_account_id)
                if user.steam_account_id is not None
                else None,
                "discord_id": user.discordId or None,
                "mmr": state.value,
                "revision": state.revision,
            }
        ],
    }
    return OrgApiMmrDelivery(
        connection=connection,
        org_user=state.org_user,
        game_type=state.game_type,
        revision=state.revision,
        delivery_id=delivery_id,
        payload=payload,
        origin_connection_id=origin_connection_id,
        config_version=connection.config_version,
        destination_origin=canonical_origin(connection.outbound_base_url),
        state="paused" if guarded else "pending",
        last_reason="sync_loop_suspected" if guarded else "",
    )


def supersede_unsent(
    connection: OrgApiConnection,
    *,
    game_type: int,
    org_user_ids: list[int],
    below_revision: int,
) -> int:
    now = timezone.now()
    return OrgApiMmrDelivery.objects.filter(
        connection=connection,
        org_user_id__in=org_user_ids,
        game_type=game_type,
        revision__lt=below_revision,
        state__in=UNSENT_STATES,
    ).update(
        state="superseded",
        last_reason="superseded",
        lease_token=None,
        lease_expires_at=None,
        updated_at=now,
    )


def enqueue_mmr_delivery(
    connection: OrgApiConnection,
    state: OrgMmrSyncState,
    *,
    origin_connection_id: int | None,
) -> OrgApiMmrDelivery | None:
    if not db_connection.in_atomic_block:
        raise RuntimeError("MMR delivery requires a locked transaction")
    if connection.pk == origin_connection_id:
        return None
    current = OrgApiConnection.objects.get(pk=connection.pk)
    if current.organization_id != state.org_user.organization_id:
        return None
    try:
        assert_connection_authority(current, direction="mmr_push")
    except PermissionDenied:
        return None
    if current.game_type is not None and current.game_type != state.game_type:
        return None
    guarded = origin_connection_id is not None and _loop_suspected(current, state)
    built = build_mmr_delivery(
        current, state, origin_connection_id=origin_connection_id, guarded=guarded
    )
    delivery, created = OrgApiMmrDelivery.objects.get_or_create(
        connection=current,
        org_user=state.org_user,
        game_type=state.game_type,
        revision=state.revision,
        defaults={
            field: getattr(built, field)
            for field in (
                "delivery_id",
                "payload",
                "origin_connection_id",
                "config_version",
                "destination_origin",
                "state",
                "last_reason",
            )
        },
    )
    if created:
        supersede_unsent(
            current,
            game_type=state.game_type,
            org_user_ids=[state.org_user_id],
            below_revision=state.revision,
        )
    return delivery
