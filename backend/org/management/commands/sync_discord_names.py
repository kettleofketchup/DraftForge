import time
from argparse import ArgumentParser
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError

from app.models import Organization
from discordbot.services.discord_members import (
    DiscordMembersFetchError,
    get_discord_members_data,
)
from discordbot.services.member_names import members_from_discord_payload
from org.activity import (
    activity_tracking_enabled,
    guild_sync_lock,
    release_guild_sync_lock,
)
from org.discord_names import apply_guild_member_names, org_ids_for_guild
from telemetry.logging import get_logger

log = get_logger(__name__)


class Command(BaseCommand):
    help = "Sync Discord global names and server nicknames from each org's guild."

    def add_arguments(self, parser: ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--org", type=int, help="Sync the guild of this org id")
        group.add_argument(
            "--all", action="store_true", help="Sync every org with a guild"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not activity_tracking_enabled():
            raise CommandError(
                "Cache or cacheops is disabled, so cached payloads would keep old "
                "names. Run via docker exec in the backend container "
                "(not py::shell/py::script)."
            )
        org_id: int | None = options["org"]
        if org_id is None and not options["all"]:
            raise CommandError("Pass --org <id> or --all.")

        guild_ids = self._guild_ids(org_id)
        failed: list[str] = []
        for guild_id in guild_ids:
            if not self._sync_guild(guild_id):
                failed.append(guild_id)
        if failed:
            raise CommandError(f"Sync failed for guild(s): {', '.join(failed)}")

    def _guild_ids(self, org_id: int | None) -> list[str]:
        if org_id is not None:
            guild_id = (
                Organization.objects.nocache()
                .filter(pk=org_id)
                .values_list("discord_server_id", flat=True)
                .first()
            )
            if not guild_id:
                raise CommandError(f"Org {org_id} not found or has no Discord server.")
            return [guild_id]
        return sorted(
            set(
                Organization.objects.nocache()
                .exclude(discord_server_id__isnull=True)
                .exclude(discord_server_id="")
                .values_list("discord_server_id", flat=True)
            )
        )

    def _sync_guild(self, guild_id: str) -> bool:
        if not guild_sync_lock(guild_id):
            self.stderr.write(f"Guild {guild_id}: sync already running, skipped.")
            return True
        try:
            org_ids = org_ids_for_guild(guild_id)
            fetched_at = time.time()
            try:
                raw = get_discord_members_data(guild_id, force=True)
            except (DiscordMembersFetchError, requests.RequestException) as exc:
                log.warning(
                    "name_sync_guild_fetch_failed",
                    system="discord",
                    subsystem="name_sync",
                    guild_id=guild_id,
                    error=str(exc),
                )
                self.stderr.write(f"Guild {guild_id}: fetch failed: {exc}")
                return False
            members = members_from_discord_payload(raw)
            result = apply_guild_member_names(
                guild_id, org_ids, members, complete=True, fetched_at=fetched_at
            )
        finally:
            release_guild_sync_lock(guild_id)
        counts = " ".join(f"{k}={v}" for k, v in result.as_dict().items())
        self.stdout.write(
            f"Guild {guild_id}: orgs={len(org_ids)} members={len(members)} {counts}"
        )
        return True
