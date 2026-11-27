from datetime import datetime

from django.db import connection

from org.api_connections.mmr_delivery import enqueue_mmr_delivery
from org.api_connections.mutations import MmrMutationContext, deferred_identity_members
from org.models import (
    OrgApiConnection,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)


def lock_revision_counters(members: list[OrgUser]) -> None:
    organizations = {member.pk: member.organization_id for member in members}
    if not organizations:
        return
    games = set(
        OrgUserGameMmr.objects.nocache()
        .filter(org_user_id__in=organizations)
        .values_list("org_user_id", "game_type")
    ) | set(
        OrgMmrSyncState.objects.filter(org_user_id__in=organizations).values_list(
            "org_user_id", "game_type"
        )
    )
    for organization_id, game_type in sorted(
        {(organizations[member_id], game) for member_id, game in games}
    ):
        OrgMmrRevisionCounter.objects.select_for_update().get_or_create(
            organization_id=organization_id, game_type=game_type
        )


def next_revision(organization_id: int, game_type: int) -> int:
    counter, _ = OrgMmrRevisionCounter.objects.select_for_update().get_or_create(
        organization_id=organization_id, game_type=game_type
    )
    counter.revision += 1
    counter.save(update_fields=["revision"])
    return counter.revision


def record_mmr_change(
    org_user: OrgUser,
    game_type: int,
    *,
    previous_value: int,
    previous_verified_at: datetime | None,
    context: MmrMutationContext | None = None,
    identity_changed: bool = False,
    verification_changed: bool = False,
) -> int:
    if not connection.in_atomic_block:
        raise RuntimeError("MMR changes require a locked transaction")
    row = (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user=org_user, game_type=game_type)
        .first()
    )
    value = row.mmr if row is not None else 0
    state = OrgMmrSyncState.objects.filter(
        org_user=org_user, game_type=game_type
    ).first()
    verified_at = (
        row.verified_at
        if row is not None
        else (
            org_user.dota_mmr_last_verified
            if verification_changed
            else state.verified_at
            if identity_changed and state
            else None
        )
    )
    if row is None and state is not None:
        previous_verified_at = state.verified_at
    if (
        value == previous_value
        and verified_at == previous_verified_at
        and not identity_changed
        and not verification_changed
    ):
        return state.revision if state else 0
    deferred = deferred_identity_members.get()
    if identity_changed and deferred is not None:
        deferred.add(org_user.pk)
        return state.revision if state else 0
    origin_id = context.origin_connection_id if context else None
    state, _ = OrgMmrSyncState.objects.update_or_create(
        org_user=org_user,
        game_type=game_type,
        defaults={
            "revision": next_revision(org_user.organization_id, game_type),
            "value": value,
            "verified_at": verified_at,
            "last_source_connection_id": origin_id,
        },
    )
    if value != previous_value or identity_changed:
        if deferred is not None:
            deferred.add(org_user.pk)
            return state.revision
        for target in OrgApiConnection.objects.filter(
            organization_id=org_user.organization_id,
            enabled=True,
            mmr_push_enabled=True,
            archived_at__isnull=True,
        ).order_by("pk"):
            enqueue_mmr_delivery(target, state, origin_connection_id=origin_id)
    return state.revision
