import logging

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import CustomUser, PositionsModel

logger = logging.getLogger(__name__)

PROD_API_URL = "https://dota.kettle.sh/api/users/"


class Command(BaseCommand):
    help = "Sync users from production (dota.kettle.sh) to local database"

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
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
                    f"  Would sync: {user.get('username')} (steamid: {user.get('steamid')}){admin_status}"
                )
            return

        with transaction.atomic():
            # Delete all existing users and positions
            existing_count = CustomUser.objects.count()
            self.stdout.write(f"Deleting {existing_count} existing users...")
            CustomUser.objects.all().delete()
            PositionsModel.objects.all().delete()

            # Create users from production data
            created_count = 0
            for user_data in prod_users:
                try:
                    self._create_user(user_data)
                    created_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to create user {user_data.get('username')}: {e}"
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped user {user_data.get('username')}: {e}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully synced {created_count} users from production!"
                )
            )

    def _create_user(self, user_data: dict) -> CustomUser:
        """Create a user from production API data."""
        # Create positions if provided
        positions_data = user_data.get("positions")
        if positions_data:
            positions = PositionsModel.objects.create(
                carry=positions_data.get("carry", 0),
                mid=positions_data.get("mid", 0),
                offlane=positions_data.get("offlane", 0),
                soft_support=positions_data.get("soft_support", 0),
                hard_support=positions_data.get("hard_support", 0),
            )
        else:
            positions = PositionsModel.objects.create()

        user = CustomUser.objects.create(
            username=user_data.get("username", f"user_{user_data.get('pk')}"),
            nickname=user_data.get("nickname"),
            steamid=user_data.get("steamid"),
            discordId=user_data.get("discordId"),
            avatar=user_data.get("avatar"),
            mmr=user_data.get("mmr"),
            positions=positions,
            is_staff=user_data.get("is_staff", False),
            is_superuser=user_data.get("is_superuser", False),
        )

        return user
