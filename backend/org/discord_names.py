"""Apply Discord guild member names to users and org memberships (backend only)."""

import copy
from collections.abc import Iterator
from dataclasses import asdict, dataclass

from cacheops import invalidate_obj as cacheops_invalidate_obj
from django.core.cache import cache
from django.db import transaction

from app.cache_utils import invalidate_model
from app.models import CustomUser, Organization
from discordbot.services.member_names import MemberNames, normalise_name
from org.models import OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)

PER_OBJECT_INVALIDATION_MAX = 1000
DISCORD_ID_CHUNK = 900
BULK_BATCH_SIZE = 500
APPLIED_SNAPSHOT_TTL_S = 86400


@dataclass(frozen=True)
class NameSyncResult:
    users_updated: int
    org_users_updated: int
    org_users_cleared: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


_ZERO = NameSyncResult(0, 0, 0)


def applied_snapshot_key(guild_id: str) -> str:
    return f"discord_name_sync_applied_{guild_id}"


def org_ids_for_guild(guild_id: str) -> list[int]:
    if not guild_id:
        return []
    return list(
        Organization.objects.nocache()
        .filter(discord_server_id=guild_id)
        .values_list("pk", flat=True)
    )


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _invalidate(
    user_snapshots: list[CustomUser], org_users: list[OrgUser], changed_rows: int
) -> None:
    if changed_rows > PER_OBJECT_INVALIDATION_MAX:
        invalidate_model(CustomUser)
        invalidate_model(OrgUser)
        mode = "model"
    else:
        for obj in [*org_users, *user_snapshots]:
            cacheops_invalidate_obj(obj)
        mode = "object"
    log.info(
        "name_sync_cache_invalidated",
        system="discord",
        subsystem="name_sync",
        mode=mode,
        users=len(user_snapshots),
        org_users=len(org_users),
    )


def apply_guild_member_names(
    guild_id: str,
    org_ids: list[int],
    members: list[MemberNames],
    *,
    complete: bool,
    fetched_at: float | None = None,
) -> NameSyncResult:
    allowed_org_ids = list(
        Organization.objects.nocache()
        .filter(pk__in=org_ids, discord_server_id=guild_id)
        .values_list("pk", flat=True)
    )
    dropped = set(org_ids) - set(allowed_org_ids)
    if dropped:
        log.warning(
            "name_sync_foreign_org_dropped",
            system="discord",
            subsystem="name_sync",
            guild_id=guild_id,
            dropped=len(dropped),
        )

    if not members and complete:
        log.warning(
            "name_sync_empty_snapshot_skipped",
            system="discord",
            subsystem="name_sync",
            guild_id=guild_id,
        )
        return _ZERO

    record_snapshot = complete and fetched_at is not None
    if complete and fetched_at is not None:
        last_applied = cache.get(applied_snapshot_key(guild_id))
        if last_applied is not None and fetched_at < last_applied:
            log.warning(
                "name_sync_stale_snapshot_dropped",
                system="discord",
                subsystem="name_sync",
                guild_id=guild_id,
                fetched_at=fetched_at,
                last_applied=last_applied,
            )
            return _ZERO

    payload = {m.discord_id: m for m in members}

    org_users = list(
        OrgUser.objects.filter(organization_id__in=allowed_org_ids)
        .select_related("user")
        .nocache()
    )
    users_by_discord_id: dict[str, CustomUser] = {}
    for ou in org_users:
        if ou.user.discordId:
            users_by_discord_id.setdefault(ou.user.discordId, ou.user)
    missing_ids = [d for d in payload if d not in users_by_discord_id]
    for chunk in _chunks(missing_ids, DISCORD_ID_CHUNK):
        for user in CustomUser.objects.filter(discordId__in=chunk).nocache():
            users_by_discord_id[user.discordId] = user

    changed_users: list[CustomUser] = []
    snapshots: dict[int, list[CustomUser]] = {}
    for discord_id, user in users_by_discord_id.items():
        member = payload.get(discord_id)
        if member is None:
            continue
        global_name = normalise_name(member.global_name)
        username = normalise_name(member.username)
        before = copy.copy(user)
        changed = False
        if user.discordNickname != global_name:
            user.discordNickname = global_name
            changed = True
        if username is not None and user.discordUsername != username:
            user.discordUsername = username
            changed = True
        if changed:
            changed_users.append(user)
            snapshots[user.pk] = [before, user]

    changed_org_users: list[OrgUser] = []
    org_users_updated = 0
    org_users_cleared = 0
    for ou in org_users:
        discord_id = ou.user.discordId
        if not discord_id:
            continue
        member = payload.get(discord_id)
        if member is not None:
            nick = normalise_name(member.nick)
            if ou.guild_nickname == nick:
                continue
            ou.guild_nickname = nick
            org_users_updated += 1
        elif complete and ou.guild_nickname is not None:
            ou.guild_nickname = None
            org_users_cleared += 1
        else:
            continue
        changed_org_users.append(ou)
        snapshots.setdefault(ou.user_id, [users_by_discord_id[discord_id]])

    result = NameSyncResult(len(changed_users), org_users_updated, org_users_cleared)
    changed_rows = len(changed_users) + len(changed_org_users)
    user_snapshots = [u for pair in snapshots.values() for u in pair]

    def _after_commit() -> None:
        if changed_rows:
            try:
                _invalidate(user_snapshots, changed_org_users, changed_rows)
            except Exception as e:
                log.error(
                    "name_sync_cache_invalidate_failed",
                    system="discord",
                    subsystem="name_sync",
                    guild_id=guild_id,
                    error_type=type(e).__name__,
                    exc_info=True,
                )
        if record_snapshot:
            cache.set(
                applied_snapshot_key(guild_id), fetched_at, APPLIED_SNAPSHOT_TTL_S
            )

    with transaction.atomic():
        if changed_users:
            CustomUser.objects.bulk_update(
                changed_users,
                ["discordNickname", "discordUsername"],
                batch_size=BULK_BATCH_SIZE,
            )
        if changed_org_users:
            OrgUser.objects.bulk_update(
                changed_org_users, ["guild_nickname"], batch_size=BULK_BATCH_SIZE
            )
        transaction.on_commit(_after_commit)

    log.info(
        "name_sync_applied",
        system="discord",
        subsystem="name_sync",
        guild_id=guild_id,
        org_count=len(allowed_org_ids),
        members=len(members),
        complete=complete,
        **result.as_dict(),
    )
    return result
