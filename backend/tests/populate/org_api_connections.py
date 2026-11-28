"""Populate and reset the org API connections E2E data (tests.data.org_api_connections).

reset_org_api_connections_data, behind POST /api/tests/org-api-connections/reset/,
creates or updates the two orgs and their users, deletes every connection row
of the two orgs in FK-safe order (see reset_connection_rows), puts the
switches, roles and seed MMRs back and seeds one disabled connection with a
finished pull run in the second org. populate_org_api_connections_data runs
the same reset.
"""

from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from common.game import GameType
from org.api_connections.runs import run_summary
from org.features import FeatureKey, set_org_feature
from org.mmr import set_org_mmr
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiLimits,
    OrgApiMmrDelivery,
    OrgApiMmrPullTarget,
    OrgApiPromotionAdoption,
    OrgApiPromotionBinding,
    OrgApiPromotionEventBinding,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
)
from org.models_promotion_sync import (
    ExternalPromotionReceipt,
    OutboxState,
    PromotionContactOutbox,
    PromotionImportObservation,
)
from tests.data.models import TestOrganization, TestUser
from tests.data.org_api_connections import (
    AC_NO_STEAM,
    AC_PLAYER_ONE,
    AC_PLAYER_TWO,
    AC_SECOND_ADMIN,
    AC_SEED_MMRS,
    API_CONNECTIONS_ORG,
    API_CONNECTIONS_ORGS,
    API_CONNECTIONS_ROLE_USERS,
    API_CONNECTIONS_ROLES,
    API_CONNECTIONS_SECOND_ORG,
    API_CONNECTIONS_USERS,
    FAKE_BAD_CREDENTIAL,
    FAKE_GOOD_CREDENTIAL,
    FAKE_MOVED_ORIGIN,
    FAKE_ORIGIN,
    FAKE_PULL_PATH,
    SEEDED_CONNECTION_NAME,
)
from tests.populate.utils import ensure_org_user
from user.models import PositionsModel

PROMOTION_GUILD_ID = "830000000000000001"
BACKLOG_SIZE = 3
BACKLOG_SEND_BASE = 830_001


def _ensure_org(data: TestOrganization) -> Organization:
    org, _ = Organization.objects.update_or_create(
        pk=data.pk,
        defaults={
            "name": data.name,
            "description": data.description,
            "logo": "",
            "timezone": data.timezone,
        },
    )
    return org


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.steam_account_id = data.get_steam_account_id()
    user.steamid = data.get_steam_id_64()
    user.is_active = True
    user.save()
    return user


def reset_connection_rows(org_pks: list[int]) -> None:
    """Delete every API connection row of ``org_pks`` in FK-safe order.

    Ledgers and sync state first, then token usage, tokens and limits, then the
    connections last: tokens RESTRICT a connection's deletion.
    """
    OrgApiMmrDelivery.objects.filter(connection__organization_id__in=org_pks).delete()
    OrgApiMmrPullTarget.objects.filter(run__organization_id__in=org_pks).delete()
    OrgApiRunCheckpoint.objects.filter(run__organization_id__in=org_pks).delete()
    OrgApiSyncRun.objects.filter(organization_id__in=org_pks).delete()
    OrgApiPromotionEventBinding.objects.filter(
        binding__organization_id__in=org_pks
    ).delete()
    OrgApiPromotionBinding.objects.filter(organization_id__in=org_pks).delete()
    OrgApiPromotionAdoption.objects.filter(organization_id__in=org_pks).delete()
    PromotionContactOutbox.objects.filter(organization_id__in=org_pks).delete()
    ExternalPromotionReceipt.objects.filter(organization_id__in=org_pks).delete()
    PromotionImportObservation.objects.filter(organization_id__in=org_pks).delete()
    OrgMmrSyncState.objects.filter(org_user__organization_id__in=org_pks).delete()
    OrgMmrRevisionCounter.objects.filter(organization_id__in=org_pks).delete()
    OrgApiTokenUsage.objects.filter(organization_id__in=org_pks).delete()
    OrgApiToken.objects.filter(organization_id__in=org_pks).delete()
    OrgApiLimits.objects.filter(organization_id__in=org_pks).delete()
    OrgApiConnection.objects.filter(organization_id__in=org_pks).delete()


def clear_action_budgets(org_pks: list[int], user_pks: list[int]) -> None:
    """Forget the per-minute admin/manual and daily test budgets of these orgs."""
    now = timezone.now()
    bucket = int(now.timestamp()) // 60
    keys: list[str] = []
    for namespace in ("admin", "manual"):
        for minute in (bucket - 1, bucket):
            keys += [f"org-api:{namespace}:org:{pk}:{minute}" for pk in org_pks]
            keys += [f"org-api:{namespace}:actor:{pk}:{minute}" for pk in user_pks]
    for day in (now.date() - timedelta(days=1), now.date()):
        keys += [f"org-api:test:{pk}:{day.isoformat()}" for pk in org_pks]
    cache.delete_many(keys)


def _seed_second_org(org: Organization, owner: CustomUser) -> OrgApiConnection:
    connection = OrgApiConnection.objects.create(
        organization=org,
        name=SEEDED_CONNECTION_NAME,
        created_by=owner,
        updated_by=owner,
        outbound_base_url=FAKE_ORIGIN,
        mmr_pull_config={
            "path": FAKE_PULL_PATH,
            "mapping": {
                "list_path": "players",
                "player_id_path": "steam_id",
                "mmr_path": "mmr",
            },
        },
    )
    finished = timezone.now() - timedelta(days=1)
    run = OrgApiSyncRun.objects.create(
        organization=org,
        connection=connection,
        kind=OrgApiSyncRun.Kind.MMR_PULL,
        requester=owner,
        state=OrgApiSyncRun.State.SUCCEEDED,
        created_at=finished - timedelta(minutes=1),
        started_at=finished - timedelta(minutes=1),
        finished_at=finished,
        request_count=1,
        row_count=2,
        unchanged_count=1,
        unmatched_count=1,
        issue_count=1,
        issues=[{"code": "unmatched", "page": 1, "index": 1, "player_id": "839998"}],
        config_snapshot={"trigger": "manual"},
    )
    connection.last_run_summary = run_summary(run)
    connection.last_success_at = finished
    connection.save(update_fields=["last_run_summary", "last_success_at"])
    return connection


def reset_org_api_connections_data() -> dict[str, Any]:
    """Put the API connection orgs, users, roles, switches and seed back."""
    with transaction.atomic():
        orgs = {o.pk: _ensure_org(o) for o in API_CONNECTIONS_ORGS}
        users = {u.pk: _ensure_user(u) for u in API_CONNECTIONS_USERS}
        org_pks = list(orgs)
        reset_connection_rows(org_pks)
        for org_data, owner, admins, staff, members, features in API_CONNECTIONS_ROLES:
            org = orgs[org_data.pk]
            org.owner = users[owner.pk]
            org.save(update_fields=["owner"])
            org.admins.set([users[u.pk] for u in admins])
            org.staff.set([users[u.pk] for u in staff])
            org.promoters.clear()
            member_pks = [m.pk for m in members]
            OrgUser.objects.nocache().filter(organization=org).exclude(
                user_id__in=member_pks
            ).delete()
            for pk in member_pks:
                ensure_org_user(users[pk], org)
            for key in FeatureKey:
                set_org_feature(org, key, enabled=key.value in features, actor=None)
        main = orgs[API_CONNECTIONS_ORG.pk]
        for user_pk in (AC_PLAYER_ONE.pk, AC_PLAYER_TWO.pk, AC_NO_STEAM.pk):
            member = OrgUser.objects.nocache().get(organization=main, user_id=user_pk)
            set_org_mmr(
                member,
                GameType.DOTA2,
                AC_SEED_MMRS.get(user_pk),
                mark_verified=False,
            )
        _seed_second_org(orgs[API_CONNECTIONS_SECOND_ORG.pk], users[AC_SECOND_ADMIN.pk])
    clear_action_budgets(org_pks, list(users))
    invalidate_model(OrgUser)
    for org in orgs.values():
        invalidate_obj(org)
    for user in users.values():
        invalidate_obj(user)
    return org_api_connections_test_data()


def seed_promotion_backlog(actor: CustomUser) -> OrgApiConnection:
    """Adopt a promotion stream connection holding a confirmed-release backlog."""
    org = Organization.objects.get(pk=API_CONNECTIONS_ORG.pk)
    now = timezone.now()
    with transaction.atomic():
        connection = OrgApiConnection.objects.create(
            organization=org,
            name="Promotion stream",
            created_by=actor,
            updated_by=actor,
            enabled=True,
            inbound_enabled=True,
            operations=["promotion:read", "promotion:write"],
            outbound_base_url=FAKE_ORIGIN,
        )
        OrgApiPromotionAdoption.objects.create(
            organization=org, connection=connection, adopted_by=actor
        )
        OrgApiPromotionBinding.objects.create(
            organization=org, connection=connection, guild_id=PROMOTION_GUILD_ID
        )
        PromotionContactOutbox.objects.bulk_create(
            PromotionContactOutbox(
                organization=org,
                local_send_id=BACKLOG_SEND_BASE + index,
                event_id=BACKLOG_SEND_BASE + index,
                sent_at=now - timedelta(hours=index + 1),
                state=OutboxState.BACKLOG_HELD,
            )
            for index in range(BACKLOG_SIZE)
        )
    return connection


def populate_org_api_connections_data(force: bool = False) -> None:
    """Create the API connection orgs and users; `force` changes nothing."""
    print("  Populating org API connections E2E data...")
    reset_org_api_connections_data()
    print(f"    Created {', '.join(o.name for o in API_CONNECTIONS_ORGS)}")


def org_api_connections_test_data() -> dict[str, Any]:
    """PKs, names and fixture constants the specs look up (never hardcoded)."""
    seeded = (
        OrgApiConnection.objects.filter(
            organization_id=API_CONNECTIONS_SECOND_ORG.pk, name=SEEDED_CONNECTION_NAME
        )
        .values_list("pk", flat=True)
        .first()
    )
    return {
        "orgs": {
            "main": {"pk": API_CONNECTIONS_ORG.pk, "name": API_CONNECTIONS_ORG.name},
            "second": {
                "pk": API_CONNECTIONS_SECOND_ORG.pk,
                "name": API_CONNECTIONS_SECOND_ORG.name,
            },
        },
        "users": {
            role: {"pk": u.pk, "username": u.username}
            for role, u in API_CONNECTIONS_ROLE_USERS.items()
        },
        "players": {
            "one": {
                "pk": AC_PLAYER_ONE.pk,
                "steam_id": AC_PLAYER_ONE.get_steam_account_id(),
                "mmr": AC_SEED_MMRS[AC_PLAYER_ONE.pk],
            },
            "two": {
                "pk": AC_PLAYER_TWO.pk,
                "steam_id": AC_PLAYER_TWO.get_steam_account_id(),
                "mmr": 0,
            },
            "no_steam": {"pk": AC_NO_STEAM.pk},
        },
        "fake": {
            "origin": FAKE_ORIGIN,
            "moved_origin": FAKE_MOVED_ORIGIN,
            "good_credential": FAKE_GOOD_CREDENTIAL,
            "bad_credential": FAKE_BAD_CREDENTIAL,
            "pull_path": FAKE_PULL_PATH,
        },
        "seeded_connection": seeded,
    }
