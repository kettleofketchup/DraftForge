from argparse import ArgumentParser
from typing import Any

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import CustomUser, PositionsModel
from org.models import (
    AttendanceOutcome,
    ContributionEntry,
    EventCaptain,
    Organization,
    PromoSend,
)
from telemetry.logging import get_logger
from user.management.prod_payload import (
    create_positions,
    position_values,
    steam_account_id,
)

log = get_logger(__name__)

PROD_API_URL = "https://dota.kettle.sh/api/users/"


class Command(BaseCommand):
    help = "Sync users from production (dota.kettle.sh) to local database"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=PROD_API_URL,
            help=f"Production API URL (default: {PROD_API_URL})",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options.get("dry_run", False)
        api_url = options.get("url", PROD_API_URL)

        self.stdout.write(f"Fetching users from {api_url}...")

        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            prod_users = response.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch users: {e}"))
            raise

        self.stdout.write(f"Found {len(prod_users)} users in production")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            for user in prod_users:
                admin_status = ""
                if user.get("is_superuser"):
                    admin_status = " [superuser]"
                elif user.get("is_staff"):
                    admin_status = " [staff]"
                self.stdout.write(
                    f"  Would sync: {user.get('username')} (steam_account_id: {user.get('steam_account_id')}){admin_status}"
                )
            return

        with transaction.atomic():
            # Organization.owner is PROTECT: owners stay and are updated in place.
            owner_ids = set(
                Organization.objects.filter(owner__isnull=False).values_list(
                    "owner_id", flat=True
                )
            )
            kept = list(CustomUser.objects.filter(pk__in=owner_ids))
            existing_count = CustomUser.objects.count()
            self.stdout.write(
                f"Deleting {existing_count - len(kept)} existing users "
                f"(keeping {len(kept)} organization owners)..."
            )
            AttendanceOutcome.objects.nocache().all().delete()
            EventCaptain.objects.nocache().all().delete()
            ContributionEntry.objects.nocache().all().delete()
            PromoSend.objects.all().delete()
            CustomUser.objects.exclude(pk__in=owner_ids).delete()
            PositionsModel.objects.filter(dotauserprofile__isnull=True).delete()

            by_discord = {u.discordId: u for u in kept if u.discordId}
            by_username = {u.username: u for u in kept if u.username}

            synced_count = 0
            for user_data in prod_users:
                existing = self._match_kept(user_data, by_discord, by_username)
                try:
                    with transaction.atomic():
                        if existing is None:
                            self._create_user(user_data)
                        else:
                            self._update_user(existing, user_data)
                    synced_count += 1
                except Exception as e:
                    log.warning(
                        "prod_user_sync_skipped",
                        system="app",
                        subsystem="prod_import",
                        username=user_data.get("username"),
                        error=str(e),
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped user {user_data.get('username')}: {e}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully synced {synced_count} users from production!"
                )
            )

    @staticmethod
    def _match_kept(
        user_data: dict[str, Any],
        by_discord: dict[str, CustomUser],
        by_username: dict[str, CustomUser],
    ) -> CustomUser | None:
        discord_id = user_data.get("discordId")
        if discord_id:
            return by_discord.get(discord_id)
        return by_username.get(user_data.get("username"))

    def _create_user(self, user_data: dict[str, Any]) -> CustomUser:
        """Create a user from production API data."""
        return CustomUser.objects.create(
            username=user_data.get("username", f"user_{user_data.get('pk')}"),
            nickname=user_data.get("nickname"),
            steam_account_id=steam_account_id(user_data),
            discordId=user_data.get("discordId"),
            avatar=user_data.get("avatar"),
            positions=create_positions(user_data),
            is_staff=user_data.get("is_staff", False),
            is_superuser=user_data.get("is_superuser", False),
        )

    def _update_user(self, user: CustomUser, user_data: dict[str, Any]) -> None:
        user.username = user_data.get("username", user.username)
        user.steamid = None
        user.steam_account_id = steam_account_id(user_data)
        user.discordId = user_data.get("discordId", user.discordId)
        user.is_staff = user_data.get("is_staff", False)
        user.is_superuser = user_data.get("is_superuser", False)
        user.save()
        user.nickname = user_data.get("nickname")
        user.avatar = user_data.get("avatar")
        positions = user.positions
        if positions is None:
            user.positions = create_positions(user_data)
        else:
            for field, value in position_values(user_data).items():
                setattr(positions, field, value)
            positions.save()
