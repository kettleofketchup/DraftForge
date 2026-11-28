from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction

from app.models import CustomUser
from org.api_connections.mutations import deferred_identity_members, lock_memberships
from org.api_connections.revisions import lock_revision_counters, record_mmr_change
from org.models import OrgMmrSyncState, OrgUser, OrgUserGameMmr


@contextmanager
def batch_identity_changes() -> Iterator[None]:
    if deferred_identity_members.get() is not None:
        yield
        return
    affected: set[int] = set()
    token = deferred_identity_members.set(affected)
    try:
        yield
    finally:
        deferred_identity_members.reset(token)
    with transaction.atomic():
        members = lock_memberships(list(affected), required=False)
        lock_revision_counters(members)
        for member in sorted(members, key=lambda m: (m.organization_id, m.pk)):
            publish_member_identity_change(member)


@transaction.atomic
def publish_member_identity_change(org_user: OrgUser) -> None:
    members = lock_memberships([org_user.pk])
    member = members[0]
    rows = {
        row.game_type: row
        for row in OrgUserGameMmr.objects.nocache().filter(org_user=member)
    }
    games = set(rows) | set(
        OrgMmrSyncState.objects.filter(org_user=member).values_list(
            "game_type", flat=True
        )
    )
    for game in sorted(games):
        row = rows.get(game)
        record_mmr_change(
            member,
            game,
            previous_value=row.mmr if row else 0,
            previous_verified_at=row.verified_at if row else None,
            identity_changed=True,
        )


@transaction.atomic
def publish_user_identity_change(user: CustomUser) -> None:
    members = list(
        OrgUser.objects.nocache()
        .select_for_update()
        .filter(user_id=user.pk)
        .order_by("pk")
    )
    lock_revision_counters(members)
    for member in members:
        publish_member_identity_change(member)


@contextmanager
def user_identity_mutation(user: CustomUser) -> Iterator[None]:
    with transaction.atomic():
        members = list(
            OrgUser.objects.nocache()
            .select_for_update()
            .filter(user_id=user.pk)
            .order_by("pk")
        )
        lock_revision_counters(members)
        before = (
            CustomUser.objects.nocache()
            .values_list("steam_account_id", "discordId")
            .get(pk=user.pk)
        )
        yield
        after = (
            CustomUser.objects.nocache()
            .values_list("steam_account_id", "discordId")
            .get(pk=user.pk)
        )
        if before != after:
            for member in members:
                publish_member_identity_change(member)


@contextmanager
def member_identity_mutation(member: OrgUser) -> Iterator[None]:
    with transaction.atomic():
        locked = lock_memberships([member.pk])
        before = locked[0].user_id
        yield
        after = (
            OrgUser.objects.nocache()
            .values_list("user_id", flat=True)
            .get(pk=member.pk)
        )
        if before != after:
            publish_member_identity_change(member)
