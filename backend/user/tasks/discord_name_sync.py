"""Celery tasks that sync Discord names through the internal API."""

import time

import requests
from celery import shared_task

from discordbot.services.discord_members import (
    DiscordMembersFetchError,
    get_discord_members_data,
)
from discordbot.services.member_names import (
    members_from_discord_payload,
    members_to_json,
)
from telemetry.logging import get_logger
from user.internal_client import (
    bulk_update_member_names,
    list_discord_name_sync_targets,
)
from user.tasks.avatar_refresh import _is_test_environment

log = get_logger(__name__)


def _sync_targets(targets: list[dict]) -> None:
    org_ids_by_guild: dict[str, list[int]] = {}
    for target in targets:
        org_ids_by_guild.setdefault(str(target["guild_id"]), []).append(
            int(target["org_id"])
        )

    for guild_id, org_ids in org_ids_by_guild.items():
        fetched_at = time.time()
        try:
            raw = get_discord_members_data(guild_id, force=True, write_cache=False)
        except (DiscordMembersFetchError, requests.RequestException) as exc:
            log.warning(
                "name_sync_guild_fetch_failed",
                system="discord",
                subsystem="name_sync",
                guild_id=guild_id,
                error=str(exc),
            )
            continue

        members = members_from_discord_payload(raw)
        if not members:
            continue

        result = bulk_update_member_names(
            guild_id,
            org_ids,
            members_to_json(members),
            complete=True,
            fetched_at=fetched_at,
        )
        log.info(
            "name_sync_guild_posted",
            system="discord",
            subsystem="name_sync",
            guild_id=guild_id,
            org_count=len(org_ids),
            member_count=len(members),
            ok=result is not None,
            **(result or {}),
        )


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def sync_active_org_discord_names() -> None:
    if _is_test_environment():
        return
    _sync_targets(list_discord_name_sync_targets(scope="active", lock=True))


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def sync_org_discord_names(org_id: int) -> None:
    if _is_test_environment():
        return
    _sync_targets(list_discord_name_sync_targets(scope="all", org_id=org_id, lock=True))
