from uuid import uuid4

from django.db import connection as db_connection
from rest_framework.exceptions import PermissionDenied

from org.api_connections.authority import assert_connection_authority
from org.api_connections.schemas import canonical_origin
from org.models import OrgApiConnection, OrgApiMmrDelivery, OrgMmrSyncState


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
    user = state.org_user.user
    delivery_id = uuid4()
    payload: dict[str, object] = {
        "schema_version": 1,
        "delivery_id": str(delivery_id),
        "org_id": current.organization_id,
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
    delivery, _ = OrgApiMmrDelivery.objects.get_or_create(
        connection=current,
        org_user=state.org_user,
        game_type=state.game_type,
        revision=state.revision,
        defaults={
            "delivery_id": delivery_id,
            "payload": payload,
            "origin_connection_id": origin_connection_id,
            "config_version": current.config_version,
            "destination_origin": canonical_origin(current.outbound_base_url),
        },
    )
    return delivery
